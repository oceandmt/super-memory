from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any
from .capture_hook import CaptureHook
from .handoff import HandoffTools
from .db import DBMixin

@dataclass
class TurnContext:
    user_message: str = ""
    assistant_message: str = ""
    agent_id: str = "lucas"
    session_id: str | None = None
    project: str | None = None
    metadata: dict[str, Any] | None = None


class HookManager(DBMixin):

    def ensure_tables(self) -> None:
        CaptureHook(self.config).ensure_tables()
        HandoffTools(self.config).ensure_tables()
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, agent_id TEXT, peer_id TEXT, status TEXT,
                current_project TEXT, current_goal TEXT, started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    def post_turn_capture(self, user_message: str, assistant_message: str, session_id: str, agent_id: str, workspace: str) -> dict[str, Any]:
        self.ensure_tables()
        hook = CaptureHook(self.config)
        meta = {"kind": "turn", "agent_id": agent_id}
        user = hook.capture_event(user_message, session_id, agent_id, "boss", workspace, "post_turn_user", metadata=meta)
        assistant = hook.capture_event(assistant_message, session_id, agent_id, agent_id, workspace, "post_turn_assistant", metadata=meta)
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO sessions(id,agent_id,peer_id,status) VALUES(?,?,?,?)", (session_id, agent_id, "boss", "active"))
            conn.execute("UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))
        return {"ok": True, "events": [user, assistant]}

    def session_start_context(self, session_id: str, agent_id: str, peer_id: str, max_tokens: int = 800) -> dict[str, Any]:
        self.ensure_tables()
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO sessions(id,agent_id,peer_id,status) VALUES(?,?,?,?)", (session_id, agent_id, peer_id, "active"))
            conclusions = [dict(r) for r in conn.execute("SELECT * FROM honcho_conclusions WHERE about_peer_id=? ORDER BY created_at DESC LIMIT 5", (peer_id,)).fetchall()] if self._has(conn,"honcho_conclusions") else []
            decisions = [dict(r) for r in conn.execute("SELECT id,content,created_at FROM memories WHERE agent_id=? AND (type='decision' OR content LIKE '%decision%') ORDER BY created_at DESC LIMIT 5", (agent_id,)).fetchall()] if self._has(conn,"memories") else []
            blockers = [dict(r) for r in conn.execute("SELECT id,content,created_at FROM memories WHERE agent_id=? AND (type='blocker' OR content LIKE '%blocker%') ORDER BY created_at DESC LIMIT 10", (agent_id,)).fetchall()] if self._has(conn,"memories") else []
            session = dict(conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())
        text = json.dumps({"conclusions": conclusions, "decisions": decisions, "blockers": blockers, "session": session}, ensure_ascii=False)
        return {"ok": True, "context": text[:max_tokens], "session": session}

    def session_end_summary(self, session_id: str, agent_id: str) -> dict[str, Any]:
        self.ensure_tables()
        with self._conn() as conn:
            events = [dict(r) for r in conn.execute("SELECT * FROM honcho_events WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()]
            content = "\n".join(e.get("content") or "" for e in events)
            decisions = [x.strip() for x in content.split("\n") if "decision" in x.lower()][:10]
            blockers = [x.strip() for x in content.split("\n") if "block" in x.lower()][:10]
            conn.execute("UPDATE sessions SET status='ended', ended_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))
        return {"ok": True, "session_id": session_id, "event_count": len(events), "key_decisions": decisions, "open_blockers": blockers}

    def delegation_handoff(self, from_agent: str, to_agent: str, objective: str, constraints: dict[str, Any] | str | None, session_id: str) -> dict[str, Any]:
        context = {"objective": objective, "constraints": constraints or {}}
        return HandoffTools(self.config).create_handoff(from_agent, to_agent, f"Handoff: {objective[:60]}", objective, session_id, objective, 10, context)

HOOKS_TOOLS = [
 {"name":"super_memory_post_turn_capture","description":"Capture a completed turn into Honcho events","inputSchema":{"type":"object","properties":{"user_message":{"type":"string"},"assistant_message":{"type":"string"},"session_id":{"type":"string"},"agent_id":{"type":"string"},"workspace":{"type":"string"}},"required":["user_message","assistant_message","session_id","agent_id","workspace"]}},
 {"name":"super_memory_session_start_context","description":"Load bounded startup context","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"},"agent_id":{"type":"string"},"peer_id":{"type":"string"},"max_tokens":{"type":"integer","default":800}},"required":["session_id","agent_id","peer_id"]}},
 {"name":"super_memory_session_end_summary","description":"Summarize and close a session","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"},"agent_id":{"type":"string"}},"required":["session_id","agent_id"]}},
 {"name":"super_memory_delegation_handoff","description":"Create a delegation handoff bundle","inputSchema":{"type":"object","properties":{"from_agent":{"type":"string"},"to_agent":{"type":"string"},"objective":{"type":"string"},"constraints":{"type":"object"},"session_id":{"type":"string"}},"required":["from_agent","to_agent","objective","session_id"]}},
]
