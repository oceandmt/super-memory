from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import load_config
from .consolidation import consolidate_real
from .models import MemoryRecord
from .sanitize import normalize_memory_payload, sanitize_prompt
from .service import SuperMemoryService
from .storage import SuperMemoryStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta_table(store: SuperMemoryStore) -> None:
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_events (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                subject TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_intelligence_kind ON intelligence_events(kind)")


def _event(config_path: str | None, kind: str, subject: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    SuperMemoryService(cfg)
    _meta_table(store)
    event_id = str(uuid4())
    row = {"id": event_id, "kind": kind, "subject": subject, "payload": payload, "created_at": _now()}
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO intelligence_events (id, kind, subject, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, kind, subject, json.dumps(payload, ensure_ascii=False), row["created_at"]),
        )
    return {"ok": True, **row}


def source(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    name = sanitize_prompt(payload.get("name") or payload.get("source") or "unnamed-source", max_chars=200)
    return _event(config_path, "source", name, {"name": name, "source_type": payload.get("source_type", "document"), "version": payload.get("version"), "status": payload.get("status", "active"), "metadata": payload.get("metadata", {})})


def provenance(memory_id: str, action: str = "trace", actor: str = "super-memory", config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    SuperMemoryService(cfg)
    rec = store.get_memory(memory_id)
    if not rec:
        return {"ok": False, "error": f"memory not found: {memory_id}"}
    if action in {"verify", "approve"}:
        return _event(config_path, f"provenance:{action}", memory_id, {"memory_id": memory_id, "actor": actor})
    return {"ok": True, "memory_id": memory_id, "record": rec.model_dump(mode="json"), "source": rec.source, "metadata": rec.metadata}


def conflicts(content: str | None = None, memory_id: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    query = sanitize_prompt(content or memory_id or "")
    hits = svc.prefetch(query, limit=10) if query else []
    candidates = [h.model_dump(mode="json") for h in hits if content and h.content != content]
    return {"ok": True, "has_conflicts": False, "conflict_count": 0, "candidates": candidates[:5], "note": "deterministic placeholder; no contradiction model enabled"}


def version(action: str = "create", name: str = "snapshot", config_path: str | None = None, **kwargs: Any) -> dict[str, Any]:
    if action == "create":
        return _event(config_path, "version", name, {"name": name, "description": kwargs.get("description", ""), "snapshot": True})
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _meta_table(store)
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM intelligence_events WHERE kind='version' ORDER BY created_at DESC LIMIT ?", (kwargs.get("limit", 20),)).fetchall()
    return {"ok": True, "versions": [{"id": r["id"], "name": r["subject"], "payload": json.loads(r["payload_json"]), "created_at": r["created_at"]} for r in rows]}


def pin(memory_id: str, action: str = "pin", config_path: str | None = None) -> dict[str, Any]:
    return _event(config_path, f"pin:{action}", memory_id, {"memory_id": memory_id, "action": action})


def reflex(memory_id: str, action: str = "pin", config_path: str | None = None) -> dict[str, Any]:
    return _event(config_path, f"reflex:{action}", memory_id, {"memory_id": memory_id, "action": action})


def boundaries(domain: str = "global", content: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    if content:
        payload = normalize_memory_payload({"content": content, "type": "doctrine", "scope": "shared", "tags": ["boundary", f"domain:{domain}"], "source": "super-memory.boundaries"})
        saved = SuperMemoryService(load_config(config_path)).save(MemoryRecord(**payload))
        return {"ok": True, "domain": domain, "results": [r.model_dump(mode="json") for r in saved]}
    records = SuperMemoryService(load_config(config_path)).prefetch(f"domain:{domain} boundary", limit=20)
    return {"ok": True, "domain": domain, "boundaries": [r.model_dump(mode="json") for r in records]}


def gaps(topic: str, action: str = "detect", config_path: str | None = None) -> dict[str, Any]:
    return _event(config_path, f"gap:{action}", topic, {"topic": sanitize_prompt(topic, max_chars=300), "action": action})


def explain(from_entity: str, to_entity: str, config_path: str | None = None) -> dict[str, Any]:
    q = f"{sanitize_prompt(from_entity)} {sanitize_prompt(to_entity)}"
    records = SuperMemoryService(load_config(config_path)).prefetch(q, limit=10)
    return {"ok": True, "from": from_entity, "to": to_entity, "path": [r.model_dump(mode="json") for r in records]}


def situation(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    status = {
        "recent": [r.model_dump(mode="json") for r in svc.prefetch("decision workflow blocker todo", limit=10)],
        "health": {"canonical_first": cfg.require_canonical_first, "enabled_layers": [layer.value for layer in cfg.enabled_layers]},
    }
    return {"ok": True, **status}


def consolidate(strategy: str = "all", dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    result = consolidate_real(strategy=strategy, dry_run=dry_run, config_path=config_path)
    if not dry_run:
        _event(config_path, "consolidate", strategy, {"strategy": strategy, "dry_run": dry_run, "summary": {"merged": len(result.get("merged", [])), "contradictions": len(result.get("contradictions", [])), "semantic_created": len(result.get("semantic_created", []))}})
    return result


def heavy_optional(action: str, **kwargs: Any) -> dict[str, Any]:
    HELP = {
        "sync": "Cloud sync. Requires SUPER_MEMORY_HUB_URL and SUPER_MEMORY_HUB_API_KEY env vars + pip install super-memory[sync]",
        "train": "Document training. Requires pip install super-memory[extract] for PDF/DOCX/PPTX support. See docs/semantic-mode.md",
        "import": "Bulk import from external systems (ChromaDB, Mem0). Requires source-specific client libs. See super_memory/import.py",
        "index": "Codebase indexing. Uses super_memory/code_index.py — run super_memory_index_local for workspace-scoped indexing",
        "store": "Brain store for sharing/importing community knowledge bases. Requires SUPER_MEMORY_STORE_API_KEY",
        "visualize": "Chart generation from memory data. Uses Vega-Lite rendering. Install optional: pip install vega-lite",
        "watch": "Directory watcher for auto-ingest. Run super_memory_watch_scan for one-shot. Daemon mode requires file watcher libs",
        "telegram_backup": "Telegram bot backup for brain DB. Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID",
    }
    help_text = HELP.get(action, "Available in Phase 4 once explicitly configured")
    return {
        "ok": False,
        "action": action,
        "enabled": False,
        "message": f"Phase 4: {help_text}",
        "alternative": f"See docs/PHASE_4_{action.upper()}.md or run with explicit config_path",
        "params": kwargs,
    }
