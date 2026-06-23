"""Per-agent isolation (P3) — memory scoping and routing by agent identity.

Ensures that each agent (lucas, alex, max, isol) sees only its own
session/agent-local memories unless explicitly querying shared or
cross-agent scopes.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .models import MemoryScope
from .service import SuperMemoryService
from .storage import SuperMemoryStore


def _now():
    return datetime.now(timezone.utc).isoformat()


def _store(config_path=None):
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    _init_tables(store)
    return store


def _init_tables(store):
    with store.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_isolation_rules (
                agent_id TEXT PRIMARY KEY,
                allowed_scopes_json TEXT NOT NULL DEFAULT '["session","agent-local","shared"]',
                allowed_agents_json TEXT NOT NULL DEFAULT '[]',
                blocked_agents_json TEXT NOT NULL DEFAULT '[]',
                read_others INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
        """)


def set_agent_rules(agent_id, allowed_scopes=None, allowed_agents=None, blocked_agents=None, read_others=None, config_path=None):
    """Set isolation rules for an agent."""
    store = _store(config_path)
    with store.connect() as conn:
        existing = conn.execute("SELECT * FROM agent_isolation_rules WHERE agent_id=?", (agent_id,)).fetchone()
        if existing:
            scopes = allowed_scopes if allowed_scopes is not None else json.loads(existing["allowed_scopes_json"])
            allowed = allowed_agents if allowed_agents is not None else json.loads(existing["allowed_agents_json"])
            blocked = blocked_agents if blocked_agents is not None else json.loads(existing["blocked_agents_json"])
            read_others_val = read_others if read_others is not None else existing["read_others"]
        else:
            scopes = allowed_scopes or ["session", "agent-local", "shared"]
            allowed = allowed_agents or []
            blocked = blocked_agents or []
            read_others_val = read_others if read_others is not None else 0
        conn.execute(
            "INSERT OR REPLACE INTO agent_isolation_rules (agent_id, allowed_scopes_json, allowed_agents_json, blocked_agents_json, read_others, metadata_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_id, json.dumps(scopes), json.dumps(allowed), json.dumps(blocked), 1 if read_others_val else 0, "{}", _now()),
        )
    return {"ok": True, "agent_id": agent_id, "allowed_scopes": scopes, "allowed_agents": allowed, "blocked_agents": blocked}


def get_agent_rules(agent_id, config_path=None):
    """Get isolation rules for an agent."""
    store = _store(config_path)
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM agent_isolation_rules WHERE agent_id=?", (agent_id,)).fetchone()
    if not row:
        return {"ok": True, "agent_id": agent_id, "allowed_scopes": ["session", "agent-local", "shared"], "allowed_agents": [], "blocked_agents": [], "read_others": False, "message": "default rules applied"}
    return {
        "ok": True, "agent_id": agent_id,
        "allowed_scopes": json.loads(row["allowed_scopes_json"]),
        "allowed_agents": json.loads(row["allowed_agents_json"]),
        "blocked_agents": json.loads(row["blocked_agents_json"]),
        "read_others": bool(row["read_others"]),
    }


def filter_memories_by_agent(memories, agent_id, query_scope="session", config_path=None):
    """Filter a list of memory dicts/records by agent isolation rules.

    Args:
        memories: List of dicts with 'scope', 'agent_id' keys
        agent_id: Current querying agent
        query_scope: 'session' | 'agent-local' | 'shared' | 'cross-agent' | 'all'
        config_path: Optional config path

    Returns:
        Filtered list of allowed memories
    """
    rules = get_agent_rules(agent_id, config_path=config_path)
    allowed_scopes = set(rules["allowed_scopes"])
    allowed_agents = set(rules["allowed_agents"])
    blocked_agents = set(rules["blocked_agents"])
    read_others = rules["read_others"]

    filtered = []
    for mem in memories:
        scope = mem.get("scope") or mem.get("scope", "session")
        mem_agent = mem.get("agent_id") or "lucas"

        # Scope check
        if query_scope != "all":
            if query_scope not in allowed_scopes:
                continue
            if scope != query_scope:
                continue

        # If scope is shared, anyone can read
        if scope == MemoryScope.SHARED.value:
            filtered.append(mem)
            continue

        # Own memories always visible
        if mem_agent == agent_id:
            filtered.append(mem)
            continue

        # Cross-agent visibility requires read_others flag
        if not read_others and mem_agent != agent_id:
            continue

        # Blocked agents
        if mem_agent in blocked_agents:
            continue

        # Allowed agents
        if allowed_agents and mem_agent not in allowed_agents:
            continue

        filtered.append(mem)

    return filtered


def isolation_summary(config_path=None):
    """Get summary of all agent isolation rules."""
    store = _store(config_path)
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM agent_isolation_rules").fetchall()
    return {
        "ok": True,
        "agents": [
            {
                "agent_id": r["agent_id"],
                "allowed_scopes": json.loads(r["allowed_scopes_json"]),
                "allowed_agents": json.loads(r["allowed_agents_json"]),
                "blocked_agents": json.loads(r["blocked_agents_json"]),
                "read_others": bool(r["read_others"]),
            }
            for r in rows
        ],
    }


def agent_memory_counts(config_path=None):
    """Count memories per agent scope."""
    store = _store(config_path)
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT agent_id, scope, COUNT(*) as c FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 GROUP BY agent_id, scope ORDER BY c DESC"
        ).fetchall()
    return {
        "ok": True,
        "counts": [{"agent_id": r["agent_id"], "scope": r["scope"], "count": r["c"]} for r in rows],
    }
