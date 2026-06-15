"""Spatial navigator — wing/room/hall query operations.

Supports spatial memory retrieval: list wings, list rooms within a wing,
list drawers within a room, search within a spatial scope.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpatialNavigator:
    """Navigate the palace (wings → rooms → halls → drawers)."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def wings(self) -> list[dict[str, Any]]:
        """List all palace wings with counts."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT wing, COUNT(*) as count
                FROM palace_drawers
                GROUP BY wing
                ORDER BY count DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def rooms(self, wing: str | None = None) -> list[dict[str, Any]]:
        """List rooms, optionally filtered by wing."""
        with self._connect() as conn:
            if wing:
                rows = conn.execute(
                    "SELECT wing, room, COUNT(*) as count FROM palace_drawers WHERE wing = ? GROUP BY wing, room ORDER BY count DESC",
                    (wing,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT wing, room, COUNT(*) as count FROM palace_drawers GROUP BY wing, room ORDER BY count DESC",
                ).fetchall()
        return [dict(r) for r in rows]

    def halls(self, wing: str | None = None, room: str | None = None) -> list[dict[str, Any]]:
        """List halls, optionally filtered by wing/room."""
        with self._connect() as conn:
            if wing and room:
                rows = conn.execute(
                    "SELECT wing, room, hall, COUNT(*) as count FROM palace_drawers WHERE wing = ? AND room = ? GROUP BY wing, room, hall ORDER BY count DESC",
                    (wing, room),
                ).fetchall()
            elif wing:
                rows = conn.execute(
                    "SELECT wing, room, hall, COUNT(*) as count FROM palace_drawers WHERE wing = ? GROUP BY wing, room, hall ORDER BY count DESC",
                    (wing,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT wing, room, hall, COUNT(*) as count FROM palace_drawers GROUP BY wing, room, hall ORDER BY count DESC",
                ).fetchall()
        return [dict(r) for r in rows]

    def drawers(self, wing: str | None = None, room: str | None = None, hall: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List drawers with optional spatial filters."""
        with self._connect() as conn:
            clauses = []
            params: list[str] = []
            if wing:
                clauses.append("wing = ?")
                params.append(wing)
            if room:
                clauses.append("room = ?")
                params.append(room)
            if hall:
                clauses.append("hall = ?")
                params.append(hall)
            where = " AND ".join(clauses) if clauses else "1=1"
            rows = conn.execute(
                f"SELECT * FROM palace_drawers WHERE {where} ORDER BY created_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [{k: dict(r)[k] for k in r.keys()} for r in rows]

    def search(self, query: str, wing: str | None = None, room: str | None = None, hall: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Search drawer content with optional spatial scope."""
        with self._connect() as conn:
            clauses = ["content LIKE ?"]
            params: list[str] = [f"%{query}%"]
            if wing:
                clauses.append("wing = ?")
                params.append(wing)
            if room:
                clauses.append("room = ?")
                params.append(room)
            if hall:
                clauses.append("hall = ?")
                params.append(hall)
            where = " AND ".join(clauses)
            rows = conn.execute(
                f"SELECT * FROM palace_drawers WHERE {where} ORDER BY created_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [{k: dict(r)[k] for k in r.keys()} for r in rows]

    def summary(self) -> dict[str, Any]:
        """Quick spatial overview."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM palace_drawers").fetchone()["c"]
            wings = conn.execute("SELECT COUNT(DISTINCT wing) as c FROM palace_drawers").fetchone()["c"]
            rooms = conn.execute("SELECT COUNT(DISTINCT room) as c FROM palace_drawers").fetchone()["c"]
            halls = conn.execute("SELECT COUNT(DISTINCT hall) as c FROM palace_drawers").fetchone()["c"]
            halls_list = conn.execute(
                "SELECT hall, COUNT(*) as count FROM palace_drawers GROUP BY hall ORDER BY count DESC"
            ).fetchall()
        return {
            "total_drawers": total,
            "total_wings": wings,
            "total_rooms": rooms,
            "total_halls": halls,
            "hall_distribution": [{"hall": r["hall"], "count": r["count"]} for r in halls_list],
        }
