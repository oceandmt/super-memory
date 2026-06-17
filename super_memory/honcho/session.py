"""Session context assembly — Honcho-style context builder.

Combines peer model, recent events, session summary into compact context.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .peer import PeerStore


class SessionContextBuilder:
    """Build session-scoped context blocks for prompt injection."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.peer_store = PeerStore(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def recent_events(self, session_id: str | None = None, peer_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch recent Honcho events by session/peer."""
        clauses: list[str] = []
        params: list[str] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if peer_id:
            clauses.append("(observer_peer_id = ? OR observed_peer_id = ?)")
            params.extend([peer_id, peer_id])
        where = " AND ".join(clauses) if clauses else "1=1"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM honcho_events WHERE {where} ORDER BY created_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [dict(r) for r in rows]

    def session_summary(self, session_id: str, max_events: int = 20) -> str:
        """Deterministic session summary from recent events."""
        events = self.recent_events(session_id=session_id, limit=max_events)
        if not events:
            return "No recent session events."
        topics: dict[str, int] = {}
        for e in events:
            text = e["content"].lower()
            for topic in ["super-memory", "mempalace", "honcho", "deploy", "test", "vps", "plugin", "memory"]:
                if topic in text:
                    topics[topic] = topics.get(topic, 0) + 1
        top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]
        topic_text = ", ".join(t for t, _ in top_topics) or "general"
        return f"Session has {len(events)} recent events. Main topics: {topic_text}."

    def build(
        self,
        session_id: str | None = None,
        peer_id: str = "boss",
        max_tokens: int = 1000,
        include_events: bool = True,
    ) -> dict[str, Any]:
        """Build Honcho-style context: peer card + session summary + recent events."""
        peer_model = self.peer_store.get(peer_id)
        lines: list[str] = []
        lines.append("# Honcho Session Context")
        
        if peer_model:
            lines.append("\n## Peer Model")
            lines.append(peer_model.to_context_block(max_tokens=400))
        else:
            lines.append(f"\n## Peer Model\nPeer {peer_id} has no stored model yet.")
        
        if session_id:
            lines.append("\n## Session Summary")
            lines.append(self.session_summary(session_id))
        
        if include_events:
            events = self.recent_events(session_id=session_id, peer_id=peer_id, limit=5)
            if events:
                lines.append("\n## Recent Events")
                for e in events:
                    content = e["content"][:120].replace("\n", " ")
                    lines.append(f"- [{e['created_at']}] {content}")
        
        text = "\n".join(lines)
        words = text.split()
        if len(words) > max_tokens:
            text = " ".join(words[:max_tokens]) + " ..."
        
        return {
            "context_text": text,
            "estimated_tokens": int(len(text.split()) * 1.3),
            "peer_id": peer_id,
            "session_id": session_id,
            "has_peer_model": peer_model is not None,
        }

    def search_messages(self, query: str, session_id: str | None = None, peer_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Search Honcho events by content."""
        clauses = ["content LIKE ?"]
        params: list[str] = [f"%{query}%"]
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if peer_id:
            clauses.append("(observer_peer_id = ? OR observed_peer_id = ?)")
            params.extend([peer_id, peer_id])
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM honcho_events WHERE {where} ORDER BY created_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [dict(r) for r in rows]
