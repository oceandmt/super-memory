from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .models import MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory


def _now():
    return datetime.now(timezone.utc).isoformat()


def _cluster_key(content: str) -> str:
    toks = [t for t in re.split(r"\W+", content.lower()) if len(t) > 4][:8]
    return hashlib.sha1(" ".join(toks).encode()).hexdigest()[:16]


def _init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS short_term_reviews (
            cluster_key TEXT PRIMARY KEY,
            decision TEXT NOT NULL,
            note TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )


def _reviewed(conn) -> dict[str, str]:
    _init(conn)
    return {r["cluster_key"]: r["decision"] for r in conn.execute(
        "SELECT cluster_key, decision FROM short_term_reviews"
    ).fetchall()}


def audit(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    SuperMemoryService(cfg)
    clusters = {}
    with store.connect() as conn:
        decisions = _reviewed(conn)
        rows = conn.execute(
            "SELECT * FROM memories WHERE type IN ('event','context') AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    for row in rows:
        rec = row_to_memory(row)
        key = _cluster_key(rec.content)
        if key in decisions:
            continue
        item = clusters.setdefault(key, {
            "cluster_key": key, "count": 0, "memory_ids": [],
            "sample": rec.content[:240], "layers": set(),
            "reason": "repeated short-term event/context",
        })
        item["count"] += 1
        item["memory_ids"].append(rec.id)
        item["layers"].add(row["layer"])
    cands = []
    for item in clusters.values():
        if item["count"] >= 2 or len(item["sample"]) > 800:
            item["layers"] = sorted(item["layers"])
            cands.append(item)
    cands.sort(key=lambda x: (x["count"], len(x["sample"])), reverse=True)
    return {
        "ok": True,
        "candidates": cands[:50],
        "reviewed_suppressed": len(decisions),
        "persistence": "short_term_reviews",
    }


def mark_reviewed(cluster_key: str, decision: str = "deferred", config_path: str | None = None) -> dict[str, Any]:
    if decision not in {"reviewed", "promoted", "deferred", "ignored"}:
        decision = "deferred"
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    SuperMemoryService(cfg)
    with store.connect() as conn:
        _init(conn)
        conn.execute(
            "INSERT OR REPLACE INTO short_term_reviews(cluster_key,decision,note,updated_at) VALUES(?,?,?,?)",
            (cluster_key, decision, "", _now()),
        )
    return {"ok": True, "cluster_key": cluster_key, "decision": decision}


def repair(dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    rep = audit(limit, config_path)
    if dry_run:
        return {"ok": True, "dry_run": True, "would_promote": rep["candidates"][:10]}
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    created = []
    marked = []
    for cand in rep["candidates"][:10]:
        rec = MemoryRecord(
            content=f"Short-term cluster summary ({cand['count']} events): {cand['sample']}",
            type=MemoryType.CONTEXT,
            scope=MemoryScope.SHARED,
            agent_id="maintenance",
            project="super-memory",
            tags=["short-term-promoted", cand["cluster_key"]],
            source="short_term.repair",
            trust_score=0.7,
            metadata={"source_memory_ids": cand["memory_ids"]},
        )
        svc.save(rec)
        created.append(rec.id)
        mark_reviewed(cand["cluster_key"], "promoted", config_path)
        with store.connect() as conn:
            for mid in cand["memory_ids"]:
                esc_rec_id = str(rec.id).replace("'", "''")
                esc_mid = str(mid).replace("'", "''")
                conn.executescript(
                    f"UPDATE memories SET metadata_json=json_set(COALESCE(metadata_json,'{{}}'),'$.compression_candidate',1,'$.short_term_promoted_by','{esc_rec_id}') WHERE id='{esc_mid}';"
                )
                marked.append(mid)
    return {
        "ok": True, "dry_run": False,
        "created": created,
        "marked_compression_candidates": sorted(set(marked)),
    }
