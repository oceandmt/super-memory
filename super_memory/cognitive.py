from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from . import bridge
from .config import load_config
from .models import MemoryScope, MemoryType
from .storage import SuperMemoryStore, row_to_memory

WORKING_MEMORY_KEY = "default"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(config_path: str | None = None) -> SuperMemoryStore:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _init_cognitive_tables(store)
    return store


def _init_cognitive_tables(store: SuperMemoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_working_memory (
                key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_events (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def _event(store: SuperMemoryStore, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_id = f"cog:{kind}:{datetime.now(timezone.utc).timestamp()}"
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO cognitive_events (id, kind, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (event_id, kind, json.dumps(payload, ensure_ascii=False), _now()),
        )
    return {"id": event_id, "kind": kind, "payload": payload}


def working_memory_get(key: str = WORKING_MEMORY_KEY, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM cognitive_working_memory WHERE key = ?", (key,)).fetchone()
    if not row:
        return {"ok": True, "key": key, "memory": None}
    expired = False
    if row["expires_at"]:
        expired = datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc)
    return {
        "ok": True,
        "key": key,
        "memory": json.loads(row["payload_json"]),
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "expired": expired,
    }


def working_memory_set(payload: dict[str, Any], key: str = WORKING_MEMORY_KEY, ttl_seconds: int | None = None, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    expires_at = None
    if ttl_seconds:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    current = working_memory_get(key, config_path=config_path).get("memory") or {}
    merged = {**current, **payload}
    with store.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO cognitive_working_memory (key, payload_json, updated_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, json.dumps(merged, ensure_ascii=False), _now(), expires_at),
        )
    _event(store, "working_memory_set", {"key": key, "fields": sorted(payload)})
    return {"ok": True, "key": key, "memory": merged, "expires_at": expires_at}


def attention_score(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    content = str(payload.get("content") or payload.get("text") or "")
    lowered = content.lower()
    tags = [str(t).lower() for t in payload.get("tags", [])]
    score = 0.15
    reasons: list[str] = []

    def add(points: float, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if payload.get("explicit_save") or any(w in lowered for w in ["remember", "save", "lưu lại", "ghi nhớ"]):
        add(0.25, "explicit save/remember signal")
    if any(w in lowered for w in ["decision", "decided", "quyết định"]):
        add(0.18, "decision signal")
    if any(w in lowered for w in ["workflow", "process", "procedure", "quy trình"]):
        add(0.15, "workflow/procedure signal")
    if any(w in lowered for w in ["blocker", "error", "fail", "lỗi", "blocked"]):
        add(0.15, "blocker/error signal")
    if payload.get("project") or any(t.startswith("project:") for t in tags):
        add(0.10, "project context")
    if payload.get("trust_score") is not None:
        add(min(float(payload.get("trust_score") or 0), 1.0) * 0.10, "trust score")
    if any(w in lowered for w in ["password", "secret", "token", "api key"]):
        add(-0.25, "sensitive content penalty")
    if len(content) < 24:
        add(-0.10, "too short")

    score = max(0.0, min(1.0, score))
    if score >= 0.8:
        salience = "critical"
    elif score >= 0.6:
        salience = "high"
    elif score >= 0.35:
        salience = "normal"
    else:
        salience = "low"

    routes = ["working_memory"]
    ttl = "session"
    promotion_candidate = False
    if salience in {"normal", "high", "critical"}:
        routes.append("workspace_markdown")
    if any(r in reasons for r in ["workflow/procedure signal", "project context"]):
        routes.append("mempalace")
    if payload.get("session_id") or payload.get("participant") or payload.get("peer_id"):
        routes.append("honcho")
    if salience in {"high", "critical"} or any(r in reasons for r in ["blocker/error signal", "decision signal"]):
        routes.append("neural_memory")
    if salience in {"high", "critical"} and any(r in reasons for r in ["decision signal", "workflow/procedure signal", "blocker/error signal"]):
        promotion_candidate = True
        ttl = "durable"
    elif salience == "normal":
        ttl = "days:7"

    return {
        "attention_score": round(score, 3),
        "salience": salience,
        "routes": list(dict.fromkeys(routes)),
        "ttl": ttl,
        "promotion_candidate": promotion_candidate,
        "reasons": reasons,
    }


def route_memory(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    scored = attention_score(payload, config_path=config_path)
    memory_type = payload.get("type") or MemoryType.CONTEXT.value
    content = str(payload.get("content") or payload.get("text") or "")
    if "decision signal" in scored["reasons"]:
        memory_type = MemoryType.DECISION.value
    elif "workflow/procedure signal" in scored["reasons"]:
        memory_type = MemoryType.WORKFLOW.value
    elif "blocker/error signal" in scored["reasons"]:
        memory_type = MemoryType.BLOCKER.value
    routed = {
        "content": content,
        "type": memory_type,
        "scope": payload.get("scope", MemoryScope.SESSION.value),
        "agent_id": payload.get("agent_id", "lucas"),
        "session_id": payload.get("session_id"),
        "project": payload.get("project"),
        "tags": list(payload.get("tags", [])) + ["phase6", f"salience:{scored['salience']}"],
        "source": payload.get("source", "super-memory.phase6"),
        "trust_score": payload.get("trust_score"),
        "metadata": {**payload.get("metadata", {}), "attention": scored},
    }
    return {"ok": True, "route": scored, "memory": routed}


def parallel_save(payload: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    routed = route_memory(payload, config_path=config_path)
    wm = working_memory_set({"last_routed_memory": routed["memory"], "last_route": routed["route"]}, config_path=config_path)
    if "workspace_markdown" not in routed["route"]["routes"]:
        return {"ok": True, "saved": False, "reason": "attention below durable threshold", "working_memory": wm, **routed}
    saved = bridge.remember(routed["memory"], config_path=config_path)
    return {"ok": True, "saved": True, "working_memory": wm, "save_result": saved, **routed}


def recall_arbitrate(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    layered = bridge.recall(query, limit=limit, config_path=config_path)
    layer_weights = {"workspace_markdown": 1.0, "mempalace": 0.75, "honcho": 0.7, "neural_memory": 0.65}
    q = query.lower()
    if any(w in q for w in ["workflow", "procedure", "project", "quy trình"]):
        layer_weights["mempalace"] = 1.05
    if any(w in q for w in ["boss", "user", "session", "conversation", "preference"]):
        layer_weights["honcho"] = 1.05
    if any(w in q for w in ["pattern", "related", "blocker", "insight", "association"]):
        layer_weights["neural_memory"] = 1.05
    if any(w in q for w in ["exact", "path", "config", "command", "date", "quote"]):
        layer_weights["workspace_markdown"] = 1.25

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    fallback_terms: list[str] = []
    for layer, records in layered.items():
        for idx, rec in enumerate(records):
            key = rec.get("id") or rec.get("content")
            if key in seen:
                continue
            seen.add(str(key))
            candidates.append({"layer": layer, "rank": idx, "score": round(layer_weights.get(layer, 0.5) - idx * 0.03, 3), "record": rec})
    if not candidates:
        # FTS5 MATCH is strict for long multi-term queries. Fall back to bounded
        # term-wise recall so arbitration can still surface the same memories that
        # normal focused recall/qualification can find.
        import re
        stop = {"the", "and", "for", "with", "from", "that", "this", "super", "memory"}
        fallback_terms = [t for t in re.split(r"[^a-zA-Z0-9_]+", q) if len(t) > 3 and t not in stop][:8]
        for term in fallback_terms:
            term_hits = bridge.recall(term, limit=limit, config_path=config_path)
            for layer, records in term_hits.items():
                layered.setdefault(layer, [])
                for rec in records:
                    key = rec.get("id") or rec.get("content")
                    if key in seen:
                        continue
                    seen.add(str(key))
                    layered[layer].append(rec)
                    candidates.append({"layer": layer, "rank": len(candidates), "score": round(layer_weights.get(layer, 0.5) * 0.85, 3), "record": rec, "fallback_term": term})
                    if len(candidates) >= limit:
                        break
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break
    candidates.sort(key=lambda item: item["score"], reverse=True)
    winner_policy = candidates[0]["layer"] if candidates else "none"
    confidence = candidates[0]["score"] if candidates else 0.0
    return {
        "query": query,
        "answer_context": candidates[:limit],
        "layer_votes": {layer: len(records) for layer, records in layered.items()},
        "fallback_terms": fallback_terms,
        "conflicts": [],
        "winner_policy": winner_policy,
        "confidence": confidence,
        "citations": [c["record"].get("source") for c in candidates[:limit] if c["record"].get("source")],
    }


def consolidation_cycle(strategy: str = "light", dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    rows = store.list_memory_rows(limit=200)
    by_content: dict[str, list[str]] = {}
    promotion: list[dict[str, Any]] = []
    for row in rows:
        rec = row_to_memory(row)
        norm = rec.content.strip().lower()
        by_content.setdefault(norm, []).append(rec.id)
        if rec.type.value in {"decision", "workflow", "blocker", "lesson", "doctrine"}:
            promotion.append({"id": rec.id, "type": rec.type.value, "content": rec.content[:240], "reason": "durable memory type"})
    duplicates = [{"content": k[:240], "ids": v} for k, v in by_content.items() if len(set(v)) > 1]
    payload = {"strategy": strategy, "dry_run": dry_run, "duplicates": duplicates[:20], "promotion_candidates": promotion[:20], "checked": len(rows)}
    event = None if dry_run else _event(store, "consolidation_cycle", payload)
    return {"ok": True, **payload, "event": event}


def conflict_resolve(conflict_id: str, resolution: str, reason: str = "", config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    payload = {"conflict_id": conflict_id, "resolution": resolution, "reason": reason}
    event = _event(store, "conflict_resolve", payload)
    return {"ok": True, "event": event, **payload}


def promotion_candidates(limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    rows = store.list_memory_rows(limit=300)
    candidates = []
    for row in rows:
        rec = row_to_memory(row)
        scored = attention_score({"content": rec.content, "type": rec.type.value, "project": rec.project, "tags": rec.tags, "trust_score": rec.trust_score})
        if scored["promotion_candidate"] or rec.type.value in {"decision", "workflow", "blocker", "lesson", "doctrine"}:
            candidates.append({"id": rec.id, "type": rec.type.value, "score": scored["attention_score"], "content": rec.content[:240], "reasons": scored["reasons"]})
        if len(candidates) >= limit:
            break
    return {"ok": True, "candidates": candidates}


def feedback_outcome(memory_id: str | None = None, success: bool = True, outcome: str = "", config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    payload = {"memory_id": memory_id, "success": success, "outcome": outcome}
    event = _event(store, "feedback_outcome", payload)
    if memory_id and outcome:
        bridge.remember({
            "content": f"Feedback for {memory_id}: {'success' if success else 'failure'} — {outcome}",
            "type": MemoryType.LESSON.value if success else MemoryType.BLOCKER.value,
            "scope": MemoryScope.PROJECT.value,
            "tags": ["phase6", "feedback", f"success:{str(success).lower()}"],
            "source": "super-memory.feedback",
            "metadata": {"related_memory_ids": [memory_id], "cognitive_event_id": event["id"]},
        }, config_path=config_path)
    return {"ok": True, "event": event}
