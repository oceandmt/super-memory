"""Insight/conclusion generation for Honcho layer.

Deterministic local substitute for Honcho dialectic conclusions.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class InsightGenerator:
    """Generate and store peer insights/conclusions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS honcho_conclusions (
                    id TEXT PRIMARY KEY,
                    about_peer_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_honcho_conclusions_peer ON honcho_conclusions(about_peer_id)")

    def conclude(self, about_peer_id: str, content: str, confidence: float = 0.7, source: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Store a conclusion/insight about a peer."""
        import hashlib
        cid = hashlib.sha256(f"{about_peer_id}\0{content}".encode("utf-8")).hexdigest()[:16]
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO honcho_conclusions
                (id, about_peer_id, content, confidence, source, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cid, about_peer_id, content, confidence, source, json.dumps(metadata or {}, ensure_ascii=False), now),
            )
        return {"id": cid, "about_peer_id": about_peer_id, "content": content, "confidence": confidence, "created_at": now}

    def list_conclusions(self, about_peer_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List conclusions, optionally filtered by peer."""
        with self._connect() as conn:
            if about_peer_id:
                rows = conn.execute(
                    "SELECT * FROM honcho_conclusions WHERE about_peer_id = ? ORDER BY created_at DESC LIMIT ?",
                    (about_peer_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM honcho_conclusions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_conclusions(self, query: str, about_peer_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Search conclusions by text."""
        clauses = ["content LIKE ?"]
        params: list[Any] = [f"%{query}%"]
        if about_peer_id:
            clauses.append("about_peer_id = ?")
            params.append(about_peer_id)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM honcho_conclusions WHERE {where} ORDER BY confidence DESC, created_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_conclusion(self, conclusion_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM honcho_conclusions WHERE id = ?", (conclusion_id,))
            return cur.rowcount > 0

    def derive_from_events(self, about_peer_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Derive simple insights from recent events."""
        insights: list[dict[str, Any]] = []
        if not events:
            return insights
        combined = "\n".join(e.get("content", "") for e in events).lower()
        signals = {
            "super-memory": "Peer is actively working on Super-Memory architecture and implementation.",
            "phase": "Peer prefers phased implementation planning.",
            "deploy": "Peer expects deploy-and-verify workflow, not just local coding.",
            "heartbeat": "Peer wants interruption-resilient task continuation.",
            "markdown": "Peer values Markdown-first canonical memory design.",
            "test": "Peer expects test or verification evidence before completion.",
        }
        for signal, conclusion in signals.items():
            if signal in combined:
                insights.append(self.conclude(about_peer_id, conclusion, confidence=0.65, source="honcho:derive_from_events"))
        return insights

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
        return d
