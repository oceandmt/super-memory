from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_config
from .models import MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(config_path: str | None = None) -> SuperMemoryStore:
    return SuperMemoryStore(load_config(config_path))


def embedding_doctor(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    vector_enabled = bool(getattr(cfg, "vector_enabled", False))
    ollama_url = os.environ.get("SUPER_MEMORY_OLLAMA_EMBED_URL", str(getattr(cfg, "embedding_endpoint", "http://127.0.0.1:11434/api/embed")))
    sqlite_vec_available = False
    try:
        import sqlite_vec  # type: ignore  # noqa: F401
        sqlite_vec_available = True
    except Exception:
        sqlite_vec_available = False
    status = {
        "ok": True,
        "semantic_enabled": vector_enabled,
        "sqlite_vec_available": sqlite_vec_available,
        "ollama_embed_url": ollama_url,
        "fts_available": True,
        "recommendation": "sqlite_fts",
        "warnings": [],
    }
    if status["semantic_enabled"] and sqlite_vec_available:
        status["recommendation"] = "sqlite_vec"
    elif status["semantic_enabled"] and not sqlite_vec_available:
        status["warnings"].append("semantic mode requested but sqlite_vec is not importable; falling back to FTS")
    return status


def embedding_auto_select(config_path: str | None = None) -> dict[str, Any]:
    doctor = embedding_doctor(config_path=config_path)
    selected = doctor["recommendation"]
    return {"ok": True, "selected": selected, "doctor": doctor, "reason": "Prefer local sqlite_vec when healthy; otherwise deterministic SQLite FTS fallback."}


def _active_event_rows(store: SuperMemoryStore, limit: int = 500) -> list[Any]:
    with store.connect() as conn:
        return conn.execute(
            """
            SELECT * FROM memories
            WHERE type = 'event'
            AND (json_extract(metadata_json, '$.soft_deleted') IS NULL OR json_extract(metadata_json, '$.soft_deleted') != 1)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def short_term_audit(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    rows = _active_event_rows(store, limit=limit)
    clusters: dict[str, list[MemoryRecord]] = defaultdict(list)
    for row in rows:
        rec = row_to_memory(row)
        key = rec.metadata.get("content_hash") or rec.session_id or rec.content[:120]
        clusters[str(key)].append(rec)
    candidates = []
    for key, records in clusters.items():
        newest = records[0]
        if len(records) > 1 or len(newest.content) > 1000:
            candidates.append({
                "cluster_key": key,
                "count": len(records),
                "representative_id": newest.id,
                "session_id": newest.session_id,
                "chars": len(newest.content),
                "suggested_type": "lesson" if "fix" in newest.content.lower() or "triển khai" in newest.content.lower() else "context",
            })
    return {"ok": True, "checked": len(rows), "candidates": candidates[:100], "candidate_count": len(candidates)}


def _summarize_event(text: str, max_chars: int = 700) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def short_term_repair(limit: int = 500, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    audit = short_term_audit(limit=limit, config_path=config_path)
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    promoted: list[dict[str, Any]] = []
    if dry_run:
        return {"ok": True, "dry_run": True, "would_promote": audit["candidates"][:20], "count": audit["candidate_count"]}
    with svc.store.connect() as conn:
        for cand in audit["candidates"][:20]:
            row = conn.execute("SELECT * FROM memories WHERE id = ? LIMIT 1", (cand["representative_id"],)).fetchone()
            if not row:
                continue
            rec = row_to_memory(row)
            promoted_rec = MemoryRecord(
                content="Short-term promoted summary: " + _summarize_event(rec.content),
                type=MemoryType.LESSON if cand["suggested_type"] == "lesson" else MemoryType.CONTEXT,
                scope=MemoryScope.SHARED if cand["suggested_type"] == "lesson" else MemoryScope.SESSION,
                agent_id=rec.agent_id,
                session_id=rec.session_id,
                project=rec.project,
                source="super-memory.short-term-promotion",
                trust_score=0.75,
                metadata={"promoted_from": rec.id, "promoted_at": _now()},
            )
            svc.save(promoted_rec)
            conn.execute(
                "UPDATE memories SET metadata_json = json_set(metadata_json, '$.promoted_to', ?, '$.compression_candidate', 1, '$.promotion_reviewed_at', ?) WHERE id = ?",
                (promoted_rec.id, _now(), rec.id),
            )
            promoted.append({"from": rec.id, "to": promoted_rec.id})
        conn.commit()
    return {"ok": True, "dry_run": False, "promoted": promoted, "count": len(promoted)}


def dreaming_audit(config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    with store.connect() as conn:
        counts = conn.execute("SELECT type, COUNT(*) AS n FROM memories WHERE json_extract(metadata_json, '$.soft_deleted') IS NULL OR json_extract(metadata_json, '$.soft_deleted') != 1 GROUP BY type").fetchall()
        recent_events = conn.execute("SELECT COUNT(*) AS n FROM memories WHERE type='event' AND (json_extract(metadata_json, '$.compression_candidate') IS NULL OR json_extract(metadata_json, '$.compression_candidate') != 1)").fetchone()
    return {"ok": True, "type_counts": {r["type"]: r["n"] for r in counts}, "uncompressed_events": recent_events["n"] if recent_events else 0}


def dreaming_run(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    rows = _active_event_rows(store, limit=limit)
    by_session = Counter(row_to_memory(r).session_id or "unknown" for r in rows)
    summary = "Dreaming consolidation: recent active event distribution by session: " + ", ".join(f"{k}={v}" for k, v in by_session.most_common(10))
    artifact = {
        "created_at": _now(),
        "summary": summary,
        "event_count": len(rows),
        "top_sessions": by_session.most_common(10),
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": artifact}
    cfg = load_config(config_path)
    dreams_dir = Path(cfg.workspace_root) / "memory" / "dreams"
    dreams_dir.mkdir(parents=True, exist_ok=True)
    path = dreams_dir / (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    svc = SuperMemoryService(cfg)
    rec = MemoryRecord(content=summary, type=MemoryType.INSIGHT, scope=MemoryScope.SHARED, source="super-memory.dreaming", trust_score=0.7, metadata={"artifact_path": str(path)})
    svc.save(rec)
    return {"ok": True, "dry_run": False, "artifact_path": str(path), "memory_id": rec.id, "artifact": artifact}


def dreaming_repair(config_path: str | None = None) -> dict[str, Any]:
    audit = dreaming_audit(config_path=config_path)
    return {"ok": True, "audit": audit, "repair": "No destructive repair needed; run dreaming_run(dry_run=false) to create consolidation artifact."}
