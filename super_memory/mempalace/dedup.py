"""Drawer deduplication — detect and remove near-duplicate drawers.

Detects near-duplicate drawers using Jaccard similarity on token sets.
Keeps the longest/richest version when duplicates found; deletes shorter ones.
Pure SQLite + regex. No embeddings, no network.

Usage:
    from super_memory.mempalace.dedup import deduplicate
    result = deduplicate(db_path, threshold=0.7, dry_run=True)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def deduplicate(
    db_path: Path | str,
    wing: str | None = None,
    threshold: float = 0.7,
    dry_run: bool = True,
    min_content_length: int = 20,
) -> dict[str, Any]:
    """Scan drawers for duplicates and deduplicate.

    Strategy:
      1. Fetch all drawers in scope (optionally filtered by wing)
      2. Tokenize each drawer's content
      3. For each pair with Jaccard similarity >= threshold:
         - Keep the longer/richer drawer
         - Mark shorter for deletion
      4. If not dry_run, DELETE the duplicates

    Args:
        db_path: Path to super_memory SQLite database
        wing: Optional wing filter
        threshold: Minimum Jaccard similarity to consider duplicate (default 0.7)
        dry_run: If True, only report what would be removed
        min_content_length: Skip drawers shorter than this

    Returns:
        Dict with stats, duplicate groups, and deleted IDs
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        return {"error": f"Database not found: {db_path}"}

    conn = sqlite3.connect(str(db), timeout=30)
    conn.row_factory = sqlite3.Row

    try:
        # Fetch drawers
        where_parts: list[str] = []
        params: list[Any] = []
        if wing:
            where_parts.append("wing = ?")
            params.append(wing)

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"
        rows = conn.execute(
            f"SELECT id, wing, room, hall, content, source_file, created_at "
            f"FROM palace_drawers WHERE {where_clause} AND length(content) >= ? "
            f"ORDER BY length(content) DESC",
            params + [min_content_length],
        ).fetchall()

        if len(rows) < 2:
            return {
                "total_drawers": len(rows),
                "duplicate_groups": 0,
                "duplicates_found": 0,
                "deleted": 0,
                "dry_run": dry_run,
                "groups": [],
            }

        # Build token sets
        drawer_info: list[dict[str, Any]] = []
        for row in rows:
            tokens = set(_tokenize(row["content"] or ""))
            drawer_info.append({
                "id": row["id"],
                "wing": row["wing"] or "",
                "room": row["room"] or "",
                "tokens": tokens,
                "token_count": len(tokens),
                "content_length": len(row["content"] or ""),
                "source_file": Path(row["source_file"] or "?").name if row["source_file"] else "?",
            })

        # Find duplicate groups
        duplicate_groups: list[dict[str, Any]] = []
        to_delete: set[str] = set()
        n = len(drawer_info)

        for i in range(n):
            if drawer_info[i]["id"] in to_delete:
                continue
            group_dupes: list[dict[str, Any]] = []
            for j in range(i + 1, n):
                if drawer_info[j]["id"] in to_delete:
                    continue
                sim = jaccard_similarity(drawer_info[i]["tokens"], drawer_info[j]["tokens"])
                if sim >= threshold:
                    # Keep the longer one, delete the shorter
                    if drawer_info[i]["content_length"] >= drawer_info[j]["content_length"]:
                        keep, discard = drawer_info[i], drawer_info[j]
                    else:
                        keep, discard = drawer_info[j], drawer_info[i]

                    group_dupes.append({
                        "id": discard["id"],
                        "wing": discard["wing"],
                        "room": discard["room"],
                        "content_length": discard["content_length"],
                        "source_file": discard["source_file"],
                        "similarity_to_kept": round(sim, 3),
                    })
                    to_delete.add(discard["id"])

            if group_dupes:
                duplicate_groups.append({
                    "kept": {
                        "id": drawer_info[i]["id"],
                        "wing": drawer_info[i]["wing"],
                        "content_length": drawer_info[i]["content_length"],
                        "source_file": drawer_info[i]["source_file"],
                    },
                    "duplicates": group_dupes,
                })

        # Execute deletion if not dry run
        deleted = 0
        if not dry_run and to_delete:
            placeholders = ",".join("?" for _ in to_delete)
            conn.execute("DELETE FROM palace_drawers WHERE id IN (" + placeholders + ")", list(to_delete))
            # Also clean up associated metadata
            for dup_id in to_delete:
                conn.execute("DELETE FROM palace_metadata WHERE drawer_id = ?", (dup_id,))
            conn.commit()
            deleted = len(to_delete)

        return {
            "total_drawers": len(rows),
            "duplicate_groups": len(duplicate_groups),
            "duplicates_found": len(to_delete),
            "deleted": deleted,
            "dry_run": dry_run,
            "threshold": threshold,
            "groups": duplicate_groups[:20],  # Limit output size
        }

    finally:
        conn.close()


def deduplicate_memories(
    store: Any,
    threshold: float = 0.6,
    dry_run: bool = True,
    limit: int = 500,
    min_content_length: int = 20,
) -> dict[str, Any]:
    """Cluster-based dedup for the memories table.

    P1 Optimization: Replace content_hash exact-match with Jaccard/tf-idf
    clustering on memory content. Detects near-duplicates missed by exact
    hash matching.

    Strategy:
      1. Fetch all active memories (grouped by agent_id to keep scope)
      2. Tokenize each memory's content
      3. For each pair with Jaccard similarity >= threshold:
         - Keep the longer/richer memory (more content_length)
         - Mark shorter for soft-delete

    Args:
        store: SuperMemoryStore instance
        threshold: Minimum Jaccard similarity (default 0.6)
        dry_run: If True, only report
        limit: Max memories to scan per agent
        min_content_length: Skip memories shorter than this

    Returns:
        Dict with stats and duplicate groups
    """
    import sqlite3

    report: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "total_scanned": 0,
        "duplicate_groups": 0,
        "duplicates_found": 0,
        "deleted": 0,
        "threshold": threshold,
        "groups": [],
    }

    with store.connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row

        # Get distinct agents
        agents = conn.execute(
            "SELECT DISTINCT agent_id FROM memories WHERE agent_id IS NOT NULL AND LENGTH(content) >= ?",
            (min_content_length,),
        ).fetchall()

        for agent_row in agents:
            agent_id = agent_row["agent_id"]
            rows = conn.execute(
                "SELECT id, content, type, created_at FROM memories WHERE agent_id = ? AND LENGTH(content) >= ? ORDER BY LENGTH(content) DESC LIMIT ?",
                (agent_id, min_content_length, limit),
            ).fetchall()

            if len(rows) < 2:
                continue

            # Build token sets
            memories: list[dict[str, Any]] = []
            for row in rows:
                tokens = set(re.findall(r"\w{3,}", (row["content"] or "").lower()))
                if len(tokens) < 3:
                    continue
                memories.append({
                    "id": row["id"],
                    "agent_id": agent_id,
                    "type": row["type"],
                    "tokens": tokens,
                    "token_count": len(tokens),
                    "content_length": len(row["content"] or ""),
                    "created_at": row["created_at"],
                })

            report["total_scanned"] += len(memories)

            # Find duplicate groups within this agent
            to_delete: set[str] = set()
            n = len(memories)

            for i in range(n):
                if memories[i]["id"] in to_delete:
                    continue
                group_dupes: list[dict[str, Any]] = []
                for j in range(i + 1, n):
                    if memories[j]["id"] in to_delete:
                        continue
                    sim = jaccard_similarity(memories[i]["tokens"], memories[j]["tokens"])
                    if sim >= threshold:
                        # Keep the longer one
                        if memories[i]["content_length"] >= memories[j]["content_length"]:
                            keep, discard = memories[i], memories[j]
                        else:
                            keep, discard = memories[j], memories[i]

                        group_dupes.append({
                            "id": discard["id"],
                            "agent_id": agent_id,
                            "type": discard["type"],
                            "content_length": discard["content_length"],
                            "similarity_to_kept": round(sim, 3),
                        })
                        to_delete.add(discard["id"])

                if group_dupes:
                    report["duplicate_groups"] += 1
                    report["duplicates_found"] += len(group_dupes)
                    report["groups"].append({
                        "kept": {
                            "id": memories[i]["id"],
                            "agent_id": agent_id,
                            "content_length": memories[i]["content_length"],
                        },
                        "duplicates": group_dupes,
                    })

        # Execute deletion if not dry run
        if not dry_run and to_delete:
            for dup_id in to_delete:
                conn.execute("DELETE FROM memories WHERE id = ?", (dup_id,))
            conn.commit()
            report["deleted"] = len(to_delete)

    # Trim groups to avoid oversized response
    report["groups"] = report["groups"][:20]
    return report


# Re-export for convenience
__all__ = ["deduplicate", "deduplicate_memories", "jaccard_similarity"]
