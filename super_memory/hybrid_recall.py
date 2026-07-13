from __future__ import annotations

import math
import re
import time
from typing import Any

from .config import load_config
from .db import DBMixin, validate_agent_scope, validate_session_scope
from .goals import compute_goal_boost, get_goal_manager
from .depth_prior import expected_depth as dp_expected_depth, record_outcome as dp_record_outcome
from .vector import VectorStore, rerank_by_embedding


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

def _query_to_pseudo_vector(query: str, dim: int = 128) -> list[float]:
    """Convert a text query to a pseudo-embedding vector for reranking.

    This is a lightweight deterministic fallback when no LLM embedding
    is available. Uses character n-gram hashing to produce a sparse vector.
    """
    import hashlib
    import math

    query = (query or "").lower().strip()
    if not query:
        return [0.0] * dim

    # Character trigram hashing into vector dimensions
    vec = [0.0] * dim
    for i in range(len(query) - 2):
        trigram = query[i:i + 3]
        h = int(hashlib.md5(trigram.encode()).hexdigest()[:8], 16)
        idx = h % dim
        vec[idx] += 1.0

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


# ── Reciprocal Rank Fusion ──────────────────────────────────────────────────
# RRF combines ranked lists from multiple retrieval backends.
# Each backend contributes 1/(k + rank) to the final score.
# k=60 is the standard default from the original RRF paper.
RRF_K = 60.0

def _rrf_fuse(lists: list[list[dict[str, Any]]], k: float = RRF_K) -> list[dict[str, Any]]:
    """Fuse multiple ranked lists using Reciprocal Rank Fusion.

    Each list must have items with an 'id' field.
    Returns items sorted by RRF score descending.
    """
    scores: dict[str, float] = {}
    items_by_id: dict[str, dict[str, Any]] = {}

    for ranked_list in lists:
        for rank, item in enumerate(ranked_list):
            item_id = item.get("id")
            if not item_id:
                continue
            items_by_id[item_id] = item
            # RRF contribution: 1 / (k + rank)
            # rank is 0-indexed, add 1 for 1-based ranking
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)

    # Sort by RRF score descending
    ranked = sorted(items_by_id.values(), key=lambda x: scores.get(x.get("id", ""), 0), reverse=True)
    return ranked


class HybridRecall(DBMixin):

    def cross_scope_recall(self, query: str, agent_scope: str = "current", session_scope: str = "recent", source_layers: list[str] | None = None, max_tokens: int = 1200, limit: int = 6) -> dict[str, Any]:
        validate_agent_scope(agent_scope)
        validate_session_scope(session_scope)

        # Depth Prior: auto-adjust search depth based on query type
        depth = dp_expected_depth(query, self._store() if hasattr(self, '_store') else None)
        candidate_limit = max(limit * (depth + 2) * 2, 50)

        layers = source_layers or ["all"]
        allowed_layers = {"all", "markdown", "honcho", "mempalace", "graph"}
        if any(layer not in allowed_layers for layer in layers):
            raise ValueError(f"invalid source_layers: {layers}")
        if "all" in layers:
            layers = ["markdown", "honcho", "mempalace", "graph"]
        ranked_lists: list[list[dict[str, Any]]] = []
        with self._conn() as conn:
            if "markdown" in layers and self._has(conn, "memories"):
                ranked_lists.append(self._search_memories(conn, query, agent_scope, session_scope, candidate_limit, "markdown"))
                if self.config.vector_enabled:
                    ranked_lists.append(self._search_semantic_memories(conn, query, agent_scope, session_scope, candidate_limit))
            if "honcho" in layers and self._has(conn, "honcho_events"):
                ranked_lists.append(self._search_honcho(conn, query, agent_scope, session_scope, candidate_limit))
            if "mempalace" in layers and self._has(conn, "palace_drawers"):
                ranked_lists.append(self._search_palace(conn, query, candidate_limit))
            if "graph" in layers and self._has(conn, "memories") and self._has(conn, "cognitive_neurons"):
                ranked_lists.append(self._search_memories(conn, query, agent_scope, session_scope, candidate_limit, "graph", graph=True))

        # RRF fusion: combine all ranked lists using Reciprocal Rank Fusion
        fused = _rrf_fuse(ranked_lists)
        merged = self._dedup(fused)

        # Goal-directed boost: apply bias from active goals
        goal_mgr = get_goal_manager()
        active_goals = goal_mgr.get_active_goals()
        if active_goals:
            for item in merged:
                tags = item.get("tags", item.get("metadata", {}).get("tags", []))
                if isinstance(tags, str):
                    try:
                        import json as _json
                        tags = _json.loads(tags)
                    except Exception:
                        tags = []
                content = item.get("content", "")
                item["_goal_boost"] = goal_mgr.compute_goal_boost(tags, content)
            merged.sort(key=lambda x: x.get("_goal_boost", 1.0), reverse=True)

        # Native sqlite-vec semantic reranking (optional)
        if self.config.vector_enabled:
            try:
                merged = rerank_by_embedding(merged, query, top_k=limit * 2, config=self.config)
            except Exception:
                pass

        return {"ok": True, "query": query, "results": self._truncate(merged[:limit], max_tokens), "count": min(len(merged), limit), "depth_prior": depth}

    def _store(self):
        """Get SuperMemoryStore instance for depth prior."""
        from .storage import SuperMemoryStore
        return SuperMemoryStore(self.config)

    def _search_semantic_memories(self, conn, query, agent_scope, session_scope, limit):
        """Search memories through sqlite-vec semantic index, then hydrate rows."""
        store = VectorStore(self.config)
        if not store.available:
            return []
        semantic = store.search_text(query, top_k=limit)
        if not semantic:
            return []
        agent_kind, agent = validate_agent_scope(agent_scope)
        session_kind, sid = validate_session_scope(session_scope)
        out = []
        for memory_id, score in semantic:
            where = ["id=?", "layer=?"]
            args = [memory_id, "workspace_markdown"]
            if agent_kind == "agent":
                where.append("agent_id=?")
                args.append(agent)
            elif agent_kind == "shared":
                where.append("scope=?")
                args.append("shared")
            if session_kind == "session":
                where.append("session_id=?")
                args.append(sid)
            row = conn.execute(
                "SELECT id, content, agent_id, session_id, created_at, type FROM memories WHERE " + " AND ".join(where),
                args,
            ).fetchone()
            if row:
                item = self._result(dict(row), "semantic")
                item["semantic_score"] = score
                out.append(item)
        return out

    def _search_memories(self, conn, query, agent_scope, session_scope, limit, layer, graph=False):
        import sqlite3 as _sqlite3
        agent_kind, agent = validate_agent_scope(agent_scope)
        session_kind, sid = validate_session_scope(session_scope)

        # Build filter clauses for base-table join
        where: list[str] = []
        args: list = []
        if agent_kind == "agent":
            where.append("m.agent_id=?")
            args.append(agent)
        elif agent_kind == "shared":
            where.append("m.scope=?")
            args.append("shared")
        if session_kind == "session":
            where.append("m.session_id=?")
            args.append(sid)
        if layer == "markdown":
            where.append("m.layer=?")
            args.append("workspace_markdown")
        elif graph:
            # P4#1: V2 path — when legacy_graph_edges is False, skip graph_edges UNION
            cfg = getattr(self, 'config', load_config())
            if getattr(cfg, 'legacy_graph_edges', True):
                where.append(
                    "m.id IN (SELECT source_memory_id FROM cognitive_neurons "
                    "WHERE source_memory_id IS NOT NULL "
                    "UNION SELECT source_memory_id FROM graph_edges "
                    "UNION SELECT target_memory_id FROM graph_edges)"
                )
            else:
                where.append(
                    "m.id IN (SELECT source_memory_id FROM cognitive_neurons "
                    "WHERE source_memory_id IS NOT NULL)"
                )
        filter_sql = (" AND " + " AND ".join(where)) if where else ""

        # Try FTS5 MATCH first; fall back to LIKE on OperationalError
        fts_query = query.replace('"', ' ').strip()
        rows = None
        if fts_query:
            try:
                fts_sql = (
                    "SELECT m.id, m.content, m.agent_id, m.session_id, m.created_at, m.type "
                    "FROM memories_fts f "
                    "JOIN memories m ON m.rowid = f.rowid "
                    "WHERE memories_fts MATCH ? " + filter_sql + " LIMIT ?"
                )
                rows = conn.execute(fts_sql, (fts_query, *args, limit)).fetchall()
            except _sqlite3.OperationalError:
                rows = None  # FTS5 unavailable or table mismatch — use LIKE fallback

        if rows is None:
            like_where = ["content LIKE ?"] + [w.replace("m.", "", 1) for w in where]
            like_sql = (
                "SELECT id, content, agent_id, session_id, created_at, type "
                "FROM memories WHERE " + " AND ".join(like_where) + " ORDER BY created_at DESC LIMIT ?"
            )
            rows = conn.execute(like_sql, (f"%{query}%", *args, limit)).fetchall()

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
        # E4: unified dedup key — content_hash first (canonical, matches
        # service.prefetch), then 12-word content prefix as fallback. This keeps
        # both recall paths deduping identically instead of diverging.
        out = []
        seen = set()
        for r in rows:
            meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
            key = r.get("content_hash") or meta.get("content_hash")
            if not key:
                key = " ".join((r.get("content") or "").lower().split()[:12])
            if key and key not in seen:
                seen.add(key)
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
