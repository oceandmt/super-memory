from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .config import load_config
from .compat import memory_get_compatible, memory_search_compatible
from .hooks import TurnContext
from .models import MemoryRecord, MemoryScope, MemoryType
from .promote import promote_both
from .service import SuperMemoryService
from .storage import SuperMemoryStore


def remember(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    record = MemoryRecord(
        content=payload["content"],
        type=payload.get("type", MemoryType.CONTEXT),
        scope=payload.get("scope", MemoryScope.SESSION),
        agent_id=payload.get("agent_id", "lucas"),
        session_id=payload.get("session_id"),
        project=payload.get("project"),
        tags=payload.get("tags", []),
        source=payload.get("source"),
        trust_score=payload.get("trust_score"),
        metadata=payload.get("metadata", {}),
    )
    results = svc.save(record)
    return {"record": record.model_dump(mode="json"), "results": [r.model_dump(mode="json") for r in results]}


def recall(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    hits = svc.recall(query, limit=limit)
    return {layer.value: [r.model_dump(mode="json") for r in records] for layer, records in hits.items()}


def prefetch(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    records = svc.prefetch(query, limit=limit)
    return {"records": [r.model_dump(mode="json") for r in records]}


def sync_turn(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    ctx = TurnContext(
        agent_id=payload.get("agent_id", "lucas"),
        session_id=payload.get("session_id"),
        user_message=payload.get("user_message"),
        assistant_message=payload.get("assistant_message"),
        project=payload.get("project"),
        metadata=payload.get("metadata", {}),
    )
    results = svc.sync_turn(ctx)
    return {"results": [r.model_dump(mode="json") for r in results]}


def promote(memory_id: str, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id)
    if not record:
        return {"ok": False, "error": f"memory not found: {memory_id}"}
    mem_path, reg_path = promote_both(cfg, record)
    return {"ok": True, "memory_id": memory_id, "long_term_path": mem_path, "register_path": reg_path}


def status(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    # Ensure schema exists/upgrades before direct status reads.
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        layers = conn.execute("SELECT layer, COUNT(*) as c FROM memories GROUP BY layer").fetchall()
        edges = conn.execute("SELECT COUNT(*) as c FROM graph_edges").fetchone()["c"]
        drawers = conn.execute("SELECT COUNT(*) as c FROM palace_drawers").fetchone()["c"]
        events = conn.execute("SELECT COUNT(*) as c FROM honcho_events").fetchone()["c"]
    return {
        "total_memories": count,
        "layers": {r["layer"]: r["c"] for r in layers},
        "graph_edges": edges,
        "palace_drawers": drawers,
        "honcho_events": events,
    }


def memory_search(query: str, max_results: int = 5, min_score: float = 0.0, corpus: str = "all", config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    return memory_search_compatible(query, max_results=max_results, min_score=min_score, corpus=corpus, config=cfg)


def memory_get(path: str, from_line: int = 1, lines: int = 20, corpus: str = "all", config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    return memory_get_compatible(path, from_line=from_line, lines=lines, corpus=corpus, config=cfg)
