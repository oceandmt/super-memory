from __future__ import annotations

import re
from typing import Any

from .db import DBMixin


class ClaimExtractor(DBMixin):
    STOP_SUBJECTS = {"it", "this", "that", "there", "they", "we", "you", "i"}
    PATTERNS = [
        re.compile(r"(?:^|[.;\n])\s*([A-Z][A-Za-z0-9 _./:-]{1,80}?)\s+(is|are|has|have|will|must|should|requires|supports|uses)\s+([^.;\n]{3,180})", re.I),
        re.compile(r"(?:^|[.;\n])\s*([A-Z][A-Za-z0-9 _./:-]{1,80}?)\s+(prefers|expects|needs|wants|rejects|dislikes|avoids)\s+([^.;\n]{3,180})", re.I),
        re.compile(r"(?:decision|decided|rule|preference|blocker):\s*([^.;\n]{6,220})", re.I),
    ]
    NEG = {"not", "no", "never", "without", "avoid", "avoids", "rejects", "dislikes", "cannot", "can't", "disabled", "blocked"}

    def ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS cross_agent_claims (
                id TEXT PRIMARY KEY, subject TEXT, predicate TEXT, object TEXT,
                polarity TEXT, agent_id TEXT, memory_id TEXT, status TEXT DEFAULT 'active',
                resolution TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    def extract_claims_from_memory(self, memory_id: str) -> dict[str, Any]:
        self.ensure_tables()
        with self._conn() as conn:
            row = conn.execute("SELECT id,content,agent_id FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "memory_not_found", "memory_id": memory_id}
            claims = self._extract(row["content"], row["agent_id"], memory_id)
            for c in claims:
                cid = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
                conn.execute("INSERT INTO cross_agent_claims(id,subject,predicate,object,polarity,agent_id,memory_id) VALUES(?,?,?,?,?,?,?)", (cid,c["subject"],c["predicate"],c["object"],c["polarity"],c["agent_id"],c["memory_id"]))
                c["id"] = cid
        return {"ok": True, "memory_id": memory_id, "claims": claims, "count": len(claims)}

    def _extract(self, text: str, agent_id: str | None, memory_id: str) -> list[dict[str, Any]]:
        claims = []
        seen = set()
        for pat in self.PATTERNS:
            for m in pat.finditer(text or ""):
                if len(m.groups()) == 1:
                    subj, pred, obj = "memory", "states", self._clean(m.group(1))
                else:
                    subj = self._clean(m.group(1))
                    pred = m.group(2).lower()
                    obj = self._clean(m.group(3))
                if not self._valid_claim(subj, pred, obj):
                    continue
                words = set((pred + " " + obj.lower()).split())
                pol = "negative" if words & self.NEG or " not " in obj.lower() else "positive"
                key = (subj.lower(), pred, obj.lower()[:80])
                if key in seen:
                    continue
                seen.add(key)
                claims.append({"subject": subj[:120], "predicate": pred, "object": obj[:240], "polarity": pol, "agent_id": agent_id, "memory_id": memory_id})
        return claims[:20]

    def _valid_claim(self, subj: str, pred: str, obj: str) -> bool:
        if not subj or not obj or len(obj) < 3:
            return False
        if subj.lower() in self.STOP_SUBJECTS:
            return False
        if len(subj.split()) > 10 or len(obj.split()) > 35:
            return False
        return True

    def _clean(self, s: str) -> str:
        return re.sub(r"\s+", " ", s.strip(" -:,'\""))

    def find_contradictions(self, topic: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        self.ensure_tables()
        q = f"%{topic}%"
        with self._conn() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM cross_agent_claims WHERE status='active' AND (subject LIKE ? OR object LIKE ?) ORDER BY created_at DESC LIMIT ? OFFSET ?", (q,q,limit*4,offset)).fetchall()]
        pairs = []
        for i, a in enumerate(rows):
            for b in rows[i+1:]:
                if a["subject"].lower() == b["subject"].lower() and a["polarity"] != b["polarity"] and a.get("agent_id") != b.get("agent_id"):
                    pairs.append({"claim_a": a, "claim_b": b})
                    if len(pairs) >= limit:
                        break
            if len(pairs) >= limit:
                break
        return {"ok": True, "topic": topic, "contradictions": pairs, "count": len(pairs)}

    def resolve_contradiction(self, claim_a_id: str, claim_b_id: str, resolution: str) -> dict[str, Any]:
        self.ensure_tables()
        valid = {"supersede_a", "supersede_b", "accept_both", "stale"}
        if resolution not in valid:
            return {"ok": False, "error": "invalid_resolution"}
        with self._conn() as conn:
            if resolution == "supersede_a":
                conn.execute("UPDATE cross_agent_claims SET status='superseded',resolution=? WHERE id=?", (resolution, claim_a_id))
            elif resolution == "supersede_b":
                conn.execute("UPDATE cross_agent_claims SET status='superseded',resolution=? WHERE id=?", (resolution, claim_b_id))
            elif resolution == "stale":
                conn.execute("UPDATE cross_agent_claims SET status='stale',resolution=? WHERE id IN (?,?)", (resolution, claim_a_id, claim_b_id))
            else:
                conn.execute("UPDATE cross_agent_claims SET resolution=? WHERE id IN (?,?)", (resolution, claim_a_id, claim_b_id))
        return {"ok": True, "claim_a_id": claim_a_id, "claim_b_id": claim_b_id, "resolution": resolution}

    def agent_belief_report(self, agent_id: str, topic: str = "", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        self.ensure_tables()
        q = f"%{topic}%"
        with self._conn() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM cross_agent_claims WHERE agent_id=? AND (subject LIKE ? OR object LIKE ?) ORDER BY created_at DESC LIMIT ? OFFSET ?", (agent_id,q,q,limit,offset)).fetchall()]
        return {"ok": True, "agent_id": agent_id, "topic": topic, "claims": rows, "count": len(rows), "limit": limit, "offset": offset}

CLAIM_EXTRACTOR_TOOLS = [
 {"name":"super_memory_extract_claims","description":"Extract subject-predicate-object claims from a memory","inputSchema":{"type":"object","properties":{"memory_id":{"type":"string"}},"required":["memory_id"]}},
 {"name":"super_memory_find_contradictions","description":"Find opposing claims across agents","inputSchema":{"type":"object","properties":{"topic":{"type":"string"},"limit":{"type":"integer","default":20},"offset":{"type":"integer","default":0}},"required":["topic"]}},
 {"name":"super_memory_resolve_contradiction","description":"Resolve a claim contradiction","inputSchema":{"type":"object","properties":{"claim_a_id":{"type":"string"},"claim_b_id":{"type":"string"},"resolution":{"type":"string"}},"required":["claim_a_id","claim_b_id","resolution"]}},
 {"name":"super_memory_agent_belief_report","description":"List claims held by an agent on a topic","inputSchema":{"type":"object","properties":{"agent_id":{"type":"string"},"topic":{"type":"string"},"limit":{"type":"integer","default":100},"offset":{"type":"integer","default":0}},"required":["agent_id"]}}, 
]
