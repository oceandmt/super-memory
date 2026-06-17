"""Collision detection — pre-write defense against drawer_id collisions.

Runs before batched inserts to detect duplicate or conflicting drawer_ids.
Catches two classes of issue:
  1. Duplicate (source_file, chunk_index) pairs in the same batch with different content
  2. Conflicting drawer_ids between incoming batch and existing drawers

Inspired by mempalace/mempalace collision_scan.py (upstream v3.4.1).
Pure SQLite. No external deps.

Usage:
    from super_memory.mempalace.collision_scan import assert_no_collisions
    assert_no_collisions(db_path, proposed_batch)
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any


class CollisionError(Exception):
    """Raised when a drawer_id collision is detected."""


def _metadata_key(meta: dict[str, Any]) -> tuple:
    """Reduce drawer metadata to the collision-discrimination key."""
    source_file = meta.get("source_file", "")
    chunk_index = meta.get("chunk_index")
    if chunk_index is not None:
        return (source_file, chunk_index)
    return (source_file,)


def _check_batch_duplicates(
    proposed: list[tuple[str, dict[str, Any]]],
) -> dict[str, set[tuple]]:
    """Scan proposed batch for internal duplicates."""
    incoming: dict[str, set[tuple]] = defaultdict(set)
    for drawer_id, meta in proposed:
        incoming[drawer_id].add(_metadata_key(meta))
    return {did: keys for did, keys in incoming.items() if len(keys) > 1}


def assert_no_collisions(
    db_path: Path | str,
    proposed: list[tuple[str, dict[str, Any]]],
) -> None:
    """Abort via CollisionError if any proposed drawer_id collides.

    Args:
        db_path: Path to SQLite database
        proposed: List of (drawer_id, metadata_dict) tuples about to be inserted.
                  metadata must carry at least 'source_file'; 'chunk_index' used when present.

    Raises:
        CollisionError: When a drawer_id maps to two+ distinct metadata keys
                        in the union of incoming + existing rows.
    """
    if not proposed:
        return

    import sqlite3

    db = Path(db_path)
    if not db.exists():
        # No existing DB — only check batch-internal
        internal = _check_batch_duplicates(proposed)
        if internal:
            raise CollisionError(_format_collisions(internal))
        return

    # Build incoming map
    incoming: dict[str, set[tuple]] = defaultdict(set)
    for drawer_id, meta in proposed:
        incoming[drawer_id].add(_metadata_key(meta))

    # Query existing drawers for any incoming id
    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        incoming_ids = list(incoming.keys())
        placeholders = ",".join("?" for _ in incoming_ids)
        rows = conn.execute(
            f"SELECT id, source_file FROM palace_drawers WHERE id IN ({placeholders})",
            incoming_ids,
        ).fetchall()
        for row in rows:
            meta = {"source_file": row["source_file"] or ""}
            incoming[row["id"]].add(_metadata_key(meta))
    finally:
        conn.close()

    collisions = {did: keys for did, keys in incoming.items() if len(keys) > 1}
    if collisions:
        raise CollisionError(_format_collisions(collisions))


def _format_collisions(collisions: dict[str, set[tuple]]) -> str:
    """Render a CollisionError message."""
    lines = [
        f"Collision scan detected {len(collisions)} "
        f"colliding drawer_id{'s' if len(collisions) != 1 else ''}:",
    ]
    for drawer_id, keys in sorted(collisions.items()):
        lines.append(f"  {drawer_id}:")
        for key in sorted(keys, key=lambda k: tuple(str(p) for p in k)):
            if len(key) == 1:
                lines.append(f"    source_file={key[0]!r}")
            else:
                lines.append(f"    source_file={key[0]!r}, chunk_index={key[1]!r}")
    lines.append(
        "Each colliding drawer_id would cause a silent overwrite. "
        "Fix the upstream chunker/miner to emit distinct keys."
    )
    return "\n".join(lines)


def scan_existing(
    db_path: Path | str,
    wing: str | None = None,
    max_results: int = 100,
) -> dict[str, Any]:
    """Scan existing drawers for potential duplicate (source_file, chunk_index) pairs.

    Returns list of groups where multiple drawers share the same source_file
    but have different content — flagged for review.

    Args:
        db_path: Path to SQLite database
        wing: Optional wing filter
        max_results: Max duplicate groups to return

    Returns:
        Dict with duplicate groups report
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        return {"error": f"Database not found: {db_path}", "duplicates": []}

    conn = sqlite3.connect(str(db), timeout=30)
    conn.row_factory = sqlite3.Row

    try:
        where = "WHERE wing = ?" if wing else ""
        params: list[Any] = [wing] if wing else []

        rows = conn.execute(
            f"SELECT id, wing, source_file, length(content) as content_len, created_at "
            f"FROM palace_drawers {where} ORDER BY source_file, created_at",
            params,
        ).fetchall()

        # Group by source_file
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            sf = row["source_file"] or f"_unknown_{row['id']}"
            by_source[sf].append({
                "id": row["id"],
                "wing": row["wing"] or "",
                "content_len": row["content_len"],
                "created_at": row["created_at"] or "",
            })

        # Find groups with >1 drawer per source_file (potential collision)
        dup_groups: list[dict[str, Any]] = []
        for sf, drawers in by_source.items():
            if len(drawers) > 1:
                dup_groups.append({
                    "source_file": Path(sf).name if "/" in sf else sf,
                    "drawer_count": len(drawers),
                    "drawers": drawers[:5],  # Limit per group
                })

        dup_groups.sort(key=lambda g: g["drawer_count"], reverse=True)

        return {
            "total_drawers": len(rows),
            "unique_source_files": len(by_source),
            "potential_duplicate_groups": len(dup_groups),
            "duplicates": dup_groups[:max_results],
        }

    finally:
        conn.close()
