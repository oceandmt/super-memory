"""Auto-capture hooks for Honcho events."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_config
from .sanitize import is_injection_content, sanitize_auto_capture


class CaptureHook:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.db_path = Path(self.config.workspace_root) / self.config.sqlite_path

    def ensure_tables(self) -> None:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS honcho_events (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT,
                    workspace TEXT,
                    session_id TEXT,
                    observer_peer_id TEXT,
                    observed_peer_id TEXT,
                    content TEXT NOT NULL,
                    source TEXT,
                    metadata_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def capture_event(
        self,
        content: str,
        session_id: str | None = None,
        observer_peer_id: str = "agent",
        observed_peer_id: str = "boss",
        workspace: str = "openclaw",
        source: str = "capture_hook",
        memory_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        analyze: bool = False,
    ) -> dict[str, Any]:
        """Insert one Honcho event and optionally run turn analysis."""
        self.ensure_tables()
        metadata = metadata or {}
        # B1: never persist runtime-appended prompt-injection / boilerplate noise.
        if is_injection_content(content):
            return {
                "ok": True,
                "event_id": None,
                "session_id": session_id,
                "captured": False,
                "skipped": "injection_content",
            }
        content = sanitize_auto_capture(content)
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            event_id = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
            # Standalone Honcho captures are not layer projections. Keep memory_id
            # NULL unless the caller explicitly links this event to a canonical
            # memory row; otherwise cross-layer health will treat successful
            # captures as false orphan projections.
            created_at = datetime.now(timezone.utc).isoformat()
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("""
                INSERT INTO honcho_events
                (id, memory_id, workspace, session_id, observer_peer_id, observed_peer_id,
                 content, source, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, memory_id, workspace, session_id, observer_peer_id,
                  observed_peer_id, content, source, json.dumps(metadata), created_at))
        result: dict[str, Any] = {"ok": True, "event_id": event_id, "session_id": session_id, "captured": True}
        if analyze:
            result["analysis"] = self.analyze_turn(content, observed_peer_id, session_id)
        return result

    def analyze_turn(self, content: str, peer_id: str = "boss", session_id: str | None = None) -> dict[str, Any]:
        """Lightweight analysis fallback for captured content."""
        signals = []
        lowered = content.lower()
        for key in ("remember", "prefer", "todo", "decision", "blocked", "important"):
            if key in lowered:
                signals.append(key)
        return {"ok": True, "peer_id": peer_id, "session_id": session_id, "signals": signals, "summary": content[:240]}

    def capture_turn(
        self,
        user_message: str,
        assistant_message: str = "",
        session_id: str | None = None,
        observer_peer_id: str = "agent",
        observed_peer_id: str = "boss",
        analyze: bool = True,
    ) -> dict[str, Any]:
        """Capture a user/assistant turn as one event."""
        content = user_message if not assistant_message else f"User: {user_message}\nAssistant: {assistant_message}"
        return self.capture_event(
            content=content,
            session_id=session_id,
            observer_peer_id=observer_peer_id,
            observed_peer_id=observed_peer_id,
            source="capture_turn",
            metadata={"has_assistant": bool(assistant_message)},
            analyze=analyze,
        )


CAPTURE_HOOK_TOOLS = [
    {"name": "super_memory_capture_event", "description": "Capture a Honcho event", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "session_id": {"type": "string"}, "observer_peer_id": {"type": "string", "default": "agent"}, "observed_peer_id": {"type": "string", "default": "boss"}, "workspace": {"type": "string", "default": "openclaw"}, "source": {"type": "string", "default": "capture_hook"}, "metadata": {"type": "object"}, "analyze": {"type": "boolean", "default": False}}, "required": ["content"]}},
    {"name": "super_memory_capture_turn", "description": "Capture a user/assistant turn", "inputSchema": {"type": "object", "properties": {"user_message": {"type": "string"}, "assistant_message": {"type": "string"}, "session_id": {"type": "string"}, "observer_peer_id": {"type": "string", "default": "agent"}, "observed_peer_id": {"type": "string", "default": "boss"}, "analyze": {"type": "boolean", "default": True}}, "required": ["user_message"]}},
]
