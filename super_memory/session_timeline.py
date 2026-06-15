"""Session timeline and evolution tools for Honcho events."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any
from .config import load_config


def _decode_meta(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata_json")
    if isinstance(raw, str):
        try:
            row["metadata"] = json.loads(raw or "{}")
        except json.JSONDecodeError:
            row["metadata"] = {"raw": raw}
    return row


class SessionTimelineTools:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.db_path = Path(self.config.workspace_root) / self.config.sqlite_path

    def _rows(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def session_timeline(self, session_id: str, limit: int = 50) -> dict[str, Any]:
        """Return chronological events for one session."""
        rows = self._rows("""
            SELECT id, memory_id, workspace, session_id, observer_peer_id,
                   observed_peer_id, content, source, metadata_json, created_at
            FROM honcho_events WHERE session_id = ?
            ORDER BY created_at ASC LIMIT ?
        """, (session_id, limit))
        events = [_decode_meta(r) for r in rows]
        return {"ok": True, "session_id": session_id, "events": events, "count": len(events)}

    def session_list(self, workspace: str | None = None, limit: int = 50) -> dict[str, Any]:
        """List sessions grouped by event counts."""
        where = "WHERE session_id IS NOT NULL" + (" AND workspace = ?" if workspace else "")
        args = (workspace, limit) if workspace else (limit,)
        rows = self._rows(f"""
            SELECT session_id, workspace, COUNT(*) AS event_count,
                   MIN(created_at) AS first_event, MAX(created_at) AS last_event
            FROM honcho_events {where}
            GROUP BY session_id, workspace ORDER BY last_event DESC LIMIT ?
        """, args)
        return {"ok": True, "workspace": workspace, "sessions": rows, "count": len(rows)}

    def session_evolution(self, peer_id: str = "boss", limit: int = 20) -> dict[str, Any]:
        """Show peer-related conclusions and event activity over sessions."""
        try:
            conclusions = self._rows("""
                SELECT id, about_peer_id AS peer_id, content, confidence, source, created_at
                FROM honcho_conclusions WHERE about_peer_id = ?
                ORDER BY created_at DESC LIMIT ?
            """, (peer_id, limit))
        except Exception:
            conclusions = []  # Table may not exist yet
        sessions = self._rows("""
            SELECT session_id, COUNT(*) AS event_count, MAX(created_at) AS last_event
            FROM honcho_events
            WHERE observed_peer_id = ? OR observer_peer_id = ?
            GROUP BY session_id ORDER BY last_event DESC LIMIT ?
        """, (peer_id, peer_id, limit))
        return {"ok": True, "peer_id": peer_id, "conclusions": conclusions, "sessions": sessions}

    def session_search(self, query: str, session_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Search Honcho events, optionally within a session."""
        like = f"%{query}%"
        if session_id:
            rows = self._rows("""
                SELECT id, session_id, observer_peer_id, observed_peer_id, content, source, metadata_json, created_at
                FROM honcho_events WHERE session_id = ? AND content LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """, (session_id, like, limit))
        else:
            rows = self._rows("""
                SELECT id, session_id, observer_peer_id, observed_peer_id, content, source, metadata_json, created_at
                FROM honcho_events WHERE content LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """, (like, limit))
        return {"ok": True, "query": query, "session_id": session_id, "events": [_decode_meta(r) for r in rows], "count": len(rows)}


SESSION_TIMELINE_TOOLS = [
    {"name": "super_memory_session_timeline", "description": "Timeline of Honcho events for a session", "inputSchema": {"type": "object", "properties": {"session_id": {"type": "string"}, "limit": {"type": "integer", "default": 50}}, "required": ["session_id"]}},
    {"name": "super_memory_session_list", "description": "List Honcho sessions", "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}, "limit": {"type": "integer", "default": 50}}, "required": []}},
    {"name": "super_memory_session_evolution", "description": "Peer evolution across sessions", "inputSchema": {"type": "object", "properties": {"peer_id": {"type": "string", "default": "boss"}, "limit": {"type": "integer", "default": 20}}, "required": []}},
    {"name": "super_memory_session_search", "description": "Search Honcho session events", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "session_id": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, "required": ["query"]}},
]
