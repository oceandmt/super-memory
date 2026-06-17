from __future__ import annotations

import math
import re
import time
from typing import Any

from .db import DBMixin, validate_agent_scope, validate_session_scope


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", (text or "").lower()) if len(t) > 1]

def _tfidf_like(query: str, content: str) -> float:
    q_terms = _tokens(query)
    c_terms = _tokens(content)
    if not q_terms or not c_terms:
        return 0.0
    counts: dict[str, int] = {}
    for t in c_terms:
        counts[t] = counts.get(t, 0) + 1
    total = max(1, len(c_terms))
    score = 0.0
    for term in q_terms:
        if term in counts:
            score += (1 + math.log(1 + counts[term])) / math.sqrt(total)
    coverage = sum(1 for t in set(q_terms) if t in counts) / max(1, len(set(q_terms)))
    phrase_boost = 0.5 if query.lower() in (content or "").lower() else 0.0
    return min(1.0, phrase_boost + coverage * 0.6 + score)

class HybridRecall(DBMixin):

    def cross_scope_recall(self, query: str, agent_scope: str = "current", session_scope: str = "recent", source_layers: list[str] | None = None, max_tokens: int = 2000, limit: int = 10) -> dict[str, Any]:
        validate_agent_scope(agent_scope)
        validate_session_scope(session_scope)
        layers = source_layers or ["all"]
        allowed_layers = {"all", "markdown", "honcho", "mempalace", "graph"}
        if any(layer not in allowed_layers for layer in layers):
            raise ValueError(f"invalid source_layers: {layers}")
        if "all" in layers:
            layers = ["markdown", "honcho", "mempalace", "graph"]
        candidate_limit = max(limit * 5, 50)
        results: list[dict[str, Any]] = []
        with self._conn() as conn:
            if "markdown" in layers and self._has(conn, "memories"):
                results += self._search_memories(conn, query, agent_scope, session_scope, candidate_limit, "markdown")
            if "honcho" in layers and self._has(conn, "honcho_events"):
                results += self._search_honcho(conn, query, agent_scope, session_scope, candidate_limit)
            if "mempalace" in layers and self._has(conn, "palace_drawers"):
                results += self._search_palace(conn, query, candidate_limit)
            if "graph" in layers and self._has(conn, "memories") and self._has(conn, "cognitive_neurons"):
                results += self._search_memories(conn, query, agent_scope, session_scope, candidate_limit, "graph", graph=True)
        merged = self._dedup(results)
        ranked = sorted(merged, key=lambda r: self._score(r, query, agent_scope, session_scope), reverse=True)
        return {"ok": True, "query": query, "results": self._truncate(ranked[:limit], max_tokens), "count": min(len(ranked), limit)}

    def _search_memories(self, conn, query, agent_scope, session_scope, limit, layer, graph=False):
        where, args = ["content LIKE ?"], [f"%{query}%"]
        agent_kind, agent = validate_agent_scope(agent_scope)
        session_kind, sid = validate_session_scope(session_scope)
        if agent_kind == "agent":
            where.append("agent_id=?")
            args.append(agent)
        elif agent_kind == "shared":
            where.append("scope=?")
            args.append("shared")
        if session_kind == "session":
            where.append("session_id=?")
            args.append(sid)
        if graph:
            where.append("id IN (SELECT source_memory_id FROM cognitive_neurons WHERE source_memory_id IS NOT NULL UNION SELECT source_memory_id FROM graph_edges UNION SELECT target_memory_id FROM graph_edges)")
        sql = "SELECT id,content,agent_id,session_id,created_at,type FROM memories WHERE " + " AND ".join(where) + " ORDER BY created_at DESC LIMIT ?"
        rows = conn.execute(sql, (*args, limit)).fetchall()
        return [self._result(dict(r), layer) for r in rows]

    def _search_honcho(self, conn, query, agent_scope, session_scope, limit):
        where, args = ["content LIKE ?"], [f"%{query}%"]
        agent_kind, agent = validate_agent_scope(agent_scope)
        session_kind, sid = validate_session_scope(session_scope)
        if agent_kind == "agent":
            where.append("observer_peer_id=?")
            args.append(agent)
        if session_kind == "session":
            where.append("session_id=?")
            args.append(sid)
        sql = "SELECT id,content,observer_peer_id AS agent_id,session_id,created_at,source AS type FROM honcho_events WHERE " + " AND ".join(where) + " ORDER BY created_at DESC LIMIT ?"
        return [self._result(dict(r), "honcho") for r in conn.execute(sql, (*args, limit)).fetchall()]

    def _search_palace(self, conn, query, limit):
        cols = [c[1] for c in conn.execute("PRAGMA table_info(palace_drawers)").fetchall()]
        content_col = "content" if "content" in cols else "summary" if "summary" in cols else cols[1]
        if content_col not in cols:
            raise ValueError("invalid palace content column")
        sql = "SELECT rowid AS id," + content_col + " AS content,created_at FROM palace_drawers WHERE " + content_col + " LIKE ? LIMIT ?"
        return [self._result(dict(r), "mempalace") for r in conn.execute(sql, (f"%{query}%", limit)).fetchall()]

    def _result(self, row: dict[str, Any], layer: str) -> dict[str, Any]:
        row.setdefault("agent_id", None)
        row.setdefault("session_id", None)
        row.setdefault("created_at", None)
        return {"id": str(row.get("id")), "content": row.get("content") or "", "agent_id": row.get("agent_id"), "session_id": row.get("session_id"), "created_at": row.get("created_at"), "type": row.get("type"), "provenance": {"layer": layer, "id": str(row.get("id"))}}

    def _dedup(self, rows):
        out = []
        prefixes = set()
        for r in rows:
            key = " ".join((r["content"] or "").lower().split()[:12])
            if key and key not in prefixes:
                prefixes.add(key)
                out.append(r)
        return out

    def _score(self, r, query, agent_scope, session_scope):
        scope = 1.0 if agent_scope in ("all","current") or (agent_scope.startswith("agent:") and r.get("agent_id") == agent_scope.split(":",1)[1]) else .4
        sess = 1.0 if not session_scope.startswith("session:") or r.get("session_id") == session_scope.split(":",1)[1] else .5
        exact = 1.0 if query.lower() in (r.get("content") or "").lower() else _tfidf_like(query, r.get("content") or "")
        recency = .5
        try:
            recency = max(.1, 1 - (time.time() - time.mktime(time.strptime((r.get("created_at") or "")[:19], "%Y-%m-%d %H:%M:%S"))) / 2592000)
        except Exception:
            pass
        return ((scope*sess) * 10 + recency * 5 + exact * 3) / 18

    def _truncate(self, rows, max_tokens):
        # Rough token estimate: 1 token ≈ 4 chars for English, 3 for mixed
        # Use len//3.5 as slightly conservative estimate
        chars_per_token = 3.5
        budget = int(max_tokens * chars_per_token)
        out = []
        used = 0
        for r in rows:
            content = r["content"] or ""
            n = len(content)
            if used + n > budget:
                content = content[:max(0, budget - used)]
            out.append({**r, "content": content})
            used += len(content)
            if used >= budget:
                break
        return out

HYBRID_RECALL_TOOLS = [{"name":"super_memory_cross_scope_recall","description":"Hybrid recall across markdown, Honcho, MemPalace, and graph layers","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"agent_scope":{"type":"string","default":"current"},"session_scope":{"type":"string","default":"recent"},"source_layers":{"type":"array","items":{"type":"string"}},"max_tokens":{"type":"integer","default":2000},"limit":{"type":"integer","default":10}},"required":["query"]}}]
