from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

from .db import DBMixin


def _tokenize(text: str) -> list[str]:
    """Break text into lowercase word tokens, skipping very short words."""
    return [w.lower() for w in text.replace(".", " ").replace(",", " ").replace(";", " ").split() if len(w) > 1]


def _tfidf_score(sentence: str, corpus: list[str], max_df: float = 0.8) -> float:
    """Score a sentence by TF-IDF against a corpus of other sentences.

    Higher score → sentence is more distinctive and representative.
    Falls back to keyword heuristic when corpus is too small.
    """
    tokens = _tokenize(sentence)
    if not tokens or len(corpus) < 3:
        return 0.0
    n_docs = len(corpus)
    tf = Counter(tokens)
    tf_max = max(tf.values()) if tf else 1
    score = 0.0
    for term, count in tf.items():
        df = sum(1 for doc in corpus if term in _tokenize(doc))
        if df / n_docs > max_df:
            continue
        tf_norm = 0.5 + 0.5 * count / tf_max
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        score += tf_norm * idf
    return score / max(len(tokens), 1)


class SessionArchive(DBMixin):

    def ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS session_archives (
                id TEXT PRIMARY KEY, session_id TEXT UNIQUE, agent_id TEXT,
                summary TEXT, event_count INTEGER, key_decisions_json TEXT,
                open_blockers_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    def create_session_summary(self, session_id: str, max_events: int = 50) -> dict[str, Any]:
        self.ensure_tables()
        with self._conn() as conn:
            events = [dict(r) for r in conn.execute("SELECT * FROM honcho_events WHERE session_id=? ORDER BY created_at DESC LIMIT ?", (session_id,max_events)).fetchall()]
            mems = [dict(r) for r in conn.execute("SELECT * FROM memories WHERE session_id=? ORDER BY created_at DESC LIMIT ?", (session_id,max_events)).fetchall()] if self._has(conn,"memories") else []
            rows = list(reversed(events)) + list(reversed(mems))
            agent = (rows[-1].get("agent_id") or rows[-1].get("observer_peer_id")) if rows else None
            decisions = self._pick_semantic(rows, "decision")
            blockers = self._pick_semantic(rows, "blocker")
            actions = self._pick_semantic(rows, "action")
            prefs = self._pick_semantic(rows, "preference")
            summary = self._summary(decisions, actions, prefs, blockers)
            aid = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
            conn.execute("""INSERT OR REPLACE INTO session_archives
                (id,session_id,agent_id,summary,event_count,key_decisions_json,open_blockers_json)
                VALUES(?,?,?,?,?,?,?)""", (aid,session_id,agent,summary,len(rows),json.dumps(decisions),json.dumps(blockers)))
        return {"ok": True, "session_id": session_id, "summary": summary, "event_count": len(rows), "key_decisions": decisions, "open_blockers": blockers}

    def get_session_summary(self, session_id: str) -> dict[str, Any]:
        self.ensure_tables()
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM session_archives WHERE session_id=?", (session_id,)).fetchone()
        return {"ok": bool(row), "summary": self._decode(dict(row)) if row else None}

    def list_session_summaries(self, agent_id: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        self.ensure_tables(); args=[]
        if agent_id: args.append(agent_id); where = "WHERE agent_id=?"
        else: where = ""
        with self._conn() as conn:
            sql = "SELECT * FROM session_archives " + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            rows = [self._decode(dict(r)) for r in conn.execute(sql, (*args, limit, offset)).fetchall()]
        return {"ok": True, "summaries": rows, "count": len(rows), "limit": limit, "offset": offset}

    def search_session_archives(self, query: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        self.ensure_tables(); q=f"%{query}%"
        with self._conn() as conn:
            rows = [self._decode(dict(r)) for r in conn.execute("SELECT * FROM session_archives WHERE summary LIKE ? OR key_decisions_json LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (q,q,limit,offset)).fetchall()]
        return {"ok": True, "query": query, "results": rows, "count": len(rows), "limit": limit, "offset": offset}

    def session_timeline_view(self, session_id: str, mode: str = "summarized") -> dict[str, Any]:
        self.ensure_tables()
        if mode == "summarized": return self.get_session_summary(session_id)
        with self._conn() as conn:
            events = [dict(r) for r in conn.execute("SELECT id,content,created_at,source FROM honcho_events WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()]
        if mode == "raw": return {"ok": True, "events": events, "count": len(events)}
        terms = ["decision", "decided"] if mode == "decisions" else ["blocker", "blocked", "stuck"]
        filtered = [e for e in events if any(t in (e.get("content") or "").lower() for t in terms)]
        return {"ok": True, "mode": mode, "events": filtered, "count": len(filtered)}

    def _pick(self, rows, terms):
        """Extract relevant content using keyword matching (fast baseline)."""
        out = []
        for r in rows:
            text = r.get("content") or ""
            if any(t in text.lower() for t in terms):
                out.append(text[:240])
            if len(out) >= 10:
                break
        return out

    def _pick_semantic(self, rows, category: str, top_n: int = 5) -> list[str]:
        """Extract most representative sentences by TF-IDF scoring.

        Uses keyword baseline first; if result set is small, supplements
        with high-TF-IDF sentences from the full session corpus.
        """
        keyword_terms = {
            "decision": ["decision", "decided", "chose", "decide", "rule", "agreed"],
            "blocker": ["blocker", "blocked", "stuck", "cannot", "can't", "issue", "problem"],
            "action": ["done", "created", "fixed", "implemented", "updated", "deployed", "built", "added"],
            "preference": ["prefers", "preference", "likes", "wants", "should", "must"],
        }
        terms = keyword_terms.get(category, [category])
        corpus_texts = [(r.get("content") or "") for r in rows]
        non_empty = [t for t in corpus_texts if t.strip()]
        if not non_empty:
            return self._pick(rows, terms)
        keyword_hits = []
        for r in rows:
            text = r.get("content") or ""
            if any(t in text.lower() for t in terms):
                keyword_hits.append(text[:240])
                if len(keyword_hits) >= top_n:
                    return keyword_hits[:top_n]
        scored = []
        for i, text in enumerate(corpus_texts):
            if not text.strip():
                continue
            sentences = [s.strip() for s in text.replace("\n", ". ").replace(".  ", ". ").split(". ") if len(s.strip()) > 10]
            for sent in sentences:
                relevance = sum(1 for t in terms if t in sent.lower())
                tfidf = _tfidf_score(sent, non_empty)
                scored.append((relevance * 0.6 + tfidf * 20.0, sent[:240]))
        scored.sort(reverse=True)
        result = [s[1] for s in scored[:top_n]]
        return result or keyword_hits[:top_n]

    def _summary(self, decisions, actions, prefs, blockers):
        parts = []
        if decisions:
            parts.append("Decisions: " + "; ".join(decisions[:3]))
        if actions:
            parts.append("Actions: " + "; ".join(actions[:3]))
        if prefs:
            parts.append("Preferences: " + "; ".join(prefs[:2]))
        if blockers:
            parts.append("Blockers: " + "; ".join(blockers[:3]))
        return "\n".join(parts) or "No notable decisions, actions, preferences, or blockers captured."

    def _decode(self, row):
        for k in ("key_decisions_json","open_blockers_json"):
            row[k[:-5]] = json.loads(row.get(k) or "[]")
        return row

SESSION_ARCHIVE_TOOLS = [
 {"name":"super_memory_create_session_summary","description":"Create a compressed session archive","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"},"max_events":{"type":"integer","default":50}},"required":["session_id"]}},
 {"name":"super_memory_get_session_summary","description":"Get one session archive summary","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"}},"required":["session_id"]}},
 {"name":"super_memory_list_session_summaries","description":"List recent session summaries","inputSchema":{"type":"object","properties":{"agent_id":{"type":"string"},"limit":{"type":"integer","default":20},"offset":{"type":"integer","default":0}},"required":[]}},
 {"name":"super_memory_search_session_archives","description":"Search archived session summaries","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":20},"offset":{"type":"integer","default":0}},"required":["query"]}},
 {"name":"super_memory_session_timeline_view","description":"View session as raw, summary, decisions, or blockers","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"},"mode":{"type":"string","default":"summarized"}},"required":["session_id"]}},
]
