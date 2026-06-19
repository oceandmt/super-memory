from __future__ import annotations

import importlib.util as _importlib_util
from typing import Any

from . import cleanup as cleanup_mod
from . import code_index, cognitive, graph, intelligence, leitner, lifecycle, phase8, reasoning, safe_flows
from .compat import memory_get_compatible, memory_search_compatible
from .config import load_config
from .hooks import TurnContext
from .models import MemoryRecord, MemoryScope, MemoryType
from .promote import promote_both
from .sanitize import normalize_memory_batch, normalize_memory_payload, sanitize_auto_capture, sanitize_prompt
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory

_HAS_STRUCTLOG = _importlib_util.find_spec("structlog") is not None
if _HAS_STRUCTLOG:
    import structlog as _structlog
    logger = _structlog.get_logger("super-memory.bridge")
else:
    import logging as _logging
    logger = _logging.getLogger("super-memory.bridge")


def remember(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    payload = normalize_memory_payload(payload)
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
    # Dedup check: skip save when an active record with the same content_hash
    # already exists. This prevents duplicate test, contract, and benchmark
    # memories from accumulating across sessions.
    dedup = svc.dedup_check(record)
    if dedup["skipped"]:
        logger.debug("remember dedup hit — skipping save", memory_id=record.id, matched_id=dedup["matched_id"])
        return {
            "record": record.model_dump(mode="json"),
            "dedup": dedup,
            "results": [],
            "graph_projection": None,
        }
    results = svc.save(record)
    graph_projection = None
    try:
        graph_projection = graph.project_memory(record, config_path=config_path)
    except Exception as exc:  # graph projection is derived and must not break canonical-first save
        graph_projection = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"record": record.model_dump(mode="json"), "results": [r.model_dump(mode="json") for r in results], "graph_projection": graph_projection}



def remember_batch(payloads: list[dict[str, Any]], config_path: str | None = None) -> dict[str, Any]:
    payloads = normalize_memory_batch(payloads)
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    items = []
    for payload in payloads:
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
        graph_projection = None
        try:
            graph_projection = graph.project_memory(record, config_path=config_path)
        except Exception as exc:
            graph_projection = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        canonical = next((r for r in results if r.layer.value == "workspace_markdown"), None)
        items.append({
            "ok": bool(canonical and canonical.ok),
            "record": record.model_dump(mode="json"),
            "results": [r.model_dump(mode="json") for r in results],
            "graph_projection": graph_projection,
        })
    return {"ok": all(item["ok"] for item in items), "items": items}

def show(memory_id: str, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    layers = {}
    for layer in ["mempalace", "honcho", "neural_memory"]:
        record = store.get_memory(memory_id, layer=layer)
        if record:
            layers[layer] = record.model_dump(mode="json")
    if not layers:
        return {"ok": False, "error": f"memory not found: {memory_id}"}
    return {"ok": True, "memory_id": memory_id, "layers": layers}

def context(query: str = "", limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    if query:
        records = svc.prefetch(query, limit=limit)
    else:
        # Canonical-first default: workspace_markdown SQLite mirror, fallback mempalace
        store = svc.store
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE layer = 'workspace_markdown' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE layer = 'mempalace' ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        records = [row_to_memory(row) for row in rows]
    return {"records": [r.model_dump(mode="json") for r in records]}

def todo(task: str, priority: int = 5, config_path: str | None = None) -> dict[str, Any]:
    return remember({
        "content": task,
        "type": MemoryType.TODO,
        "scope": MemoryScope.SESSION,
        "tags": ["todo", f"priority:{priority}"],
        "metadata": {"priority": priority},
        "source": "super-memory.todo",
    }, config_path=config_path)

def auto(text: str, save: bool = False, config_path: str | None = None) -> dict[str, Any]:
    text = sanitize_auto_capture(text)
    candidates = []
    for raw in text.splitlines():
        line = raw.strip(" -\t")
        if not line or len(line) < 12:
            continue
        lowered = line.lower()
        mem_type = MemoryType.CONTEXT
        if any(word in lowered for word in ["decided", "decision", "quyết định"]):
            mem_type = MemoryType.DECISION
        elif any(word in lowered for word in ["todo", "next", "cần làm"]):
            mem_type = MemoryType.TODO
        elif any(word in lowered for word in ["blocker", "blocked", "lỗi", "error"]):
            mem_type = MemoryType.BLOCKER
        elif any(word in lowered for word in ["workflow", "process", "quy trình"]):
            mem_type = MemoryType.WORKFLOW
        candidates.append(normalize_memory_payload({"content": line, "type": mem_type.value, "scope": MemoryScope.SESSION.value, "source": "super-memory.auto"}, auto_capture=True))
    result = {"candidates": candidates, "saved": None}
    if save and candidates:
        result["saved"] = remember_batch(candidates, config_path=config_path)
    return result

def stats(config_path: str | None = None) -> dict[str, Any]:
    return status(config_path=config_path)

def health(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    st = status(config_path=config_path)
    canonical_enabled = "workspace_markdown" in [layer.value for layer in cfg.enabled_layers]
    return {
        "ok": canonical_enabled and cfg.require_canonical_first,
        "canonical_first": cfg.require_canonical_first,
        "workspace_markdown_enabled": canonical_enabled,
        "enabled_layers": [layer.value for layer in cfg.enabled_layers],
        "status": st,
    }

def conflicts(content: str | None = None, memory_id: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    return intelligence.conflicts(content=content, memory_id=memory_id, config_path=config_path)

def provenance(memory_id: str, action: str = "trace", actor: str = "super-memory", config_path: str | None = None) -> dict[str, Any]:
    return intelligence.provenance(memory_id, action=action, actor=actor, config_path=config_path)

def source(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    return intelligence.source(payload, config_path=config_path)

def version(action: str = "create", name: str = "snapshot", config_path: str | None = None, **kwargs: Any) -> dict[str, Any]:
    return intelligence.version(action=action, name=name, config_path=config_path, **kwargs)

def pin(memory_id: str, action: str = "pin", config_path: str | None = None) -> dict[str, Any]:
    return intelligence.pin(memory_id, action=action, config_path=config_path)

def consolidate(strategy: str = "all", dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    return intelligence.consolidate(strategy=strategy, dry_run=dry_run, config_path=config_path)

def gaps(topic: str, action: str = "detect", config_path: str | None = None) -> dict[str, Any]:
    return intelligence.gaps(topic, action=action, config_path=config_path)

def explain(from_entity: str, to_entity: str, config_path: str | None = None) -> dict[str, Any]:
    return intelligence.explain(from_entity, to_entity, config_path=config_path)

def situation(config_path: str | None = None) -> dict[str, Any]:
    return intelligence.situation(config_path=config_path)

def reflex(memory_id: str, action: str = "pin", config_path: str | None = None) -> dict[str, Any]:
    return intelligence.reflex(memory_id, action=action, config_path=config_path)

def boundaries(domain: str = "global", content: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    return intelligence.boundaries(domain=domain, content=content, config_path=config_path)

def optional_heavy(action: str, **kwargs: Any) -> dict[str, Any]:
    config_path = kwargs.pop("config_path", None)
    if action == "train":
        return safe_flows.train(
            kwargs.get("path", "."),
            domain_tag=kwargs.get("domain_tag", "local"),
            recursive=kwargs.get("recursive", True),
            limit=kwargs.get("limit", 200),
            max_chunks_per_file=kwargs.get("max_chunks_per_file", 20),
            save=kwargs.get("save", True),
            config_path=config_path,
        )
    if action == "index":
        return code_index.index_codebase(
            kwargs.get("path", "."),
            extensions=kwargs.get("extensions"),
            recursive=kwargs.get("recursive", True),
            limit=kwargs.get("limit", 500),
            save=kwargs.get("save", True),
            config_path=config_path,
        )
    return intelligence.heavy_optional(action, **kwargs)

def recall(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    query = sanitize_prompt(query)
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    hits = svc.recall(query, limit=limit)
    return {layer.value: [r.model_dump(mode="json") for r in records] for layer, records in hits.items()}


def prefetch(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    query = sanitize_prompt(query)
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    records = svc.prefetch(query, limit=limit)
    return {"records": [r.model_dump(mode="json") for r in records]}


def sync_turn(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    payload = dict(payload)
    if payload.get("user_message"):
        payload["user_message"] = sanitize_auto_capture(payload["user_message"])
    if payload.get("assistant_message"):
        payload["assistant_message"] = sanitize_auto_capture(payload["assistant_message"])
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


def forget(memory_id: str, hard: bool = False, reason: str = "", config_path: str | None = None) -> dict[str, Any]:
    """Delete a memory. Soft delete by default (marks metadata; recoverable).
    Hard delete also removes related graph synapses, fibers, and cross-layer entries."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id)
    if not record:
        return {"ok": False, "error": f"memory not found: {memory_id}"}
    if not hard:
        with store.connect() as conn:
            conn.execute(
                "UPDATE memories SET metadata_json = json_set(metadata_json, '$.soft_deleted', 1, '$.deleted_reason', ?) WHERE id = ?",
                (reason, memory_id),
            )
            conn.commit()
        return {"ok": True, "memory_id": memory_id, "hard": False, "action": "soft_delete"}
    # Hard delete: cascade cleanup
    with store.connect() as conn:
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        if cfg.legacy_graph_edges:
            conn.execute("DELETE FROM graph_edges WHERE source_memory_id = ? OR target_memory_id = ?", (memory_id, memory_id))
        conn.execute("DELETE FROM cognitive_synapses WHERE source_neuron_id IN (SELECT id FROM cognitive_neurons WHERE source_memory_id = ?) OR target_neuron_id IN (SELECT id FROM cognitive_neurons WHERE source_memory_id = ?)", (memory_id, memory_id))
        conn.execute("DELETE FROM cognitive_neurons WHERE source_memory_id = ?", (memory_id,))
        conn.execute("DELETE FROM cognitive_fibers WHERE id = ?", (f"f:{memory_id}",))
        conn.execute("DELETE FROM honcho_events WHERE memory_id = ?", (memory_id,))
        conn.execute("DELETE FROM palace_drawers WHERE memory_id = ?", (memory_id,))
        conn.commit()
    return {"ok": True, "memory_id": memory_id, "hard": True, "action": "hard_delete"}


def edit(memory_id: str, content: str | None = None, type: str | None = None, priority: int | None = None, tier: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    """Edit a memory's content, type, priority, or tier. Preserves all synapses."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id)
    if not record:
        return {"ok": False, "error": f"memory not found: {memory_id}"}
    updates: list[str] = []
    params: list[Any] = []
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if type is not None:
        updates.append("type = ?")
        params.append(type)
    if priority is not None:
        updates.append("trust_score = ?")
        params.append(max(0, min(10, priority)) / 10.0)
    if tier is not None:
        updates.append("metadata_json = json_set(metadata_json, '$.tier', ?)")
        params.append(tier)
    if not updates:
        return {"ok": False, "error": "no fields to update"}
    params.append(memory_id)
    set_clause = ", ".join(updates)
    with store.connect() as conn:
        conn.execute("UPDATE memories SET " + set_clause + " WHERE id = ?", params)
        conn.commit()
    updated = store.get_memory(memory_id)
    return {"ok": True, "memory_id": memory_id, "updated": updated.model_dump(mode="json") if updated else None}


def status(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    # Ensure schema exists/upgrades before direct status reads.
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        layers = conn.execute("SELECT layer, COUNT(*) as c FROM memories GROUP BY layer").fetchall()
        # V2: when legacy_graph_edges is disabled, only count cognitive_synapses
        if cfg.legacy_graph_edges:
            leg_edges = conn.execute("SELECT COUNT(*) as c FROM graph_edges").fetchone()["c"]
        else:
            leg_edges = 0
        # Unified graph: cognitive_synapses primary + graph_edges legacy, graceful fallback
        try:
            cog_syn = conn.execute("SELECT COUNT(*) as c FROM cognitive_synapses").fetchone()["c"]
        except Exception:
            cog_syn = 0
        try:
            neurons_ct = conn.execute("SELECT COUNT(*) as c FROM cognitive_neurons").fetchone()["c"]
        except Exception:
            neurons_ct = 0
        try:
            fibers_ct = conn.execute("SELECT COUNT(*) as c FROM cognitive_fibers").fetchone()["c"]
        except Exception:
            fibers_ct = 0
        edges = cog_syn + leg_edges
        drawers = conn.execute("SELECT COUNT(*) as c FROM palace_drawers").fetchone()["c"]
        events = conn.execute("SELECT COUNT(*) as c FROM honcho_events").fetchone()["c"]

    # Filesystem markdown stats (canonical layer outside SQLite)
    fs_stats = _filesystem_markdown_stats(cfg)

    return {
        "total_memories": count,
        "layers": {r["layer"]: r["c"] for r in layers},
        "filesystem_markdown": fs_stats,
        "graph_edges": edges,
        "cognitive_synapses": cog_syn,
        "cognitive_neurons": neurons_ct,
        "cognitive_fibers": fibers_ct,
        "palace_drawers": drawers,
        "honcho_events": events,
    }


def memory_search(query: str, max_results: int = 5, min_score: float = 0.0, corpus: str = "all", config_path: str | None = None) -> dict[str, Any]:
    query = sanitize_prompt(query)
    cfg = load_config(config_path)
    return memory_search_compatible(query, max_results=max_results, min_score=min_score, corpus=corpus, config=cfg)


def memory_get(path: str, from_line: int = 1, lines: int = 20, corpus: str = "all", config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    return memory_get_compatible(path, from_line=from_line, lines=lines, corpus=corpus, config=cfg)

def working_memory_get(key: str = "default", config_path: str | None = None) -> dict[str, Any]:
    return cognitive.working_memory_get(key=key, config_path=config_path)

def working_memory_set(payload: dict[str, Any], key: str = "default", ttl_seconds: int | None = None, config_path: str | None = None) -> dict[str, Any]:
    return cognitive.working_memory_set(payload, key=key, ttl_seconds=ttl_seconds, config_path=config_path)

def attention_score(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    return cognitive.attention_score(payload, config_path=config_path)

def route_memory(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    return cognitive.route_memory(payload, config_path=config_path)

def parallel_save(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    return cognitive.parallel_save(payload, config_path=config_path)

def recall_arbitrate(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    return cognitive.recall_arbitrate(query, limit=limit, config_path=config_path)

def consolidation_cycle(strategy: str = "light", dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    return cognitive.consolidation_cycle(strategy=strategy, dry_run=dry_run, config_path=config_path)

def conflict_resolve(conflict_id: str, resolution: str, reason: str = "", config_path: str | None = None) -> dict[str, Any]:
    return cognitive.conflict_resolve(conflict_id, resolution, reason=reason, config_path=config_path)

def promotion_candidates(limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    return cognitive.promotion_candidates(limit=limit, config_path=config_path)

def feedback_outcome(memory_id: str | None = None, success: bool = True, outcome: str = "", config_path: str | None = None) -> dict[str, Any]:
    return cognitive.feedback_outcome(memory_id=memory_id, success=success, outcome=outcome, config_path=config_path)

# Phase 7 / Layer 4 graph maturity
def graph_stats(config_path: str | None = None) -> dict[str, Any]:
    return graph.stats(config_path=config_path)

def graph_neighbors(neuron_or_memory_id: str, direction: str = "out", limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    return graph.neighbors(neuron_or_memory_id, direction=direction, limit=limit, config_path=config_path)

def graph_recall(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    return graph.recall(query, limit=limit, config_path=config_path)

def spreading_activation_recall(query: str, depth: int = 2, top_k: int = 20, seed_limit: int = 30, config_path: str | None = None) -> dict[str, Any]:
    """Neural-memory-style spreading activation recall through the cognitive graph."""
    return graph.spreading_activation(query, depth=depth, top_k=top_k, seed_limit=seed_limit, config_path=config_path)

def graph_rebuild(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Rebuild Layer 4 cognitive graph (incremental by default). Use graph_rebuild_destructive() for full rebuild."""
    return graph.rebuild_incremental(limit=limit, config_path=config_path)

def graph_rebuild_destructive(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Destructive full rebuild — drops and recreates all cognitive projections."""
    return graph.rebuild(limit=limit, config_path=config_path)

def graph_rebuild_incremental(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return graph.rebuild_incremental(limit=limit, config_path=config_path)

def graph_cleanup_orphans(config_path: str | None = None) -> dict[str, Any]:
    return graph.cleanup_orphans(config_path=config_path)


def cleanup(config_path: str | None = None, vacuum: bool = False, integrity_check: bool = True) -> dict[str, Any]:
    return cleanup_mod.cleanup(config_path=config_path, vacuum=vacuum, integrity_check=integrity_check)


def prune(config_path: str | None = None, dry_run: bool = True, source_prefixes: list[str] | None = None, max_days: int | None = None) -> dict[str, Any]:
    """Prune memories matching retention policy criteria.

    Safe by default (dry_run=True). Use dry_run=False to actually delete.
    See cleanup_mod.prune for details.
    """
    return cleanup_mod.prune(config_path=config_path, dry_run=dry_run, source_prefixes=source_prefixes, max_days=max_days)

# Phase 7 / P2 lifecycle
def lifecycle_review(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return lifecycle.review(config_path=config_path, limit=limit)

def lifecycle_cache(action: str = "status", config_path: str | None = None) -> dict[str, Any]:
    return lifecycle.cache(action=action, config_path=config_path)

def lifecycle_tier(action: str = "evaluate", dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return lifecycle.tier(action=action, dry_run=dry_run, config_path=config_path, limit=limit)

def lifecycle_compression(action: str = "review", dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return lifecycle.compression(action=action, dry_run=dry_run, config_path=config_path, limit=limit)

def reflex_status(config_path: str | None = None) -> dict[str, Any]:
    return lifecycle.reflex_status(config_path=config_path)

def leitner_due(config_path: str | None = None) -> dict[str, Any]:
    """Return only the count of Leitner-due memories (lightweight)."""
    return leitner.due(config_path=config_path)

def leitner_queue(limit: int = 50, config_path: str | None = None) -> dict[str, Any]:
    """Return memories due for Leitner review."""
    return leitner.queue(config_path=config_path, limit=limit)

def leitner_mark(fiber_id: str, success: bool, config_path: str | None = None) -> dict[str, Any]:
    """Record a Leitner review result (success → box++, failure → reset to 0)."""
    return leitner.mark(fiber_id, success=success, config_path=config_path)

def leitner_schedule(fiber_id: str, box: int, config_path: str | None = None) -> dict[str, Any]:
    """Manually set a memory's Leitner box."""
    return leitner.schedule(fiber_id, box=box, config_path=config_path)

def leitner_stats(config_path: str | None = None) -> dict[str, Any]:
    """Leitner 5-box distribution + review stats."""
    return leitner.stats(config_path=config_path)

def leitner_auto_seed(limit: int = 100, config_path: str | None = None) -> dict[str, Any]:
    """Auto-assign Leitner box 0 to unreviewed memories."""
    return leitner.auto_seed(config_path=config_path, limit=limit)

# Phase 7 / P3 safe flows
def train_local(path: str, domain_tag: str = "local", recursive: bool = True, limit: int = 200, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    return safe_flows.train(path, domain_tag=domain_tag, recursive=recursive, limit=limit, save=save, config_path=config_path)

def index_local(path: str, extensions: list[str] | None = None, recursive: bool = True, limit: int = 500, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    return code_index.index_codebase(path, extensions=extensions, recursive=recursive, limit=limit, save=save, config_path=config_path)

def index_status(config_path: str | None = None) -> dict[str, Any]:
    return code_index.index_status(config_path=config_path)

def import_local(path: str, source_name: str = "local-import", recursive: bool = True, limit: int = 200, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    return safe_flows.import_local(path, source_name=source_name, recursive=recursive, limit=limit, save=save, config_path=config_path)

def watch_scan(directory: str, recursive: bool = True, limit: int = 200, save: bool = False, config_path: str | None = None) -> dict[str, Any]:
    return safe_flows.watch_scan(directory, recursive=recursive, limit=limit, save=save, config_path=config_path)

def sync_status(config_path: str | None = None) -> dict[str, Any]:
    return safe_flows.sync_status(config_path=config_path)

def store_status(config_path: str | None = None) -> dict[str, Any]:
    return safe_flows.store_status(config_path=config_path)

# Phase 7 / P1 cognitive workflow
def hypothesis_create(content: str, confidence: float = 0.5, tags: list[str] | None = None, config_path: str | None = None) -> dict[str, Any]:
    return reasoning.hypothesis_create(content, confidence=confidence, tags=tags, config_path=config_path)

def hypothesis_get(hypothesis_id: str, config_path: str | None = None) -> dict[str, Any]:
    return reasoning.hypothesis_get(hypothesis_id, config_path=config_path)

def hypothesis_list(status: str | None = None, limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    return reasoning.hypothesis_list(status=status, limit=limit, config_path=config_path)

def evidence_add(hypothesis_id: str, content: str, direction: str = "for", weight: float = 0.5, config_path: str | None = None) -> dict[str, Any]:
    return reasoning.evidence_add(hypothesis_id, content, direction=direction, weight=weight, config_path=config_path)

def prediction_create(content: str, confidence: float = 0.7, hypothesis_id: str | None = None, deadline: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    return reasoning.prediction_create(content, confidence=confidence, hypothesis_id=hypothesis_id, deadline=deadline, config_path=config_path)

def prediction_list(status: str | None = None, limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    return reasoning.prediction_list(status=status, limit=limit, config_path=config_path)

def verify_prediction(prediction_id: str, outcome: str, content: str = "", config_path: str | None = None) -> dict[str, Any]:
    return reasoning.verify_prediction(prediction_id, outcome, content=content, config_path=config_path)

def expire_predictions(config_path: str | None = None) -> dict[str, Any]:
    return reasoning.expire_predictions(config_path=config_path)


# Phase 8 live-readiness / diagnostics / contracts
def diagnostics(config_path: str | None = None) -> dict[str, Any]:
    return phase8.diagnostics(config_path=config_path)

def memory_slot_contract(config_path: str | None = None) -> dict[str, Any]:
    return phase8.memory_slot_contract(config_path=config_path)

def mcp_contract(profile: str = "admin", config_path: str | None = None) -> dict[str, Any]:
    return phase8.mcp_contract(profile=profile, config_path=config_path)

def supervised_runtime_smoke(config_path: str | None = None) -> dict[str, Any]:
    return phase8.supervised_runtime_smoke(config_path=config_path)


# ── Cross-layer health & filesystem markdown helpers ────────────────────────

def _filesystem_markdown_stats(cfg: Any) -> dict[str, Any]:
    """Count filesystem markdown entries (canonical layer outside SQLite)."""
    try:
        mem_dir = cfg.workspace_root / cfg.daily_memory_dir
        if not mem_dir.exists():
            return {"daily_files": 0, "total_entries": 0, "latest_file": None}
        daily_files = sorted(mem_dir.glob("*.md"))
        total_entries = 0
        latest_file = None
        for fpath in daily_files:
            total_entries += sum(1 for line in fpath.read_text(encoding="utf-8", errors="ignore").splitlines() if line.startswith("- "))
            latest_file = str(fpath.relative_to(cfg.workspace_root))
        return {
            "daily_files": len(daily_files),
            "total_entries": total_entries,
            "latest_file": latest_file,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def cross_layer_health(config_path: str | None = None) -> dict[str, Any]:
    """Cross-layer consistency audit.

    Verifies:
    - (a) Every SQLite memory ID has a matching filesystem markdown entry
    - (b) Content hasn't drifted (content_hash check)
    - (c) No orphan projections (palace_drawers, honcho_events, graph, cognitive)
    """

    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    issues: list[dict[str, Any]] = []

    FILTER_ACTIVE = "(json_extract(metadata_json, '$.soft_deleted') IS NULL OR json_extract(metadata_json, '$.soft_deleted') != 1)"

    def _has_table(conn, table: str) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

    with store.connect() as conn:
        has_memories = _has_table(conn, "memories")
        has_palace = _has_table(conn, "palace_drawers")
        has_honcho = _has_table(conn, "honcho_events")
        has_graph_edges = _has_table(conn, "graph_edges")
        has_cognitive_neurons = _has_table(conn, "cognitive_neurons")
        has_cognitive_synapses = _has_table(conn, "cognitive_synapses")
        has_cognitive_fibers = _has_table(conn, "cognitive_fibers")
        if not has_memories:
            return {
                "ok": True,
                "verdict": "pass",
                "active_ids": 0,
                "full_4layer_coverage": 0,
                "full_4layer_pct": 0,
                "soft_deleted": 0,
                "pending_canonical_sync": 0,
                "sqlite_only_ids": 0,
                "content_drift_count": 0,
                "orphan_projections_total": 0,
                "issues": [],
            }
        # ── (a) Check for SQLite-only IDs (no workspace_markdown row) ──
        sqlite_only = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM memories"
            " WHERE layer != 'workspace_markdown'"
            " AND " + FILTER_ACTIVE +
            " AND id NOT IN ("
            " SELECT id FROM memories WHERE layer = 'workspace_markdown'"
            " )"
        ).fetchone()[0]

        # ── (b) Content drift: workspace_markdown vs other layers ──
        drift_rows = conn.execute("""
            SELECT m1.id, m1.layer, m2.layer AS layer2,
                   m1.content_hash, m2.content_hash AS hash2
            FROM memories m1
            JOIN memories m2 ON m1.id = m2.id
            WHERE m1.layer = 'workspace_markdown'
            AND m2.layer != 'workspace_markdown'
            AND m1.content_hash IS NOT NULL
            AND m2.content_hash IS NOT NULL
            AND m1.content_hash != m2.content_hash
            LIMIT 50
        """).fetchall()

        drift_details: list[dict[str, Any]] = []
        for row in drift_rows:
            drift_details.append({
                "id": row["id"],
                "layer_a": row["layer"],
                "layer_b": row["layer2"],
                "hash_a": row["content_hash"][:12],
                "hash_b": row["hash2"][:12],
            })

        # ── (c) Orphan projections ──
        orphan_palace = conn.execute("""
            SELECT COUNT(*) FROM palace_drawers
            WHERE memory_id NOT IN (SELECT DISTINCT id FROM memories)
        """).fetchone()[0] if has_palace else 0

        orphan_honcho = conn.execute("""
            SELECT COUNT(*) FROM honcho_events
            WHERE memory_id NOT IN (SELECT DISTINCT id FROM memories)
            AND memory_id IS NOT NULL
        """).fetchone()[0] if has_honcho else 0

        orphan_graph = conn.execute("""
            SELECT COUNT(*) FROM graph_edges
            WHERE source_memory_id NOT IN (SELECT DISTINCT id FROM memories)
            OR target_memory_id NOT IN (SELECT DISTINCT id FROM memories)
        """).fetchone()[0] if has_graph_edges else 0

        orphan_cog_syn = conn.execute("""
            SELECT COUNT(*) FROM cognitive_synapses cs
            LEFT JOIN cognitive_neurons cn1 ON cs.source_neuron_id = cn1.id
            LEFT JOIN cognitive_neurons cn2 ON cs.target_neuron_id = cn2.id
            WHERE cn1.id IS NULL OR cn2.id IS NULL
        """).fetchone()[0] if has_cognitive_synapses and has_cognitive_neurons else 0

        orphan_cog_neurons = conn.execute("""
            SELECT COUNT(*) FROM cognitive_neurons
            WHERE source_memory_id IS NOT NULL
            AND source_memory_id NOT IN (SELECT DISTINCT id FROM memories)
        """).fetchone()[0] if has_cognitive_neurons else 0

        orphan_cog_fibers = conn.execute("""
            SELECT COUNT(*) FROM cognitive_fibers cf
            LEFT JOIN cognitive_neurons cn ON cf.anchor_neuron_id = cn.id
            WHERE cn.id IS NULL
        """).fetchone()[0] if has_cognitive_fibers and has_cognitive_neurons else 0

        # ── Layer coverage: how many IDs have full 4-layer representation ──
        active_ids = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM memories WHERE " + FILTER_ACTIVE
        ).fetchone()[0]

        full_coverage = conn.execute(
            "SELECT COUNT(*) FROM ("
            " SELECT id FROM memories WHERE " + FILTER_ACTIVE +
            " GROUP BY id HAVING COUNT(DISTINCT layer) = 4"
            " )"
        ).fetchone()[0]

        soft_deleted = conn.execute("""
            SELECT COUNT(*) FROM memories
            WHERE json_extract(metadata_json, '$.soft_deleted') = 1
        """).fetchone()[0]

        pending_sync = conn.execute("""
            SELECT COUNT(*) FROM memories
            WHERE pending_canonical_sync = 1
        """).fetchone()[0]

    orphan_total = orphan_palace + orphan_honcho + orphan_graph + orphan_cog_syn + orphan_cog_neurons + orphan_cog_fibers

    verdict = "pass"
    issues = []
    if sqlite_only > 0:
        issues.append({"check": "sqlite_only_ids", "count": sqlite_only, "detail": "IDs in SQLite layers but missing workspace_markdown row"})
    if drift_details:
        issues.append({"check": "content_drift", "count": len(drift_details), "samples": drift_details[:5]})
    if orphan_total > 0:
        issues.append({
            "check": "orphan_projections",
            "total": orphan_total,
            "breakdown": {
                "palace_drawers": orphan_palace,
                "honcho_events": orphan_honcho,
                "graph_edges": orphan_graph,
                "cognitive_synapses": orphan_cog_syn,
                "cognitive_neurons": orphan_cog_neurons,
                "cognitive_fibers": orphan_cog_fibers,
            }
        })

    if issues:
        verdict = "issues_found"

    return {
        "ok": len(issues) == 0,
        "verdict": verdict,
        "active_ids": active_ids,
        "full_4layer_coverage": full_coverage,
        "full_4layer_pct": round(full_coverage / active_ids * 100, 1) if active_ids else 0,
        "soft_deleted": soft_deleted,
        "pending_canonical_sync": pending_sync,
        "sqlite_only_ids": sqlite_only,
        "content_drift_count": len(drift_details),
        "orphan_projections_total": orphan_total,
        "issues": issues,
    }


def backfill_markdown_sqlite(limit: int = 2000, config_path: str | None = None) -> dict[str, Any]:
    """Backfill workspace_markdown rows into SQLite for historical records.

    For records that exist in mempalace/honcho/neural_memory but lack a
    workspace_markdown row in SQLite. Reconstructs from existing layers
    using content from the earliest available SQLite layer.
    """

    import json

    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    with store.connect() as conn:
        # Find IDs that have SQLite layers but no workspace_markdown
        ids_to_backfill = conn.execute("""
            SELECT DISTINCT m.id, m.content, m.type, m.scope, m.agent_id,
                   m.session_id, m.project, m.tags_json, m.source,
                   m.trust_score, m.created_at, m.metadata_json,
                   m.content_hash
            FROM memories m
            WHERE m.layer != 'workspace_markdown'
            AND m.id NOT IN (
                SELECT id FROM memories WHERE layer = 'workspace_markdown'
            )
            LIMIT ?
        """, (limit,)).fetchall()

        backfilled = 0
        errors = 0
        for row in ids_to_backfill:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO memories
                    (id, layer, content, type, scope, agent_id, session_id,
                     project, tags_json, source, trust_score, created_at,
                     metadata_json, pending_canonical_sync, content_hash)
                    VALUES (?, 'workspace_markdown', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """, (
                    row["id"], row["content"], row["type"], row["scope"],
                    row["agent_id"], row["session_id"], row["project"],
                    row["tags_json"], row["source"], row["trust_score"],
                    row["created_at"], row["metadata_json"], row["content_hash"],
                ))
                backfilled += 1
            except Exception:
                errors += 1
        conn.commit()

        # Re-count remaining
        remaining = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM memories"
            " WHERE layer != 'workspace_markdown'"
            " AND id NOT IN ("
            " SELECT id FROM memories WHERE layer = 'workspace_markdown'"
            " )"
        ).fetchone()[0]

    return {
        "ok": True,
        "backfilled": backfilled,
        "errors": errors,
        "remaining_sqlite_only": remaining,
    }
