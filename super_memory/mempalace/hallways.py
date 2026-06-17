"""Hallways — entity-to-entity connectors within a wing.

A hallway connects two entities that co-occur across drawers in the same wing.
Materialized as SQLite table: hallways(wing, entity_a, entity_b, strength).

Built from drawer entity extractions. Used to discover which concepts/people
are related within a project domain.

Usage:
    from super_memory.mempalace.hallways import build_hallways, list_hallways
    build_hallways(db_path, wing="my_project")
    result = list_hallways(db_path, wing="my_project")
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")  # Capitalized tokens as entity proxies


def _extract_entity_mentions(text: str) -> set[str]:
    """Extract capitalized proper-noun-like tokens from text."""
    if not text:
        return set()
    return set(m.group(0) for m in _TOKEN_RE.finditer(text))


def _ensure_tables(conn) -> None:
    """Create hallways table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS palace_hallways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wing TEXT NOT NULL,
            entity_a TEXT NOT NULL,
            entity_b TEXT NOT NULL,
            strength REAL NOT NULL DEFAULT 0.0,
            co_occurrences INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(wing, entity_a, entity_b)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hallways_wing ON palace_hallways(wing)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hallways_entity ON palace_hallways(entity_a, entity_b)
    """)


def build_hallways(
    db_path: Path | str,
    wing: str | None = None,
    min_strength: float = 0.02,
    max_entities_per_drawer: int = 20,
) -> dict[str, Any]:
    """Build/rebuild hallways from drawer entity co-occurrence.

    For each drawer, extract capitalized tokens as entity proxies,
    count co-occurrence pairs across all drawers in the wing,
    and materialize as hallway records.

    Args:
        db_path: Path to SQLite database
        wing: Optional wing filter (builds for all wings if None)
        min_strength: Minimum co-occurrence strength to store
        max_entities_per_drawer: Cap entities per drawer to bound computation

    Returns:
        Dict with stats about hallways built
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        return {"error": f"Database not found: {db_path}"}

    conn = sqlite3.connect(str(db), timeout=30)
    conn.row_factory = sqlite3.Row

    try:
        _ensure_tables(conn)

        # Fetch drawers
        params: list[Any] = []
        if wing:
            rows = conn.execute(
                "SELECT id, wing, content FROM palace_drawers WHERE wing = ?",
                (wing,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, wing, content FROM palace_drawers",
            ).fetchall()

        # Build per-wing co-occurrence counters
        wing_cooccur: dict[str, Counter] = {}

        for row in rows:
            w = row["wing"] or "default"
            entities = _extract_entity_mentions(row["content"] or "")
            if not entities or len(entities) > max_entities_per_drawer:
                continue

            entity_list = sorted(entities)
            if w not in wing_cooccur:
                wing_cooccur[w] = Counter()

            for i in range(len(entity_list)):
                for j in range(i + 1, len(entity_list)):
                    pair = (entity_list[i], entity_list[j])
                    wing_cooccur[w][pair] += 1

        # Clear old hallways and insert new
        total_inserted = 0
        for w, counter in wing_cooccur.items():
            if wing and w != wing:
                continue

            conn.execute("DELETE FROM palace_hallways WHERE wing = ?", (w,))

            for (a, b), count in counter.items():
                if count < 2:  # At least 2 co-occurrences
                    continue
                # Strength: relative frequency in this wing
                max_count = max(counter.values()) if counter else 1
                strength = count / max_count

                if strength >= min_strength:
                    conn.execute(
                        """INSERT OR REPLACE INTO palace_hallways 
                           (wing, entity_a, entity_b, strength, co_occurrences)
                           VALUES (?, ?, ?, ?, ?)""",
                        (w, a, b, round(strength, 4), count),
                    )
                    total_inserted += 1

        conn.commit()

        return {
            "wings_processed": len(wing_cooccur),
            "hallways_created": total_inserted,
            "min_strength": min_strength,
        }

    finally:
        conn.close()


def list_hallways(
    db_path: Path | str,
    wing: str | None = None,
    entity: str | None = None,
    min_strength: float = 0.0,
    limit: int = 50,
) -> dict[str, Any]:
    """List hallways with optional filters.

    Args:
        db_path: Path to SQLite database
        wing: Filter by wing
        entity: Filter hallways connected to this entity
        min_strength: Minimum connection strength
        limit: Max results

    Returns:
        Dict with hallways list
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        return {"error": f"Database not found: {db_path}", "hallways": []}

    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row

    try:
        where_parts: list[str] = []
        params: list[Any] = []

        if wing:
            where_parts.append("wing = ?")
            params.append(wing)
        if entity:
            where_parts.append("(entity_a = ? OR entity_b = ?)")
            params.extend([entity, entity])
        if min_strength > 0:
            where_parts.append("strength >= ?")
            params.append(min_strength)

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"

        rows = conn.execute(
            f"SELECT wing, entity_a, entity_b, strength, co_occurrences "
            f"FROM palace_hallways WHERE {where_clause} "
            f"ORDER BY strength DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        return {
            "hallways": [
                {
                    "wing": row["wing"],
                    "entity_a": row["entity_a"],
                    "entity_b": row["entity_b"],
                    "strength": row["strength"],
                    "co_occurrences": row["co_occurrences"],
                }
                for row in rows
            ],
            "count": len(rows),
            "filters": {"wing": wing, "entity": entity, "min_strength": min_strength},
        }

    finally:
        conn.close()


def find_path(
    db_path: Path | str,
    entity_a: str,
    entity_b: str,
    wing: str | None = None,
    max_hops: int = 4,
) -> dict[str, Any]:
    """Find a connection path between two entities through hallways.

    BFS traversal through hallway graph. Returns shortest path if found.
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        return {"error": f"Database not found: {db_path}"}

    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row

    try:
        # Load all hallways for the wing
        if wing:
            rows = conn.execute(
                "SELECT entity_a, entity_b, strength FROM palace_hallways WHERE wing = ?",
                (wing,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT entity_a, entity_b, strength FROM palace_hallways",
            ).fetchall()

        if not rows:
            return {"path": [], "found": False, "hops": 0}

        # Build adjacency list
        graph: dict[str, list[tuple[str, float]]] = {}
        for row in rows:
            a, b, s = row["entity_a"], row["entity_b"], row["strength"]
            graph.setdefault(a, []).append((b, s))
            graph.setdefault(b, []).append((a, s))

        if entity_a not in graph or entity_b not in graph:
            return {"path": [], "found": False, "hops": 0, "reason": "One or both entities not in graph"}

        # BFS
        from collections import deque
        visited: dict[str, tuple[str | None, float, int]] = {entity_a: (None, 1.0, 0)}
        queue: deque = deque([entity_a])

        while queue:
            current = queue.popleft()
            if current == entity_b:
                # Reconstruct path
                path: list[dict[str, Any]] = []
                node = entity_b
                while node is not None:
                    prev, strength, depth = visited[node]
                    if prev is not None:
                        path.append({"from": prev, "to": node, "strength": round(strength, 3)})
                    node = prev
                path.reverse()
                return {"path": path, "found": True, "hops": len(path)}

            current_depth = visited[current][2]
            if current_depth >= max_hops:
                continue

            for neighbor, strength in graph.get(current, []):
                if neighbor not in visited:
                    visited[neighbor] = (current, strength, current_depth + 1)
                    queue.append(neighbor)

        return {"path": [], "found": False, "hops": 0, "reason": f"No path within {max_hops} hops"}

    finally:
        conn.close()
