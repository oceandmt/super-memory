from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .models import MemoryRecord
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory

_DURABLE = {"decision", "workflow", "preference", "lesson", "doctrine", "fact"}
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on",
         "is", "are", "was", "were", "be", "by", "as", "this", "that", "memory", "super"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) > 2 and t not in _STOP}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _boosted_score(query: str, rec: MemoryRecord, rank_base: float = 0.5) -> dict[str, Any]:
    q = _tokens(query)
    c = _tokens(rec.content)
    tags = set(rec.normalized_tags())
    overlap = len(q & c) / max(1, len(q))
    jacc = len(q & c) / max(1, len(q | c)) if q or c else 0.0
    trust = rec.trust_score if rec.trust_score is not None else 0.5

    durable = 0.15 if rec.type.value in _DURABLE else 0.0
    project = 0.10 if rec.project else 0.0
    pinned = 0.15 if ({"pinned", "durable", "reflex"} & tags or rec.metadata.get("pinned")) else 0.0
    exact = 0.20 if query.lower() in rec.content.lower() else 0.0

    score = min(1.0, 0.45 * overlap + 0.20 * jacc + 0.15 * trust + durable + project + pinned + exact + 0.05 * rank_base)
    return {
        "score": round(score, 4),
        "overlap": round(overlap, 4),
        "jaccard": round(jacc, 4),
        "trust": trust,
        "boosts": {"durable": durable, "project": project, "pinned": pinned, "exact": exact},
    }


def verify(query: str = "semantic recall smoke test", limit: int = 5, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    rows = []
    for layer, records in svc.recall(query, limit=max(limit * 4, 20)).items():
        for idx, rec in enumerate(records):
            rows.append({
                "id": rec.id,
                "layer": layer.value,
                "type": rec.type.value,
                "project": rec.project,
                "content": rec.content[:240],
                **_boosted_score(query, rec, 1.0 - idx * 0.05),
            })
    rows.sort(key=lambda r: r["score"], reverse=True)
    noisy = [r for r in rows[:limit] if r["overlap"] == 0 and r["score"] < 0.45]
    return {
        "ok": len(noisy) == 0,
        "query": query,
        "results": rows[:limit],
        "noisy_top_results": noisy,
        "scoring": "lexical overlap + durable/trust/project/pinned boosts",
    }


def quality_audit(config_path: str | None = None) -> dict[str, Any]:
    probes = [
        "OpenClaw memory slot contract",
        "semantic quality audit",
        "canonical first workspace markdown",
        "short term reviewed deferred state",
        "durable memory pack",
    ]
    reports = [verify(p, 5, config_path) for p in probes]
    noisy = sum(len(r["noisy_top_results"]) for r in reports)
    return {"ok": noisy == 0, "probes": len(probes), "noisy_top_results": noisy, "reports": reports}


def index(rebuild: bool = False, batch_size: int = 8, limit: int | None = None, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    SuperMemoryService(cfg)
    lim = limit or 500
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_index (
                memory_id TEXT, layer TEXT,
                tokens_json TEXT NOT NULL, durable INTEGER DEFAULT 0,
                trust REAL, project TEXT, updated_at TEXT NOT NULL,
                PRIMARY KEY(memory_id, layer)
            )
            """
        )
        if rebuild:
            conn.execute("DELETE FROM semantic_index")
        rows = conn.execute(
            "SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT ?",
            (lim,),
        ).fetchall()
        n = 0
        for row in rows:
            rec = row_to_memory(row)
            tags = rec.normalized_tags()
            durable = 1 if rec.type.value in _DURABLE or "durable" in tags or "pinned" in tags else 0
            conn.execute(
                "INSERT OR REPLACE INTO semantic_index(memory_id,layer,tokens_json,durable,trust,project,updated_at) VALUES(?,?,?,?,?,?,?)",
                (rec.id, row["layer"], json.dumps(sorted(_tokens(rec.content))),
                 durable, rec.trust_score, rec.project, _now()),
            )
            n += 1
    return {"ok": True, "indexed": n, "rebuild": rebuild, "mode": "sqlite semantic-lite"}
