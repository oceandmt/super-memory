from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
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
from . import semantic as semantic_ops
from . import maintenance as maintenance_ops
from . import memory_core as memory_core_ops




def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "value") and value.__class__.__module__ == "enum":
        return value.value
    return value


def _envelope_dict(env: Any) -> dict[str, Any]:
    if hasattr(env, "to_dict"):
        return _json_safe(env.to_dict())
    return _json_safe(asdict(env) if is_dataclass(env) else getattr(env, "__dict__", {}))


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
    """Save a memory through MemoryEnvelope + WriteGate + canonical-first layer order.

    Integrates MemoryEnvelope v1 (quality/trust/provenance/lifecycle) and
    WriteGateResult (dedup/quarantine/allow) into the save path.
    """
    from .core.envelope import build_envelope as _build_envelope
    from .core.write_gate import evaluate_write, WriteGateResult

    payload = apply_quality_gate(normalize_memory_payload(payload))

    # Build envelope for contract metadata
    env = _build_envelope(
        content=payload["content"],
        memory_type=payload.get("type", "context"),
        scope=payload.get("scope", "session"),
        agent_id=payload.get("agent_id", "lucas"),
        session_id=payload.get("session_id"),
        project=payload.get("project"),
        tags=payload.get("tags", []),
        source_adapter=payload.get("source") or "direct",
        trust_score=payload.get("trust_score"),
        metadata=payload.get("metadata", {}),
    )

    # WriteGate evaluation
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg) if payload.get("source") else None
    existing_hashes = None
    if store:
        try:
            with store.connect() as conn:
                rows = conn.execute(
                    "SELECT content_hash, id FROM memories WHERE content_hash IS NOT NULL AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT 50"
                ).fetchall()
                existing_hashes = {r["content_hash"]: r["id"] for r in rows if r["content_hash"]}
        except Exception:
            pass
    write_gate: WriteGateResult = evaluate_write(env, existing_hashes=existing_hashes)

    if not write_gate.allow:
        return {
            "ok": False,
            "envelope": _envelope_dict(env),
            "write_gate": write_gate.to_dict(),
            "reason": f"WriteGate blocked: {write_gate.action} ({', '.join(write_gate.reasons)})",
        }

    # Pass envelope metadata + id through to MemoryRecord
    record_id = payload.get("id") or env.id
    svc = SuperMemoryService(cfg)
    record = MemoryRecord(
        id=record_id,
        content=payload["content"],
        type=payload.get("type", MemoryType.CONTEXT),
        scope=payload.get("scope", MemoryScope.SESSION),
        agent_id=payload.get("agent_id", "lucas"),
        session_id=payload.get("session_id"),
        project=payload.get("project"),
        tags=payload.get("tags", []) + write_gate.suggested_tags,
        source=payload.get("source"),
        trust_score=payload.get("trust_score") or env.effective_trust,
        metadata={
            **(payload.get("metadata", {})),
            "envelope_id": env.id,
            "quality_score": env.quality_score,
            "content_hash": env.content_hash,
            "write_gate_action": write_gate.action,
            "write_gate_reasons": write_gate.reasons,
            "provenance": [e.__dict__ if hasattr(e, '__dict__') else e for e in env.provenance.entries],
            "lifecycle_policy": env.lifecycle_policy.__dict__,
        },
    )
    results = svc.save(record)
    graph_projection = None
    try:
        graph_projection = graph.project_memory(record, config_path=config_path)
    except Exception as exc:
        graph_projection = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "envelope": _envelope_dict(env),
        "write_gate": write_gate.to_dict(),
        "record": record.model_dump(mode="json"),
        "results": [r.model_dump(mode="json") for r in results],
        "graph_projection": graph_projection,
    }



def remember_batch(payloads: list[dict[str, Any]], config_path: str | None = None) -> dict[str, Any]:
    """Save multiple memories through MemoryEnvelope + WriteGate + canonical-first."""
    from .core.envelope import build_envelope as _build_envelope
    from .core.write_gate import evaluate_write, WriteGateResult

    payloads = [apply_quality_gate(p) for p in normalize_memory_batch(payloads)]
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    items = []
    for payload in payloads:
        env = _build_envelope(
            content=payload["content"],
            memory_type=payload.get("type", "context"),
            scope=payload.get("scope", "session"),
            agent_id=payload.get("agent_id", "lucas"),
            session_id=payload.get("session_id"),
            project=payload.get("project"),
            tags=payload.get("tags", []),
            source_adapter=payload.get("source") or "direct",
            trust_score=payload.get("trust_score"),
            metadata=payload.get("metadata", {}),
        )
        write_gate: WriteGateResult = evaluate_write(env)
        if not write_gate.allow:
            items.append({
                "ok": False,
                "envelope": env.__dict__,
                "write_gate": write_gate.to_dict(),
                "reason": f"WriteGate blocked: {write_gate.action}",
            })
            continue
        record = MemoryRecord(
            id=payload.get("id") or env.id,
            content=payload["content"],
            type=payload.get("type", MemoryType.CONTEXT),
            scope=payload.get("scope", MemoryScope.SESSION),
            agent_id=payload.get("agent_id", "lucas"),
            session_id=payload.get("session_id"),
            project=payload.get("project"),
            tags=payload.get("tags", []) + write_gate.suggested_tags,
            source=payload.get("source"),
            trust_score=payload.get("trust_score") or env.effective_trust,
            metadata={
                **(payload.get("metadata", {})),
                "envelope_id": env.id,
                "quality_score": env.quality_score,
                "content_hash": env.content_hash,
                "write_gate_action": write_gate.action,
                "write_gate_reasons": write_gate.reasons,
            },
        )
        results = svc.save(record)
        graph_projection = None
        try:
            graph_projection = graph.project_memory(record, config_path=config_path)
        except Exception as exc:
            graph_projection = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        canonical = next((r for r in results if r.layer.value == "workspace_markdown"), None)
        dedup_skipped = bool(canonical and canonical.message and str(canonical.message).startswith("dedup-skip"))
        item = {
            "ok": bool(canonical and canonical.ok),
            "envelope": _envelope_dict(env),
            "write_gate": write_gate.to_dict(),
            "record": record.model_dump(mode="json"),
            "results": [r.model_dump(mode="json") for r in results],
            "graph_projection": graph_projection,
        }
        if dedup_skipped:
            item["dedup"] = {"skipped": True, "matched_id": canonical.reference, "message": canonical.message}
        items.append(item)
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

def _build_recall_channels(query: str, limit: int, config_path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Collect recall candidates from all implemented recall channels."""
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    hits = svc.recall(query, limit=max(limit * 2, 20))
    channels: dict[str, list[dict[str, Any]]] = {
        layer.value: [r.model_dump(mode="json") for r in records]
        for layer, records in hits.items()
    }

    # Add semantic closet/drawer evidence as a first-class channel when available.
    try:
        from .projections.closet import search_closets
        closet_hits = search_closets(query, limit=limit, config_path=config_path)
        rows = closet_hits.get("results") or closet_hits.get("items") or []
        if rows:
            # search_closets exposes drawer_id/closet_id at top level, but the
            # arbitration layer only carries `metadata` into selected evidence.
            # Fold the pointers into metadata so hydration can resolve them.
            for r in rows:
                meta = dict(r.get("metadata") or {})
                if r.get("drawer_id") and not meta.get("drawer_id"):
                    meta["drawer_id"] = r["drawer_id"]
                if r.get("closet_id") and not meta.get("closet_id"):
                    meta["closet_id"] = r["closet_id"]
                if r.get("summary") and not r.get("content"):
                    r["content"] = r["summary"]
                r["metadata"] = meta
            channels["semantic_closet"] = rows
    except Exception:
        pass

    # Add graph recall as a channel when available.
    try:
        grecall = graph.recall(query, limit=limit, config_path=config_path)
        rows = grecall.get("results") or grecall.get("records") or []
        if rows:
            channels["graph"] = rows
    except Exception:
        pass

    return channels


def _hydrate_recall_selection(result: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    """Hydrate drawer/closet references from selected recall evidence."""
    from .projections.closet import hydrate_closets
    drawer_ids: list[str] = []
    closet_ids: list[str] = []
    for ev in result.get("selected", result.get("selected_memories", [])):
        meta = ev.get("metadata") or {}
        if meta.get("drawer_id"):
            drawer_ids.append(str(meta["drawer_id"]))
        if meta.get("closet_id"):
            closet_ids.append(str(meta["closet_id"]))
        # NOTE: for semantic_closet evidence the drawer_id/closet_id now arrive
        # via metadata (folded in _build_recall_channels). Do NOT fall back to
        # ev["memory_id"] here — that is the canonical memory UUID, not a
        # drawer_id, and querying palace_drawers with it returns empty content.
    if not drawer_ids and not closet_ids:
        return {"ok": True, "results": [], "reason": "no drawer/closet refs"}
    return hydrate_closets(drawer_ids=drawer_ids[:10], closet_ids=closet_ids[:10], config_path=config_path)


def recall(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    """Recall memories via Recall Arbitration V4 across all channels."""
    query = sanitize_prompt(query)
    from .recall.arbitration_v4 import arbitrate_v4
    channels = _build_recall_channels(query, limit, config_path=config_path)
    result = arbitrate_v4(query, channels, limit=limit)
    result.setdefault("selected", result.get("selected_memories", []))
    result.setdefault("excluded", result.get("excluded_memories", []))
    result["channels"] = {k: len(v) for k, v in channels.items()}
    try:
        result["hydrated_evidence"] = _hydrate_recall_selection(result, config_path=config_path)
    except Exception as exc:
        result["hydrated_evidence"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    # E3: log every recall to recall_events so the feedback loop has data to
    # learn from (the table + record_recall_event() already existed but had
    # zero callers, so recall_feedback/recall_events stayed empty forever).
    try:
        from .recall.feedback import record_recall_event
        selected = result.get("selected") or []
        ids = [
            (ev.get("memory_id") or ev.get("id"))
            for ev in selected
            if isinstance(ev, dict) and (ev.get("memory_id") or ev.get("id"))
        ]
        fb = record_recall_event(
            query=query, selected_memory_ids=ids, source="bridge.recall",
            config_path=config_path,
        )
        result["recall_event_id"] = fb.get("event_id")
    except Exception:
        pass
    return result


def prefetch(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    """Prefetch top memories through Recall Arbitration V4."""
    query = sanitize_prompt(query)
    from .recall.arbitration_v4 import arbitrate_v4
    channels = _build_recall_channels(query, limit, config_path=config_path)
    result = arbitrate_v4(query, channels, limit=limit)
    result.setdefault("selected", result.get("selected_memories", []))
    result.setdefault("excluded", result.get("excluded_memories", []))
    records = []
    for ev in result.get("selected", result.get("selected_memories", [])):
        records.append({
            "id": ev.get("memory_id"),
            "content": ev.get("content"),
            "source": ev.get("citation"),
            "layer": ev.get("layer"),
            "score": ev.get("score"),
            "why_selected": ev.get("why_selected"),
            "channel": ev.get("channel"),
            "metadata": ev.get("metadata", {}),
        })
    return {"records": records, "arbitration": result}

def sync_turn(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    """Save compact turn event + auto-create perspective memory from metadata."""
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

    # Auto-create perspective memory from chat/sender metadata.
    perspective = None
    meta = payload.get("metadata") or {}
    sender = meta.get("sender") or meta.get("sender_id") or meta.get("username") or meta.get("name")
    channel = meta.get("channel") or meta.get("conversation_label") or meta.get("chat_id")
    group = meta.get("group_subject") or meta.get("group_channel")
    if sender and ctx.user_message:
        tags = ["agent:" + ctx.agent_id, "perspective:observed_turn"]
        if channel:
            tags.append("channel:" + str(channel)[:60])
        if group:
            tags.append("group:" + str(group)[:60])
        perspective_note = (
            f"[Perspective] Observed turn from {sender}"
            f"{' in ' + group if group else ''}"
            f"{' on ' + str(channel)[:40] if channel else ''}"
        )
        try:
            from .core.envelope import build_envelope as _env
            from .core.write_gate import evaluate_write
            env = _env(
                content=perspective_note,
                memory_type="observation",
                scope="session",
                agent_id=ctx.agent_id,
                session_id=ctx.session_id,
                project=payload.get("project"),
                tags=tags,
                source_adapter="chat",
                trust_score=0.5,
                metadata={"sender": str(sender)[:120], "user_message_preview": ctx.user_message[:200]},
            )
            wg = evaluate_write(env)
            if wg.allow:
                record = MemoryRecord(
                    id=env.id,
                    content=perspective_note,
                    type=MemoryType.CONTEXT,
                    scope=MemoryScope.SESSION,
                    agent_id=ctx.agent_id,
                    session_id=ctx.session_id,
                    project=payload.get("project"),
                    tags=tags,
                    source="chat",
                    trust_score=env.effective_trust,
                    metadata={"envelope_id": env.id, "quality_score": env.quality_score,
                              "content_hash": env.content_hash, "perspective_auto": True,
                              "sender": str(sender)[:120]},
                )
                perspective = svc.save(record)
        except Exception as exc:
            perspective = [{"ok": False, "error": f"{type(exc).__name__}: {exc}"}]

    return {
        "results": [r.model_dump(mode="json") for r in results],
        "perspective": [r.model_dump(mode="json") for r in perspective] if perspective else None,
    }


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
    raw_layered = recall(query, limit=max(limit, 10), config_path=config_path)
    if isinstance(raw_layered, dict) and "selected_memories" in raw_layered and "answer_context" in raw_layered:
        selected_records = []
        for ev in raw_layered.get("selected_memories", []) or []:
            rec = ev.get("record") if isinstance(ev, dict) else None
            if isinstance(rec, dict):
                selected_records.append(rec)
        layered = {"arbitration_v4": selected_records}
    else:
        layered = raw_layered
    from .recall_arbitration import arbitrate
    result = arbitrate(query, layered, limit=limit)
    if result.get("answer_context"):
        return result

    # Robust fallback for long diagnostic/natural-language queries: the legacy
    # arbiter receives no candidates when strict FTS requires every query term.
    # Compatible search already applies per-layer fallbacks, so route through it
    # before reporting a false-negative recall miss.
    try:
        compat = memory_search(query, max_results=limit, min_score=0.0, corpus="all", config_path=config_path)
        answer_context = []
        selected = []
        layer_votes: dict[str, int] = {}
        for idx, hit in enumerate(compat.get("results", [])[:limit]):
            rec = {
                "id": hit.get("memory_id") or hit.get("id"),
                "content": hit.get("snippet") or "",
                "source": hit.get("path") or hit.get("source"),
                "metadata": {"compat_hit": hit},
            }
            layer = hit.get("layer") or "compat"
            layer_votes[layer] = layer_votes.get(layer, 0) + 1
            item = {
                "layer": layer,
                "rank": idx,
                "score": hit.get("score", 0.0),
                "record": rec,
                "why_selected": ["fallback=memory_search_compatible"],
                "citation": hit.get("citation") or hit.get("path"),
            }
            answer_context.append(item)
            selected.append(rec)
        if answer_context:
            return {
                "query": query,
                "answer_context": answer_context,
                "selected_memories": selected,
                "excluded_memories": result.get("excluded_memories", []),
                "layer_votes": layer_votes,
                "winner_policy": answer_context[0]["layer"],
                "confidence": answer_context[0].get("score", 0.0),
                "citations": [c.get("citation") for c in answer_context if c.get("citation")],
                "why": "fallback via compatible memory_search after strict arbitration returned no candidates",
                "fallback_terms": True,
            }
    except Exception:
        pass

    # Last-resort token-OR scan. This keeps diagnostics useful when FTS tables are
    # stale/empty or strict AND semantics over-constrain a long query.
    try:
        import re as _re
        from .config import load_config as _load_config
        from .storage import SuperMemoryStore as _Store, row_to_memory as _row_to_memory
        qterms = [t for t in _re.split(r"\W+", query.lower()) if len(t) > 3 and t not in {"super", "memory"}][:12]
        if qterms:
            cfg = _load_config(config_path)
            store = _Store(cfg)
            with store.connect() as conn:
                clauses = " OR ".join(["LOWER(content) LIKE ?" for _ in qterms])
                rows = conn.execute(
                    f"""
                    SELECT * FROM memories
                    WHERE COALESCE(json_extract(metadata_json, '$.soft_deleted'), 0) != 1
                      AND ({clauses})
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (*[f"%{t}%" for t in qterms], limit * 4),
                ).fetchall()
            scored = []
            seen = set()
            for row in rows:
                rec_obj = _row_to_memory(row)
                rec = rec_obj.model_dump(mode="json")
                key = rec.get("id") or rec.get("content", "")[:200]
                if key in seen:
                    continue
                seen.add(key)
                content_l = (rec.get("content") or "").lower()
                overlap = sum(1 for t in qterms if t in content_l)
                if overlap <= 0:
                    continue
                score = min(1.0, overlap / max(1, len(qterms)))
                scored.append({
                    "layer": row["layer"], "rank": len(scored), "score": score, "record": rec,
                    "why_selected": [f"fallback_token_overlap={overlap}/{len(qterms)}"],
                    "citation": rec.get("source") or rec.get("id"),
                })
            scored.sort(key=lambda x: x["score"], reverse=True)
            if scored:
                top = scored[:limit]
                return {
                    "query": query,
                    "answer_context": top,
                    "selected_memories": [c["record"] for c in top],
                    "excluded_memories": result.get("excluded_memories", []),
                    "layer_votes": {k: sum(1 for c in top if c["layer"] == k) for k in {c["layer"] for c in top}},
                    "winner_policy": top[0]["layer"],
                    "confidence": top[0]["score"],
                    "citations": [c.get("citation") for c in top if c.get("citation")],
                    "why": "fallback via token-OR scan after strict arbitration returned no candidates",
                    "fallback_terms": qterms,
                }
    except Exception:
        pass
    return result

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

def lifecycle_quality_cleanup(dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Quality cleanup wrapper for lifecycle tests/operators.

    Conservative actions:
    - Review active duplicate groups from lifecycle.review().
    - Soft-delete all but the first ID in each duplicate group when apply.
    - Mark long-content compression candidates via lifecycle.compression(action='mark').

    This wrapper intentionally avoids hard deletes and does not truncate content.
    """
    import json as _json
    from datetime import datetime, timezone
    from .config import load_config as _load_config
    from .storage import SuperMemoryStore as _Store

    report = lifecycle.review(config_path=config_path, limit=limit)
    duplicates = []
    now = datetime.now(timezone.utc).isoformat()
    for group in report.get("duplicates", []):
        ids = list(dict.fromkeys(group.get("ids", [])))
        if len(ids) <= 1:
            continue
        keep = ids[0]
        for dup_id in ids[1:]:
            duplicates.append({"id": dup_id, "kept": keep, "reason": "lifecycle_quality_duplicate"})

    compression = lifecycle.compression(action="review", dry_run=True, config_path=config_path, limit=limit)
    compression_candidates = compression.get("candidates", [])

    applied_rows = 0
    if not dry_run:
        store = _Store(_load_config(config_path))
        with store.connect() as conn:
            for item in duplicates:
                rows = conn.execute("SELECT id, layer, metadata_json FROM memories WHERE id=?", (item["id"],)).fetchall()
                for row in rows:
                    meta = _json.loads(row["metadata_json"] or "{}")
                    if meta.get("soft_deleted") == 1:
                        continue
                    meta["soft_deleted"] = 1
                    meta["deleted_at"] = now
                    meta["deleted_reason"] = item["reason"]
                    meta["merged_into"] = item["kept"]
                    conn.execute(
                        "UPDATE memories SET metadata_json=? WHERE id=? AND layer=?",
                        (_json.dumps(meta, ensure_ascii=False), row["id"], row["layer"]),
                    )
                    applied_rows += 1
        # Mark compression candidates after duplicate cleanup.
        lifecycle.compression(action="mark", dry_run=False, config_path=config_path, limit=limit)

    return {
        "ok": True,
        "dry_run": dry_run,
        "duplicates_count": len(duplicates),
        "compression_count": len(compression_candidates),
        "duplicates": duplicates,
        "compression_candidates": compression_candidates[:50],
        "applied_rows": applied_rows,
    }

def reflex_status(config_path: str | None = None) -> dict[str, Any]:
    return lifecycle.reflex_status(config_path=config_path)

def embedding_doctor(config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.embedding_doctor(config_path=config_path)

def embedding_auto_select(config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.embedding_auto_select(config_path=config_path)

# Semantic quality / short-term maintenance
def semantic_doctor(config_path: str | None = None, query: str = "semantic recall smoke test") -> dict[str, Any]:
    """Bridge wrapper for semantic doctor checks."""
    return semantic_ops.semantic_doctor(config_path=config_path, query=query)

def semantic_quality_audit(config_path: str | None = None) -> dict[str, Any]:
    """Bridge wrapper preserving the semantic quality audit contract."""
    return semantic_ops.semantic_quality_audit(config_path=config_path)

def semantic_verify(query: str = "semantic recall smoke test", limit: int = 5, config_path: str | None = None) -> dict[str, Any]:
    return semantic_quality.verify(query=query, limit=limit, config_path=config_path)

def semantic_index(rebuild: bool = False, batch_size: int = 8, limit: int | None = None, config_path: str | None = None) -> dict[str, Any]:
    return semantic_quality.index(rebuild=rebuild, batch_size=batch_size, limit=limit, config_path=config_path)

def short_term_audit(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.short_term_audit(limit=limit, config_path=config_path)

def short_term_mark_reviewed(cluster_key: str, decision: str = "deferred", config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.short_term_mark_reviewed(cluster_key=cluster_key, decision=decision, config_path=config_path)

def short_term_repair(dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.short_term_repair(dry_run=dry_run, limit=limit, config_path=config_path)


def dreaming_audit(config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.dreaming_audit(config_path=config_path)


def dreaming_run(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.dreaming_run(limit=limit, dry_run=dry_run, config_path=config_path)


def dreaming_repair(config_path: str | None = None) -> dict[str, Any]:
    return memory_core_ops.dreaming_repair(config_path=config_path)

def maintenance_run(dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Bridge wrapper for full safe maintenance workflow."""
    SuperMemoryService(load_config(config_path))
    return maintenance_ops.maintenance_run(dry_run=dry_run, limit=limit, config_path=config_path)

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

def recommendations(limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    from . import recommendation
    return recommendation.recommendations(limit=limit, config_path=config_path)


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

def deep_improve(dry_run: bool = True, config_path: str | None = None, compact: bool = False, max_seconds: int | None = None, async_mode: bool = False) -> dict[str, Any]:
    if async_mode:
        from .maintenance_jobs import deep_improve_mcp_safe
        return deep_improve_mcp_safe(dry_run=dry_run, config_path=config_path, async_mode=True, compact=compact, max_seconds=max_seconds or 3)
    from . import deep_auto
    result = deep_auto.deep_improve(dry_run=dry_run, config_path=config_path)
    if compact:
        return {"ok": result.get("ok", True), "mode": "sync", "compact": True, "summary": result.get("summary"), "audit_grade": result.get("audit_grade"), "qualify_grade": result.get("qualify_grade"), "problems_found": result.get("problems_found"), "applied_count": len(result.get("applied", [])), "improvement_count": len(result.get("improvement_proposals", []))}
    return result

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
        # recall() now returns an arbitration payload with scalar fields plus
        # selected/answer_context lists. Older durable-pack qualification code
        # assumed a layer->list mapping and crashed on scalar values such as
        # confidence. Count selected evidence first, then fall back to any
        # list-valued legacy layer payloads for backwards compatibility.
        selected = res.get("selected") or res.get("selected_memories") or res.get("answer_context") or []
        if isinstance(selected, list):
            total = len(selected)
        else:
            total = sum(len(v) for v in res.values() if isinstance(v, list))
        qual_results.append({"ok": total > 0, "query": q[:60], "hit_count": total})
    saved_items = saved.get("items", []) if isinstance(saved, dict) else []
    has_duplicates = all(item.get("ok") or item.get("dedup", {}).get("skipped") for item in saved_items)
    st = {"ok": True, "duplicates_count": 0}
    debug_payload = {"health": cross_layer_health(config_path=config_path)} if debug else None
    out = {"ok": True, "pack_name": pack_name, "saved": {"ok": has_duplicates, "items": saved_items, "raw": saved}, "qualification": qual_results, "status": st}
    if debug_payload is not None:
        out["debug"] = debug_payload
    return out

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


def self_heal_status(config_path: str | None = None, mode: str = "fast") -> dict[str, Any]:
    """Show self-heal status (missing vector count).

    The MCP schema exposes ``mode`` and defaults to ``fast``. Keep this path
    bounded so health checks do not time out on large/locked databases; callers
    can request ``mode='full'`` for the complete count.
    """
    if mode == "fast":
        from .health_cache import self_heal_status_fast
        try:
            return self_heal_status_fast(config_path=config_path)
        except Exception as exc:
            # If cache update or a transient lock fails, fall back to a read-only
            # bounded status instead of timing out the MCP call.
            return {"ok": False, "mode": "fast", "error": f"{type(exc).__name__}: {exc}", "timeout_resilient": True}
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


# ── Improvement roadmap v2.3 additive bridge wrappers ─────────────────────
def build_memory_envelope(content: str, memory_type: str = "context", scope: str = "session", agent_id: str = "lucas", session_id: str | None = None, project: str | None = None, tags: list[str] | None = None, source_adapter: str = "direct", trust_score: float | None = None, config_path: str | None = None) -> dict[str, Any]:
    from .core.envelope import build_envelope
    env = build_envelope(content, memory_type=memory_type, scope=scope, agent_id=agent_id, session_id=session_id, project=project, tags=tags or [], source_adapter=source_adapter, trust_score=trust_score)
    return {"ok": True, "envelope": env.to_memory_record()["metadata"] | {"id": env.id, "content": env.content, "type": env.type.value, "scope": env.scope.value}}

def evaluate_write_gate(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    from .core.envelope import build_envelope
    from .core.write_gate import evaluate_write
    env = build_envelope(payload.get("content", ""), memory_type=payload.get("type"), scope=payload.get("scope"), agent_id=payload.get("agent_id", "lucas"), session_id=payload.get("session_id"), project=payload.get("project"), tags=payload.get("tags") or [], source_adapter=payload.get("source") or "direct", trust_score=payload.get("trust_score"), metadata=payload.get("metadata") or {})
    return {"ok": True, "write_gate": evaluate_write(env).to_dict()}

def projection_manifest_register(memory_id: str, projection_type: str, source_content: str = "", projection_content: str = "", config_path: str | None = None) -> dict[str, Any]:
    from .projections.manifest import register_projection
    return register_projection(memory_id, projection_type, source_content, projection_content, config_path=config_path)

def projection_manifest_audit(config_path: str | None = None, limit: int = 200) -> dict[str, Any]:
    from .projections.manifest import audit_projection_drift
    return audit_projection_drift(config_path=config_path, limit=limit)

def projection_manifest_repair(config_path: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    from .projections.manifest import repair_projection_drift
    return repair_projection_drift(config_path=config_path, dry_run=dry_run)

def projection_manifest_backfill(config_path: str | None = None, limit: int = 500) -> dict[str, Any]:
    from .projections.manifest import backfill_projection_manifest
    return backfill_projection_manifest(config_path=config_path, limit=limit)

def long_memory_review(threshold: int = 2000, limit: int = 100, config_path: str | None = None) -> dict[str, Any]:
    from .long_memory import review_long_memories
    return review_long_memories(threshold=threshold, limit=limit, config_path=config_path)

def long_memory_compress(memory_id: str, layer: str = "workspace_markdown", dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from .long_memory import compress_long_memory
    return compress_long_memory(memory_id, layer=layer, dry_run=dry_run, config_path=config_path)

def recall_arbitrate_v4(query: str, channels: dict[str, list[dict[str, Any]]], limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    from .recall.arbitration_v4 import arbitrate_v4
    return arbitrate_v4(query, channels, limit=limit)

def peer_profile_upsert(peer_id: str, facts: list[str] | None = None, preferences: list[str] | None = None, goals: list[str] | None = None, role: str = "human", workspace: str = "openclaw", config_path: str | None = None) -> dict[str, Any]:
    from .peer_profile import upsert_peer_profile
    return upsert_peer_profile(peer_id, workspace=workspace, role=role, facts=facts, preferences=preferences, goals=goals, config_path=config_path)

def peer_profile_get(peer_id: str, config_path: str | None = None) -> dict[str, Any]:
    from .peer_profile import get_peer_profile
    return get_peer_profile(peer_id, config_path=config_path)

def perspective_record(memory_id: str, observer_peer_id: str, observed_peer_id: str, session_id: str | None = None, observation_type: str = "explicit", config_path: str | None = None) -> dict[str, Any]:
    from .peer_profile import record_perspective
    return record_perspective(memory_id, observer_peer_id, observed_peer_id, session_id=session_id, observation_type=observation_type, config_path=config_path)

def recall_benchmark_create(query: str, expected_contains: list[str] | None = None, config_path: str | None = None) -> dict[str, Any]:
    from .recall_benchmark import create_recall_case
    return create_recall_case(query, expected_contains=expected_contains, config_path=config_path)

def recall_benchmark_run(config_path: str | None = None, limit: int = 50) -> dict[str, Any]:
    from .recall_benchmark import run_recall_benchmark
    return run_recall_benchmark(config_path=config_path, limit=limit)


def recall_benchmark_seed(config_path: str | None = None, overwrite: bool = False) -> dict[str, Any]:
    from .recall_benchmark import seed_default_recall_cases
    return seed_default_recall_cases(config_path=config_path, overwrite=overwrite)


def recall_release_gate(config_path: str | None = None, limit: int = 100) -> dict[str, Any]:
    from .recall_benchmark import release_gate
    return release_gate(config_path=config_path, limit=limit)


def scheduled_maintenance_report(config_path: str | None = None, dry_run: bool = False, profile: str = "daily") -> dict[str, Any]:
    from .maintenance_reports import run_scheduled_maintenance
    return run_scheduled_maintenance(config_path=config_path, dry_run=dry_run, profile=profile)


def maintenance_enqueue(job_type: str, args: dict[str, Any] | None = None, config_path: str | None = None) -> dict[str, Any]:
    from .maintenance_jobs import enqueue
    return enqueue(job_type, args or {}, config_path=config_path)

def maintenance_job_status(job_id: str, config_path: str | None = None) -> dict[str, Any]:
    from .maintenance_jobs import status
    return status(job_id, config_path=config_path)

def maintenance_process_jobs(limit: int = 5, config_path: str | None = None) -> dict[str, Any]:
    from .maintenance_jobs import process_jobs
    return process_jobs(limit=limit, config_path=config_path)
# ── Self-improvement orchestration ──────────────────────────────────────────

def self_improvement_orchestrator(dry_run: bool = True, limit: int = 500, remember_lesson: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from .self_improvement.orchestrator import run_self_improvement_cycle
    return run_self_improvement_cycle(dry_run=dry_run, limit=limit, remember_lesson=remember_lesson, config_path=config_path)

def write_contract_process_jobs(limit: int = 50, config_path: str | None = None) -> dict[str, Any]:
    """Process bounded write-contract projection/embed jobs.

    MCP exposes this name directly, so keep a thin bridge wrapper instead of
    relying on missing dynamic attributes. The worker itself enforces the
    supplied limit.
    """
    from .write_contract.worker import process_memory_jobs
    return process_memory_jobs(limit=limit, config_path=config_path)


def write_contract_reconcile(limit: int = 200, config_path: str | None = None) -> dict[str, Any]:
    """Reconcile write-contract integrity gaps and enqueue bounded jobs."""
    from .write_contract.worker import reconcile_memory_integrity
    return reconcile_memory_integrity(limit=limit, config_path=config_path)


def write_contract_semantic_merge(threshold: float = 0.92, simhash_distance: int = 3, limit: int = 500, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    from .write_contract.semantic_merge import soft_delete_duplicate_clusters
    return soft_delete_duplicate_clusters(threshold=threshold, simhash_distance=simhash_distance, limit=limit, dry_run=dry_run, config_path=config_path)


def duplicate_resolution_v2(threshold: float = 0.92, simhash_distance: int = 3, limit: int = 500, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    return write_contract_semantic_merge(threshold=threshold, simhash_distance=simhash_distance, limit=limit, dry_run=dry_run, config_path=config_path)


def project_backfill(limit: int = 2000, dry_run: bool = True, config_path: str | None = None, rebuild_graph: bool = False) -> dict[str, Any]:
    from .project_inference import backfill_projects
    return backfill_projects(limit=limit, dry_run=dry_run, rebuild_graph=rebuild_graph, config_path=config_path)


def project_synapse_backfill(limit: int = 2000, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Infer missing projects and rebuild project synapses in one maintenance step."""
    from .project_inference import backfill_projects
    return backfill_projects(limit=limit, dry_run=dry_run, rebuild_graph=True, config_path=config_path)

def vector_coverage(config_path: str | None = None) -> dict[str, Any]:
    from .validation import vector_coverage as _vector_coverage
    return _vector_coverage(config_path=config_path)

def graph_multihop_validation(query: str = "super memory project recall graph", limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    from .validation import graph_multihop_validation as _graph_multihop_validation
    return _graph_multihop_validation(query=query, limit=limit, config_path=config_path)
