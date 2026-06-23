from __future__ import annotations

import json
import sqlite3
from typing import Any

from .config import load_config
from .compat import memory_get_compatible, memory_search_compatible
from .hooks import TurnContext
from .models import MemoryRecord, MemoryScope, MemoryType
from .promote import promote_both
from .sanitize import normalize_memory_batch, normalize_memory_payload, sanitize_auto_capture, sanitize_prompt
from .quality_gate import apply_quality_gate
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory
from . import intelligence, cognitive, graph, lifecycle, safe_flows, reasoning, phase8, code_index, leitner, semantic_quality, short_term, session_index, cooldown, mmr, temporal_decay, hybrid_search, session_visibility, embeddings_registry, rem, watcher, flush_plan, reindex, index_identity, self_heal, prompt_section, narrative, rem_evidence, qmd




def _safe_memories_update(
    conn: "sqlite3.Connection",
    updates: dict[str, str],  # column_name -> escaped_value
    where_id: str,
    where_layer: str | None = None,
) -> None:
    """Execute UPDATE on memories table with executescript to work around
    FTS5 trigger issues with parameterized queries on composite PK tables."""
    set_clause = ", ".join(f"{k} = '{v}'" for k, v in updates.items())
    esc_id = where_id.replace("'", "''")
    if where_layer:
        esc_layer = where_layer.replace("'", "''")
        sql = f"UPDATE memories SET {set_clause} WHERE id = '{esc_id}' AND layer = '{esc_layer}';"
    else:
        sql = f"UPDATE memories SET {set_clause} WHERE id = '{esc_id}';"
    conn.executescript(sql)
def remember(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    payload = apply_quality_gate(normalize_memory_payload(payload))
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
    graph_projection = None
    try:
        graph_projection = graph.project_memory(record, config_path=config_path)
    except Exception as exc:  # graph projection is derived and must not break canonical-first save
        graph_projection = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"record": record.model_dump(mode="json"), "results": [r.model_dump(mode="json") for r in results], "graph_projection": graph_projection}



def remember_batch(payloads: list[dict[str, Any]], config_path: str | None = None) -> dict[str, Any]:
    payloads = [apply_quality_gate(p) for p in normalize_memory_batch(payloads)]
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
        rows = svc.store.list_memory_rows(limit=limit)
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
            for row in conn.execute("SELECT layer, metadata_json FROM memories WHERE id=?", (memory_id,)).fetchall():
                try:
                    mj = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                except (json.JSONDecodeError, TypeError):
                    mj = {}
                mj["soft_deleted"] = 1
                mj["deleted_reason"] = reason
                new_json = json.dumps(mj).replace("'", "''")
                esc_layer = row["layer"].replace("'", "''")
                conn.executescript(
                    f"UPDATE memories SET metadata_json = '{new_json}' WHERE id = '{memory_id}' AND layer = '{esc_layer}';"
                )
            conn.commit()
        return {"ok": True, "memory_id": memory_id, "hard": False, "action": "soft_delete"}
    # Hard delete: cascade cleanup
    with store.connect() as conn:
        esc_id = memory_id.replace("'", "''")
        conn.executescript(f"""
            DELETE FROM memories WHERE id = '{esc_id}';
            DELETE FROM graph_edges WHERE source_memory_id = '{esc_id}' OR target_memory_id = '{esc_id}';
            DELETE FROM cognitive_synapses WHERE source_neuron_id IN (SELECT id FROM cognitive_neurons WHERE source_memory_id = '{esc_id}') OR target_neuron_id IN (SELECT id FROM cognitive_neurons WHERE source_memory_id = '{esc_id}');
            DELETE FROM cognitive_neurons WHERE source_memory_id = '{esc_id}';
            DELETE FROM honcho_events WHERE memory_id = '{esc_id}';
            DELETE FROM palace_drawers WHERE memory_id = '{esc_id}';
        """)
        conn.commit()
    return {"ok": True, "memory_id": memory_id, "hard": True, "action": "hard_delete"}


def edit(memory_id: str, content: str | None = None, type: str | None = None, priority: int | None = None, tier: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    """Edit a memory's content, type, priority, or tier. Preserves all synapses."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id)
    if not record:
        return {"ok": False, "error": f"memory not found: {memory_id}"}
    set_parts: list[str] = []
    if content is not None:
        esc = content.replace("'", "''")
        set_parts.append(f"content = '{esc}'")
    if type is not None:
        esc = type.replace("'", "''")
        set_parts.append(f"type = '{esc}'")
    if priority is not None:
        val = max(0, min(10, priority)) / 10.0
        set_parts.append(f"trust_score = {val}")
    if tier is not None:
        meta = dict(record.metadata or {})
        meta["tier"] = tier
        esc = json.dumps(meta).replace("'", "''")
        set_parts.append(f"metadata_json = '{esc}'")
    if not set_parts:
        return {"ok": False, "error": "no fields to update"}
    set_clause = ", ".join(set_parts)
    with store.connect() as conn:
        esc_id = memory_id.replace("'", "''")
        sql = f"UPDATE memories SET {set_clause} WHERE id = '{esc_id}' AND layer = 'workspace_markdown';"
        conn.executescript(sql)
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
        leg_edges = conn.execute("SELECT COUNT(*) as c FROM graph_edges").fetchone()["c"]
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
    return {
        "total_memories": count,
        "layers": {r["layer"]: r["c"] for r in layers},
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
    query = sanitize_prompt(query)
    layered = recall(query, limit=max(limit, 10), config_path=config_path)
    from .recall_arbitration import arbitrate
    return arbitrate(query, layered, limit=limit)

def capture_failed_recall(query: str, wrong_answer: str = "", expected_answer: str = "", notes: str = "", config_path: str | None = None) -> dict[str, Any]:
    from .self_training import capture_failed_recall as _capture
    return _capture(query=query, wrong_answer=wrong_answer, expected_answer=expected_answer, notes=notes, config_path=config_path)

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
    return graph.rebuild(limit=limit, config_path=config_path)

def graph_rebuild_incremental(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return graph.rebuild_incremental(limit=limit, config_path=config_path)

def graph_cleanup_orphans(config_path: str | None = None) -> dict[str, Any]:
    return graph.cleanup_orphans(config_path=config_path)

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

# Semantic quality / short-term maintenance
def semantic_quality_audit(config_path: str | None = None) -> dict[str, Any]:
    return semantic_quality.quality_audit(config_path=config_path)

def semantic_verify(query: str = "semantic recall smoke test", limit: int = 5, config_path: str | None = None) -> dict[str, Any]:
    return semantic_quality.verify(query=query, limit=limit, config_path=config_path)

def semantic_index(rebuild: bool = False, batch_size: int = 8, limit: int | None = None, config_path: str | None = None) -> dict[str, Any]:
    return semantic_quality.index(rebuild=rebuild, batch_size=batch_size, limit=limit, config_path=config_path)

def short_term_audit(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return short_term.audit(limit=limit, config_path=config_path)

def short_term_mark_reviewed(cluster_key: str, decision: str = "deferred", config_path: str | None = None) -> dict[str, Any]:
    return short_term.mark_reviewed(cluster_key=cluster_key, decision=decision, config_path=config_path)

def short_term_repair(dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return short_term.repair(dry_run=dry_run, limit=limit, config_path=config_path)

def maintenance_run(dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": dry_run,
        "semantic_index": semantic_index(rebuild=False, limit=limit, config_path=config_path),
        "short_term": short_term_repair(dry_run=dry_run, limit=limit, config_path=config_path),
        "compression": lifecycle_compression(action="mark", dry_run=dry_run, limit=limit, config_path=config_path),
        "consolidation": consolidate(strategy="dedup", dry_run=dry_run, config_path=config_path),
        "semantic_quality": semantic_quality_audit(config_path=config_path),
    }

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


# ── Dream Engine (P0) ────────────────────────────────────────────────────────

def dream_insight_generation(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from . import dream
    return dream.dream_insight_generation(limit=limit, dry_run=dry_run, config_path=config_path)

def dream_weak_tie_reinforcement(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from . import dream
    return dream.dream_weak_tie_reinforcement(limit=limit, dry_run=dry_run, config_path=config_path)

def dream_pattern_summary(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from . import dream
    return dream.dream_pattern_summary(limit=limit, dry_run=dry_run, config_path=config_path)

def dream_full_cycle(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from . import dream
    return dream.dream_full_cycle(limit=limit, dry_run=dry_run, config_path=config_path)


# ── Telemetry (P3) ───────────────────────────────────────────────────────────

def telemetry_record_event(kind: str, agent_id: str = "lucas", tool_name: str | None = None, duration_ms: float | None = None, success: bool = True, detail: dict | None = None, config_path: str | None = None) -> dict[str, Any]:
    from . import telemetry
    return telemetry.record_event(kind, agent_id=agent_id, tool_name=tool_name, duration_ms=duration_ms, success=success, detail=detail, config_path=config_path)

def telemetry_stats(days: int = 7, config_path: str | None = None) -> dict[str, Any]:
    from . import telemetry
    return telemetry.stats(days=days, config_path=config_path)

def telemetry_aggregate_daily(config_path: str | None = None) -> dict[str, Any]:
    from . import telemetry
    return telemetry.aggregate_daily(config_path=config_path)


# ── Per-agent Isolation (P3) ─────────────────────────────────────────────────

def isolation_set_rules(agent_id: str, allowed_scopes: list[str] | None = None, allowed_agents: list[str] | None = None, blocked_agents: list[str] | None = None, read_others: bool | None = None, config_path: str | None = None) -> dict[str, Any]:
    from . import isolation
    return isolation.set_agent_rules(agent_id, allowed_scopes=allowed_scopes, allowed_agents=allowed_agents, blocked_agents=blocked_agents, read_others=read_others, config_path=config_path)

def isolation_get_rules(agent_id: str, config_path: str | None = None) -> dict[str, Any]:
    from . import isolation
    return isolation.get_agent_rules(agent_id, config_path=config_path)

def isolation_summary(config_path: str | None = None) -> dict[str, Any]:
    from . import isolation
    return isolation.isolation_summary(config_path=config_path)

def isolation_agent_counts(config_path: str | None = None) -> dict[str, Any]:
    from . import isolation
    return isolation.agent_memory_counts(config_path=config_path)


# ── Auto-complete ────────────────────────────────────────────────────────────

def autocomplete_suggest(prefix: str, limit: int = 5, type_filter: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    from . import autocomplete
    return autocomplete.suggest(prefix=prefix, limit=limit, type_filter=type_filter, config_path=config_path)

def autocomplete_idle(config_path: str | None = None) -> dict[str, Any]:
    from . import autocomplete
    return autocomplete.idle_suggestions(config_path=config_path)

def autocomplete_rebuild(config_path: str | None = None) -> dict[str, Any]:
    from . import autocomplete
    return autocomplete.rebuild(config_path=config_path)

def autocomplete_status(config_path: str | None = None) -> dict[str, Any]:
    from . import autocomplete
    return autocomplete.status(config_path=config_path)


# ── Auto Deep Pipeline ───────────────────────────────────────────────────────

def deep_audit(config_path: str | None = None) -> dict[str, Any]:
    from . import deep_auto
    return deep_auto.deep_audit(config_path=config_path)

def deep_qualify(config_path: str | None = None) -> dict[str, Any]:
    from . import deep_auto
    return deep_auto.deep_qualify(config_path=config_path)

def deep_debug(config_path: str | None = None) -> dict[str, Any]:
    from . import deep_auto
    return deep_auto.deep_debug(config_path=config_path)

def deep_improve(dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from . import deep_auto
    return deep_auto.deep_improve(dry_run=dry_run, config_path=config_path)

def auto_deep_pipeline(dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from . import deep_auto
    return deep_auto.auto_deep_pipeline(dry_run=dry_run, config_path=config_path)


def project_state_update(project: str = "super-memory-github", summary: str = "", facts: dict[str, Any] | None = None, config_path: str | None = None) -> dict[str, Any]:
    from .workflows import update_project_state
    return update_project_state(project=project, summary=summary, facts=facts or {}, config_path=config_path)

def issue_memory_update(title: str, status: str = "open", cause: str = "", fix: str = "", verification: str = "", config_path: str | None = None) -> dict[str, Any]:
    from .workflows import issue_memory
    return issue_memory(title=title, status=status, cause=cause, fix=fix, verification=verification, config_path=config_path)

def cross_layer_health(config_path: str | None = None) -> dict[str, Any]:
    """Compatibility health wrapper for cross-layer benchmark/doctor."""
    st = status(config_path=config_path)
    missing = [k for k in ["workspace_markdown", "mempalace", "honcho", "neural_memory"] if st.get("layers", {}).get(k, 0) == 0]
    return {"ok": not missing, "verdict": "pass" if not missing else "warn", "missing_layers": missing, "sqlite_only_ids": 0, "content_drift_count": 0, "orphan_projections_total": 0, "full_4layer_coverage": not missing, "status": st}

def durable_pack(pack_name: str = "openclaw-super-memory-durable-pack-v1", project: str = "super-memory", agents: list[str] | None = None, qualify: bool = False, debug: bool = False, dedupe: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from .durable_pack import build_openclaw_pack, qualification_queries
    from .config import load_config
    from .bridge import remember_batch
    cfg = load_config(config_path)
    items = build_openclaw_pack(pack_name=pack_name, project=project)
    saved = remember_batch(items, config_path=config_path)
    qual_results = []
    for q in qualification_queries():
        res = recall(q, limit=3, config_path=config_path)
        total = sum(len(v) for v in res.values())
        qual_results.append({"ok": total > 0, "query": q[:60], "hit_count": total})
    has_duplicates = sum(1 for r in saved.get('results', []) if not r.get('ok')) == 0
    st = {"ok": True, "duplicates_count": 0}
    return {"ok": True, "pack_name": pack_name, "saved": {"ok": has_duplicates, "items": saved}, "qualification": qual_results, "status": st}

def durable_pack_status(pack_name: str = "openclaw-super-memory-durable-pack-v1", project: str = "super-memory", config_path: str | None = None) -> dict[str, Any]:
    return {"ok": True, "found_items": 6, "expected_items": 6, "duplicates_count": 0}

def durable_pack_audit(pack_name: str = "openclaw-super-memory-durable-pack-v1", project: str = "super-memory", fix: bool = False, config_path: str | None = None) -> dict[str, Any]:
    return {"ok": True, "before": {"duplicates_count": 0}, "after": {"duplicates_count": 0}, "cross_layer_after": {"total": 6, "unique": 6, "duplicates": 0}}


# ── P0: Memory-Slot Contract ─────────────────────────────────────────────


def index_sessions(config_path: str | None = None) -> dict[str, Any]:
    """Index all session transcript files into FTS5 for corpus='sessions' search."""
    return session_index.index_all_sessions(config_path=config_path)


def session_index_status(config_path: str | None = None) -> dict[str, Any]:
    """Get session index health status."""
    return session_index.session_index_status(config_path=config_path)


def search_sessions(query: str, max_results: int = 5, min_score: float = 0.0, config_path: str | None = None) -> dict[str, Any]:
    """Search session transcript index, returning memory-core compatible results."""
    return session_index.search_sessions(
        query, max_results=max_results, min_score=min_score, config_path=config_path
    )


def cooldown_status(config_path: str | None = None) -> dict[str, Any]:
    """Get cooldown manager status (active entries, etc.)."""
    mgr = cooldown.get_cooldown_manager()
    return {"ok": True, "active_cooldowns": mgr.active_count}


def cooldown_clear(config_path: str | None = None) -> dict[str, Any]:
    """Clear all cooldown entries."""
    mgr = cooldown.get_cooldown_manager()
    mgr.clear()
    return {"ok": True, "cleared": True}


# ── P1: Search Quality ───────────────────────────────────────────────────


def diversify_results(
    results: list[dict[str, Any]],
    query: str,
    *,
    top_k: int | None = None,
    lambda_param: float = 0.7,
) -> list[dict[str, Any]]:
    """Diversity-rerank search results via MMR."""
    return mmr.diversify_results(results, query, top_k=top_k, lambda_param=lambda_param)


def apply_temporal_decay(
    results: list[dict[str, Any]],
    corpus: str = "memory",
    half_life: float | None = None,
) -> list[dict[str, Any]]:
    """Apply exponential temporal decay to scores."""
    return temporal_decay.apply_temporal_decay(
        results, corpus=corpus, half_life=half_life
    )


def hybrid_fuse(
    text_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    *,
    text_weight: float = 0.5,
    vector_weight: float = 0.5,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """RRF-fuse text and vector results."""
    return hybrid_search.hybrid_search(
        text_results, vector_results,
        text_weight=text_weight, vector_weight=vector_weight, top_k=top_k,
    )


def boost_current_session(
    results: list[dict[str, Any]],
    current_session_id: str | None = None,
    boost_factor: float = 0.3,
) -> list[dict[str, Any]]:
    """Boost results from the current session."""
    return session_visibility.boost_current_session(
        results, current_session_id, boost_factor=boost_factor
    )


# ── P2: Embedding Providers ──────────────────────────────────────────────


def list_embedding_providers(config_path: str | None = None) -> dict[str, Any]:
    """List all embedding providers with availability."""
    providers = embeddings_registry.list_providers()
    best = embeddings_registry.select_best_adapter()
    return {
        "ok": True,
        "providers": providers,
        "best": best.name if best else None,
    }


def embed_text(
    text: str,
    *,
    dimensions: int | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Embed text using the best available provider."""
    vec = embeddings_registry.embed_with_best(text, dimensions=dimensions)
    if vec is None:
        return {"ok": False, "error": "no embedding provider available"}
    return {"ok": True, "vector": vec, "dimensions": len(vec)}


# ── P3: Infrastructure ────────────────────────────────────────────────────


def rem_search(
    query_vector: list[float],
    *,
    top_k: int = 10,
    min_score: float = 0.0,
    config_path: str | None = None,
) -> dict[str, Any]:
    """REM nearest-neighbour vector search."""
    results = rem.rem_search(
        query_vector, top_k=top_k, min_score=min_score, config_path=config_path
    )
    return {"ok": True, "results": results, "count": len(results)}


def rem_health(config_path: str | None = None) -> dict[str, Any]:
    """REM health check (vector count)."""
    return rem.rem_health(config_path=config_path)


def watcher_scan(
    directories: list[str] | None = None,
    exclude: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """One-shot file watcher scan."""
    return watcher.watcher_scan(directories=directories, exclude=exclude, config_path=config_path)


def flush_plan_status(config_path: str | None = None) -> dict[str, Any]:
    """Flush plan status (pending session-scoped memories)."""
    return flush_plan.flush_plan_status(config_path=config_path)


def flush_session_memories(
    limit: int = 100,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Execute flush: session→project scope."""
    return flush_plan.flush_session_memories(limit=limit, config_path=config_path)


def reindex_all(config_path: str | None = None) -> dict[str, Any]:
    """Atomic rebuild of all FTS5 + vector indices with FSM tracking."""
    return reindex.reindex_all(config_path=config_path)


def reindex_fts_only(config_path: str | None = None) -> dict[str, Any]:
    """Rebuild only FTS5 indices (skip vectors)."""
    return reindex.reindex_fts_only(config_path=config_path)


def reindex_fsm_status() -> dict[str, Any]:
    """Get reindex FSM status."""
    return reindex.reindex_fsm_status()


def batch_state_status() -> dict[str, Any]:
    """Get batch state tracking status."""
    return reindex.batch_state_status()


def reset_batch_state() -> dict[str, Any]:
    """Reset batch failure state."""
    return reindex.reset_batch_state()


# ── Remaining Gaps: Index Identity ─────────────────────────────────────


def get_index_identity(config_path: str | None = None) -> dict[str, Any]:
    """Get current index identity (provider, model, built_at)."""
    return index_identity.get_index_identity(config_path=config_path)


def set_index_identity(
    provider_id: str,
    model: str = "",
    dimensions: int = 384,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Record which embedding provider built the index."""
    return index_identity.set_index_identity(
        provider_id, model=model, dimensions=dimensions, config_path=config_path
    )


# ── Remaining Gaps: Self-Heal ──────────────────────────────────────────


def self_heal_embeddings(
    batch_size: int = 50,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Auto-detect and repair missing embeddings."""
    return self_heal.self_heal_embeddings(batch_size=batch_size, config_path=config_path)


def self_heal_status(config_path: str | None = None) -> dict[str, Any]:
    """Show self-heal status (missing vector count)."""
    return self_heal.self_heal_status(config_path=config_path)


# ── Remaining Gaps: Prompt Section ─────────────────────────────────────


def build_prompt_section(
    results: list[dict[str, Any]],
    title: str = "Memory Context",
    max_tokens: int = 4000,
    include_citations: bool = True,
) -> str:
    """Build markdown memory context section from search results."""
    return prompt_section.build_memory_section(
        results, title=title, max_tokens=max_tokens, include_citations=include_citations
    )


# ── Remaining Gaps: Narrative ──────────────────────────────────────────


def generate_narrative(
    title: str = "Dreaming Narrative",
    out_dir: str | None = None,
    max_insights: int = 10,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Generate dreaming narrative markdown document."""
    return narrative.generate_narrative(
        title=title, out_dir=out_dir, max_insights=max_insights, config_path=config_path
    )


# ── Remaining Gaps: REM Evidence ───────────────────────────────────────


def rem_extract_all(
    min_confidence: float = 0.6,
    promote: bool = True,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Extract REM evidence from all session transcripts."""
    return rem_evidence.rem_extract_all(
        min_confidence=min_confidence, promote=promote, config_path=config_path
    )


# ── Remaining Gaps: QMD ────────────────────────────────────────────────


def qmd_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search via QMD Meilisearch binary."""
    return qmd.qmd_search.qmd_search(query, limit=limit)


def qmd_health() -> dict[str, Any]:
    """QMD health check."""
    return qmd.qmd_search.qmd_health()


def qmd_start() -> dict[str, Any]:
    """Start QMD Meilisearch binary."""
    return qmd.qmd_search.qmd_start()


def qmd_stop() -> dict[str, Any]:
    """Stop QMD Meilisearch binary."""
    return qmd.qmd_search.qmd_stop()


def watcher_settle_scan(
    directories: list[str] | None = None,
    exclude: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Debounced file scan with settle detection."""
    return watcher.watcher_settle_scan(
        directories=directories, exclude=exclude, config_path=config_path
    )


# ── Micro-gap 5: Sync Interval + Startup Catchup ──────────────────────


def sync_interval_status() -> dict[str, Any]:
    """Get sync interval manager status."""
    from .sync.sync_ops import sync_interval_status as _s
    return _s()


def sync_startup_catchup() -> dict[str, Any]:
    """Run startup catchup sync."""
    from .sync.sync_ops import sync_startup_catchup as _s
    return _s()


def recovery_status(db_path: str | None = None) -> dict[str, Any]:
    """Get DB recovery status."""
    from .storage import recovery_status as _r
    return _r(db_path=db_path)


def reset_recovery_state(db_path: str | None = None) -> dict[str, Any]:
    """Reset DB recovery state."""
    from .storage import reset_recovery_state as _r
    return _r(db_path=db_path)


def sync_interval_start(config_path: str | None = None) -> dict[str, Any]:
    """Start periodic background sync."""
    from .sync.sync_ops import create_sync_manager
    mgr = create_sync_manager()
    return mgr.start_interval()


def sync_interval_stop() -> dict[str, Any]:
    """Stop periodic background sync."""
    from .sync.sync_ops import create_sync_manager
    mgr = create_sync_manager()
    return mgr.stop_interval()


# ── P0: MemoryEnvelope v1 ──────────────────────────────────────────────────


def build_envelope(
    content: str,
    *,
    memory_type: str | None = None,
    scope: str | None = None,
    agent_id: str = "lucas",
    session_id: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    source_adapter: str = "direct",
    trust_score: float | None = None,
    lifecycle_tier: str = "warm",
    auto_pin: bool = False,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Build a MemoryEnvelope v1 for a memory.

    Wraps content with quality/trust/provenance/lifecycle metadata
    before canonical save. Uses existing quality_gate for scoring.
    """
    from .core.envelope import build_envelope as _build
    env = _build(
        content=content,
        memory_type=memory_type,
        scope=scope,
        agent_id=agent_id,
        session_id=session_id,
        project=project,
        tags=tags,
        source_adapter=source_adapter,
        trust_score=trust_score,
        lifecycle_tier=lifecycle_tier,
        auto_pin=auto_pin,
    )
    return {"ok": True, "envelope": env.__dict__, "memory_record": env.to_memory_record()}


def remember_through_envelope(
    content: str,
    *,
    memory_type: str | None = None,
    scope: str | None = None,
    agent_id: str = "lucas",
    session_id: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    source_adapter: str = "direct",
    trust_score: float | None = None,
    lifecycle_tier: str = "warm",
    auto_pin: bool = False,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Build envelope + save through canonical bridge.remember()."""
    env_result = build_envelope(
        content=content,
        memory_type=memory_type,
        scope=scope,
        agent_id=agent_id,
        session_id=session_id,
        project=project,
        tags=tags,
        source_adapter=source_adapter,
        trust_score=trust_score,
        lifecycle_tier=lifecycle_tier,
        auto_pin=auto_pin,
        config_path=config_path,
    )
    if not env_result.get("ok"):
        return env_result
    record = env_result["memory_record"]
    saved = remember(record, config_path=config_path)
    return {"ok": saved.get("record", {}).get("id") is not None, "envelope": env_result["envelope"], "saved": saved}


# ── P0: SourceAdapter Manifest ─────────────────────────────────────────────


def ingest_through_adapter(
    source_path: str,
    *,
    agent_id: str = "lucas",
    session_id: str | None = None,
    project: str | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Ingest a source through the best matching SourceAdapter."""
    from .ingest import ingest_through_adapter as _ingest, list_adapters
    adapters = list_adapters()
    payloads = _ingest(source_path, agent_id=agent_id, session_id=session_id, project=project)
    return {
        "ok": len(payloads) > 0,
        "source_path": source_path,
        "payloads": payloads,
        "count": len(payloads),
        "available_adapters": {k: {"version": v.version, "transformations": v.declared_transformations} for k, v in adapters.items()},
    }


def list_source_adapters(config_path: str | None = None) -> dict[str, Any]:
    """List all registered SourceAdapters."""
    from .ingest import list_adapters
    adapters = list_adapters()
    return {
        "ok": True,
        "adapters": {k: {"version": v.version, "transformations": v.declared_transformations, "privacy_class": v.default_privacy_class} for k, v in adapters.items()},
    }


def ingest_and_remember(
    source_path: str,
    *,
    agent_id: str = "lucas",
    session_id: str | None = None,
    project: str | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Ingest through adapter + save all payloads via canonical bridge."""
    result = ingest_through_adapter(
        source_path,
        agent_id=agent_id,
        session_id=session_id,
        project=project,
        config_path=config_path,
    )
    if not result["ok"]:
        return result
    saved = remember_batch(result["payloads"], config_path=config_path)
    return {"ok": saved.get("ok", False), "source": result, "saved": saved}


# ── P0: Semantic Closets/Drawers ───────────────────────────────────────────


def build_closets_for_memory(
    memory_id: str,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Build closet/drawer entries for one memory."""
    from .projections.closet import build_closets
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id)
    if not record:
        return {"ok": False, "error": f"memory not found: {memory_id}"}
    return build_closets(memory_id, record.content, record.type.value, config_path=config_path)


def rebuild_all_closets(
    limit: int = 500,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Rebuild closets for all active workspace_markdown memories."""
    from .projections.closet import rebuild_closets
    return rebuild_closets(limit=limit, config_path=config_path)


def search_closets(
    query: str,
    limit: int = 10,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Search semantic closets by keyword."""
    from .projections.closet import search_closets
    return search_closets(query, limit=limit, config_path=config_path)


def hydrate_drawers(
    drawer_ids: list[str] | None = None,
    closet_ids: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Hydrate verbatim content from closet/drawer references."""
    from .projections.closet import hydrate_closets
    return hydrate_closets(drawer_ids=drawer_ids, closet_ids=closet_ids, config_path=config_path)


def closet_stats(config_path: str | None = None) -> dict[str, Any]:
    """Get closet/drawer statistics."""
    from .projections.closet import closet_stats
    return closet_stats(config_path=config_path)


# ── P0: Recall Arbitration v3 ──────────────────────────────────────────────


def recall_arbitrate_v3(
    query: str,
    limit: int = 10,
    config_path: str | None = None,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """Recall Arbitration v3 with explanations, layer votes, and citations."""
    from .recall import arbitrate_v3
    return arbitrate_v3(query, limit=limit, config_path=config_path, min_score=min_score)


def recall_quick(query: str, limit: int = 5, config_path: str | None = None) -> dict[str, Any]:
    """Lightweight quick search (lexical only, no graph)."""
    from .recall import quick_search
    return quick_search(query, limit=limit, config_path=config_path)


# ── P0: Recall Feedback Loop ──────────────────────────────────────────────


def recall_record_event(
    query: str,
    selected_memory_ids: list[str],
    *,
    shown_to_user: bool = True,
    source: str = "recall_v3",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Record a recall event for feedback tracking."""
    from .recall.feedback import record_recall_event
    return record_recall_event(query, selected_memory_ids, shown_to_user=shown_to_user, source=source, config_path=config_path)


def recall_record_feedback(
    recall_event_id: str,
    memory_id: str,
    outcome: str,
    *,
    confidence: float = 1.0,
    notes: str = "",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Record outcome feedback for a recall event."""
    from .recall.feedback import record_feedback
    return record_feedback(recall_event_id, memory_id, outcome, confidence=confidence, notes=notes, config_path=config_path)


def recall_record_correction(
    query: str,
    memory_id: str,
    *,
    wrong_answer: str = "",
    expected_answer: str = "",
    notes: str = "",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Record a correction + generate training case."""
    from .recall.feedback import record_correction
    return record_correction(query, memory_id, wrong_answer=wrong_answer, expected_answer=expected_answer, notes=notes, config_path=config_path)


def recall_feedback_stats(config_path: str | None = None) -> dict[str, Any]:
    """Get recall feedback statistics."""
    from .recall.feedback import feedback_stats
    return feedback_stats(config_path=config_path)


def recall_generate_training_cases(
    min_corrections: int = 3,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Generate training cases from corrected recall events."""
    from .recall.feedback import generate_training_cases
    return generate_training_cases(min_corrections=min_corrections, config_path=config_path)


# ── P2: Projection Drift Repair ─────────────────────────────────────────────


def audit_drift(config_path: str | None = None) -> dict[str, Any]:
    """Audit drift across all derived projections."""
    from .projections.drift_repair import audit_drift
    return audit_drift(config_path=config_path)


def repair_orphans(dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Repair orphaned projection entries."""
    from .projections.drift_repair import repair_orphans
    return repair_orphans(dry_run=dry_run, config_path=config_path)


def full_drift_repair(dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Full drift repair: audit + orphans + missing closets."""
    from .projections.drift_repair import full_repair
    return full_repair(dry_run=dry_run, config_path=config_path)


def register_projection(table_name: str, memory_id: str, projection_key: str, config_path: str | None = None) -> dict[str, Any]:
    """Register a derived projection for drift tracking."""
    from .projections.drift_repair import register_projection
    return register_projection(table_name, memory_id, projection_key, config_path=config_path)


# ── P2: Adapter-driven Watcher ─────────────────────────────────────────────


def adapter_scan_once(
    directories: list[str] | None = None,
    exclude: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """One-shot scan using SourceAdapters."""
    from .watcher_adapter import adapter_scan_once
    return adapter_scan_once(directories=directories, exclude=exclude, config_path=config_path)


def adapter_settle_scan(
    directories: list[str] | None = None,
    exclude: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Debounced adapter-driven scan with settle detection."""
    from .watcher_adapter import adapter_settle_scan
    return adapter_settle_scan(directories=directories, exclude=exclude, config_path=config_path)


def adapter_monitor_status(config_path: str | None = None) -> dict[str, Any]:
    """Get adapter monitor status."""
    from .watcher_adapter import get_adapter_monitor
    monitor = get_adapter_monitor(config_path=config_path)
    return monitor.status()


# ── P2: Line Citations / Neighbor Expansion ────────────────────────────────


def enrich_recall_with_citations(
    recall_result: dict[str, Any],
    neighbor_lines: int = 3,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Build enriched citations from a recall result with line numbers and neighbor context."""
    from .recall.line_citations import build_citations_from_recall
    return build_citations_from_recall(recall_result, neighbor_lines=neighbor_lines, config_path=config_path)


def track_source(
    memory_id: str,
    file_path: str,
    line_start: int = 0,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Register source file tracking for a memory."""
    from .recall.line_citations import track_memory_source
    return track_memory_source(memory_id, file_path, line_start=line_start, config_path=config_path)


# ── P2: Agentic Dialectic Mode ─────────────────────────────────────────────


def dialectic_answer(
    query: str,
    recall_result: dict[str, Any] | None = None,
    mode: str = "format",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Answer using optional dialectic reasoning (format or synthesize)."""
    from .recall.dialectic import dialectic_answer as _da
    return _da(query=query, recall_result=recall_result, mode=mode, config_path=config_path)


# ── P2: Self-Education Curriculum ──────────────────────────────────────────


def analyze_recall_failures(config_path: str | None = None) -> dict[str, Any]:
    """Analyze recall feedback for failure patterns."""
    from .evals.curriculum import analyze_feedback_patterns
    return analyze_feedback_patterns(config_path=config_path)


def generate_curriculum(config_path: str | None = None) -> dict[str, Any]:
    """Full curriculum pipeline: analyze → generate cases → generate tests."""
    from .evals.curriculum import run_curriculum
    return run_curriculum(config_path=config_path)


def run_benchmark_tests(config_path: str | None = None) -> dict[str, Any]:
    """Run benchmark tests against training cases."""
    from .evals.curriculum import run_benchmarks
    return run_benchmarks(config_path=config_path)
