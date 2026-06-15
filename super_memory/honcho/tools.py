"""Honcho MCP tool definitions.

Local Honcho-style peer/session/conclusion operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import SuperMemoryConfig
from .peer import PeerFact, PeerModel, PeerRole, PeerStore
from .dialectic import DialecticEngine
from .session import SessionContextBuilder
from .insights import InsightGenerator


class HonchoTools:
    """MCP tool wrapper for local Honcho operations."""

    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.db_path = Path(config.workspace_root) / config.sqlite_path
        self.peer_store = PeerStore(self.db_path)
        self.dialectic = DialecticEngine()
        self.context_builder = SessionContextBuilder(self.db_path)
        self.insights = InsightGenerator(self.db_path)

    def honcho_ask(self, query: str, about_peer: str = "boss", limit: int = 10) -> dict[str, Any]:
        """Ask about a peer using peer model + conclusions + message search."""
        peer = self.peer_store.get(about_peer)
        conclusions = self.insights.search_conclusions(query, about_peer_id=about_peer, limit=limit)
        messages = self.context_builder.search_messages(query, peer_id=about_peer, limit=limit)
        answer_parts: list[str] = []
        if peer:
            answer_parts.append(peer.to_context_block(max_tokens=300))
        if conclusions:
            answer_parts.append("Conclusions:\n" + "\n".join(f"- {c['content']}" for c in conclusions[:5]))
        if messages:
            answer_parts.append("Recent matching events:\n" + "\n".join(f"- {m['content'][:120]}" for m in messages[:5]))
        answer = "\n\n".join(answer_parts) if answer_parts else "No local Honcho evidence found."
        return {"ok": True, "query": query, "about_peer": about_peer, "answer": answer, "sources": {"peer": peer is not None, "conclusions": len(conclusions), "messages": len(messages)}}

    def honcho_context(self, session_id: str | None = None, peer_id: str = "boss", max_tokens: int = 1000) -> dict[str, Any]:
        """Build Honcho-style context block."""
        return {"ok": True, **self.context_builder.build(session_id=session_id, peer_id=peer_id, max_tokens=max_tokens)}

    def honcho_profile(self, peer_id: str = "boss", role: str = "human", facts: list[str] | None = None, merge: bool = True) -> dict[str, Any]:
        """Read or update peer profile."""
        peer = self.peer_store.get(peer_id)
        if peer is None and not facts:
            return {"ok": False, "error": f"Peer not found: {peer_id}", "peer_id": peer_id}
        if peer is None:
            peer = self.peer_store.get_or_create(peer_id, role=PeerRole(role), display_name=peer_id)
        if facts:
            if not merge:
                peer.facts = []
            for fact in facts:
                peer.add_fact(PeerFact(content=fact, type="fact", confidence=0.8, source="honcho_profile"))
            self.peer_store.save(peer)
        return {"ok": True, "peer": peer.to_dict()}

    def honcho_conclude(self, content: str | None = None, about_peer: str = "boss", delete_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Create/list/delete conclusions."""
        if delete_id:
            return {"ok": self.insights.delete_conclusion(delete_id), "deleted_id": delete_id}
        if content:
            conclusion = self.insights.conclude(about_peer, content, confidence=0.75, source="honcho_conclude")
            return {"ok": True, "conclusion": conclusion}
        return {"ok": True, "conclusions": self.insights.list_conclusions(about_peer_id=about_peer, limit=limit)}

    def honcho_search(self, query: str, peer_id: str | None = None, session_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Search Honcho events/messages."""
        messages = self.context_builder.search_messages(query, session_id=session_id, peer_id=peer_id, limit=limit)
        conclusions = self.insights.search_conclusions(query, about_peer_id=peer_id, limit=limit)
        return {"ok": True, "query": query, "messages": messages, "conclusions": conclusions, "count": len(messages) + len(conclusions)}

    def honcho_analyze_turn(self, user_message: str, assistant_message: str = "", peer_id: str = "boss", session_id: str | None = None, depth: int = 2, save: bool = True) -> dict[str, Any]:
        """Run dialectic analysis on a turn and optionally update peer model."""
        peer = self.peer_store.get_or_create(peer_id, role=PeerRole.HUMAN, display_name=peer_id)
        result = self.dialectic.analyze_turn(user_message, assistant_message, peer_model=peer, depth=depth)
        if save:
            peer = self.dialectic.apply_to_peer(peer, result)
            self.peer_store.save(peer)
            for insight in result.insights:
                self.insights.conclude(peer_id, insight, confidence=result.confidence, source="honcho:dialectic")
        return {"ok": True, "peer_id": peer_id, "session_id": session_id, "dialectic": result.to_dict(), "saved": save}

    def honcho_sessions(self, workspace: str = "openclaw", limit: int = 50) -> dict[str, Any]:
        """List sessions with counts."""
        import sqlite3
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, COUNT(*) as count, MAX(created_at) as last_event
                FROM honcho_events
                WHERE workspace = ? AND session_id IS NOT NULL
                GROUP BY session_id
                ORDER BY last_event DESC
                LIMIT ?
                """,
                (workspace, limit),
            ).fetchall()
        return {"ok": True, "workspace": workspace, "sessions": [dict(r) for r in rows]}


HONCHO_TOOLS = [
    {
        "name": "super_memory_honcho_ask",
        "description": "Ask about a peer using local Honcho peer model, conclusions, and messages",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "about_peer": {"type": "string", "default": "boss"}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]},
    },
    {
        "name": "super_memory_honcho_context",
        "description": "Build Honcho-style session context block",
        "inputSchema": {"type": "object", "properties": {"session_id": {"type": "string"}, "peer_id": {"type": "string", "default": "boss"}, "max_tokens": {"type": "integer", "default": 1000}}, "required": []},
    },
    {
        "name": "super_memory_honcho_profile",
        "description": "Read or update local Honcho peer profile",
        "inputSchema": {"type": "object", "properties": {"peer_id": {"type": "string", "default": "boss"}, "role": {"type": "string", "default": "human"}, "facts": {"type": "array", "items": {"type": "string"}}, "merge": {"type": "boolean", "default": True}}, "required": []},
    },
    {
        "name": "super_memory_honcho_conclude",
        "description": "Create/list/delete conclusions about a peer",
        "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "about_peer": {"type": "string", "default": "boss"}, "delete_id": {"type": "string"}, "limit": {"type": "integer", "default": 50}}, "required": []},
    },
    {
        "name": "super_memory_honcho_search",
        "description": "Search local Honcho messages and conclusions",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "peer_id": {"type": "string"}, "session_id": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, "required": ["query"]},
    },
    {
        "name": "super_memory_honcho_analyze_turn",
        "description": "Run dialectic analysis on a turn and optionally update peer model",
        "inputSchema": {"type": "object", "properties": {"user_message": {"type": "string"}, "assistant_message": {"type": "string"}, "peer_id": {"type": "string", "default": "boss"}, "session_id": {"type": "string"}, "depth": {"type": "integer", "minimum": 1, "maximum": 3, "default": 2}, "save": {"type": "boolean", "default": True}}, "required": ["user_message"]},
    },
    {
        "name": "super_memory_honcho_sessions",
        "description": "List Honcho sessions with event counts",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string", "default": "openclaw"}, "limit": {"type": "integer", "default": 50}}, "required": []},
    },
]
