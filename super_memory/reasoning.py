from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import load_config
from .models import MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore
from . import bridge, graph


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(config_path: str | None = None) -> SuperMemoryStore:
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    _init_tables(store)
    return store


def _init_tables(store: SuperMemoryStore) -> None:
    graph.init_tables(store)
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_hypotheses (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_evidence (
                id TEXT PRIMARY KEY,
                hypothesis_id TEXT NOT NULL,
                content TEXT NOT NULL,
                direction TEXT NOT NULL,
                weight REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_evidence_hypothesis ON cognitive_evidence(hypothesis_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_predictions (
                id TEXT PRIMARY KEY,
                hypothesis_id TEXT,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                deadline TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_predictions_hypothesis ON cognitive_predictions(hypothesis_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_verifications (
                id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                content TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def _clamp(value: float) -> float:
    return max(0.01, min(0.99, float(value)))


def _status(confidence: float, evidence_count: int = 0) -> str:
    if evidence_count >= 3 and confidence >= 0.9:
        return "confirmed"
    if evidence_count >= 3 and confidence <= 0.1:
        return "refuted"
    return "active"


def _confidence_update(current: float, direction: str, weight: float) -> float:
    # Deterministic Bayesian-ish update: positive evidence moves toward 1,
    # negative evidence moves toward 0; no stochastic LLM dependency.
    weight = max(0.0, min(1.0, weight))
    if direction == "for":
        return _clamp(current + (1.0 - current) * weight * 0.35)
    return _clamp(current - current * weight * 0.35)


def hypothesis_create(content: str, confidence: float = 0.5, tags: list[str] | None = None, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    hyp_id = f"hyp:{uuid4()}"
    tags = tags or []
    now = _now()
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO cognitive_hypotheses (id, content, confidence, status, tags_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (hyp_id, content, _clamp(confidence), "active", json.dumps(tags, ensure_ascii=False), json.dumps({"canonical_first": True}, ensure_ascii=False), now, now),
        )
    saved = bridge.remember({"content": f"Hypothesis: {content}", "type": MemoryType.INSIGHT.value, "scope": MemoryScope.PROJECT.value, "tags": ["hypothesis", *tags], "source": "super-memory.reasoning", "trust_score": _clamp(confidence), "metadata": {"hypothesis_id": hyp_id}}, config_path=config_path)
    return {"ok": True, "hypothesis_id": hyp_id, "content": content, "confidence": _clamp(confidence), "status": "active", "memory": saved.get("record")}


def hypothesis_get(hypothesis_id: str, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    with store.connect() as conn:
        hyp = conn.execute("SELECT * FROM cognitive_hypotheses WHERE id=?", (hypothesis_id,)).fetchone()
        ev = conn.execute("SELECT * FROM cognitive_evidence WHERE hypothesis_id=? ORDER BY created_at", (hypothesis_id,)).fetchall()
        pred = conn.execute("SELECT * FROM cognitive_predictions WHERE hypothesis_id=? ORDER BY created_at", (hypothesis_id,)).fetchall()
    if not hyp:
        return {"ok": False, "error": f"hypothesis not found: {hypothesis_id}"}
    return {"ok": True, "hypothesis": {"id": hyp["id"], "content": hyp["content"], "confidence": hyp["confidence"], "status": hyp["status"], "tags": json.loads(hyp["tags_json"]), "metadata": json.loads(hyp["metadata_json"]), "created_at": hyp["created_at"], "updated_at": hyp["updated_at"]}, "evidence": [{"id": r["id"], "content": r["content"], "direction": r["direction"], "weight": r["weight"], "created_at": r["created_at"]} for r in ev], "predictions": [{"id": r["id"], "content": r["content"], "confidence": r["confidence"], "status": r["status"], "deadline": r["deadline"]} for r in pred]}


def hypothesis_list(status: str | None = None, limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    where = "WHERE status=?" if status else ""
    params: tuple[Any, ...] = (status, limit) if status else (limit,)
    with store.connect() as conn:
        rows = conn.execute(f"SELECT * FROM cognitive_hypotheses {where} ORDER BY updated_at DESC LIMIT ?", params).fetchall()
    return {"ok": True, "hypotheses": [{"id": r["id"], "content": r["content"], "confidence": r["confidence"], "status": r["status"], "tags": json.loads(r["tags_json"]), "updated_at": r["updated_at"]} for r in rows]}


def evidence_add(hypothesis_id: str, content: str, direction: str = "for", weight: float = 0.5, config_path: str | None = None) -> dict[str, Any]:
    if direction not in {"for", "against"}:
        raise ValueError("direction must be 'for' or 'against'")
    store = _store(config_path)
    ev_id = f"ev:{uuid4()}"
    now = _now()
    with store.connect() as conn:
        hyp = conn.execute("SELECT * FROM cognitive_hypotheses WHERE id=?", (hypothesis_id,)).fetchone()
        if not hyp:
            return {"ok": False, "error": f"hypothesis not found: {hypothesis_id}"}
        new_conf = _confidence_update(float(hyp["confidence"]), direction, weight)
        ev_count = conn.execute("SELECT COUNT(*) c FROM cognitive_evidence WHERE hypothesis_id=?", (hypothesis_id,)).fetchone()["c"] + 1
        status = _status(new_conf, ev_count)
        conn.execute("INSERT INTO cognitive_evidence (id, hypothesis_id, content, direction, weight, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (ev_id, hypothesis_id, content, direction, max(0.0, min(1.0, weight)), json.dumps({}, ensure_ascii=False), now))
        conn.execute("UPDATE cognitive_hypotheses SET confidence=?, status=?, updated_at=? WHERE id=?", (new_conf, status, now, hypothesis_id))
    saved = bridge.remember({"content": f"Evidence {direction} {hypothesis_id}: {content}", "type": MemoryType.INSIGHT.value if direction == "for" else MemoryType.BLOCKER.value, "scope": MemoryScope.PROJECT.value, "tags": ["evidence", f"evidence:{direction}"], "source": "super-memory.reasoning", "trust_score": max(0.1, min(0.9, weight)), "metadata": {"hypothesis_id": hypothesis_id, "evidence_id": ev_id, "relation": "evidence_for" if direction == "for" else "evidence_against"}}, config_path=config_path)
    return {"ok": True, "evidence_id": ev_id, "hypothesis_id": hypothesis_id, "confidence": new_conf, "status": status, "memory": saved.get("record")}


def prediction_create(content: str, confidence: float = 0.7, hypothesis_id: str | None = None, deadline: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    pred_id = f"pred:{uuid4()}"
    now = _now()
    with store.connect() as conn:
        if hypothesis_id and not conn.execute("SELECT id FROM cognitive_hypotheses WHERE id=?", (hypothesis_id,)).fetchone():
            return {"ok": False, "error": f"hypothesis not found: {hypothesis_id}"}
        conn.execute("INSERT INTO cognitive_predictions (id, hypothesis_id, content, confidence, status, deadline, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (pred_id, hypothesis_id, content, _clamp(confidence), "active", deadline, json.dumps({}, ensure_ascii=False), now, now))
    saved = bridge.remember({"content": f"Prediction: {content}", "type": MemoryType.INSIGHT.value, "scope": MemoryScope.PROJECT.value, "tags": ["prediction"], "source": "super-memory.reasoning", "trust_score": _clamp(confidence), "metadata": {"prediction_id": pred_id, "hypothesis_id": hypothesis_id, "relation": "predicted"}}, config_path=config_path)
    return {"ok": True, "prediction_id": pred_id, "hypothesis_id": hypothesis_id, "content": content, "confidence": _clamp(confidence), "status": "active", "memory": saved.get("record")}


def prediction_list(status: str | None = None, limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    where = "WHERE status=?" if status else ""
    params: tuple[Any, ...] = (status, limit) if status else (limit,)
    with store.connect() as conn:
        rows = conn.execute(f"SELECT * FROM cognitive_predictions {where} ORDER BY updated_at DESC LIMIT ?", params).fetchall()
    return {"ok": True, "predictions": [{"id": r["id"], "hypothesis_id": r["hypothesis_id"], "content": r["content"], "confidence": r["confidence"], "status": r["status"], "deadline": r["deadline"]} for r in rows]}


def verify_prediction(prediction_id: str, outcome: str, content: str = "", config_path: str | None = None) -> dict[str, Any]:
    if outcome not in {"correct", "wrong"}:
        raise ValueError("outcome must be 'correct' or 'wrong'")
    store = _store(config_path)
    ver_id = f"ver:{uuid4()}"
    now = _now()
    with store.connect() as conn:
        pred = conn.execute("SELECT * FROM cognitive_predictions WHERE id=?", (prediction_id,)).fetchone()
        if not pred:
            return {"ok": False, "error": f"prediction not found: {prediction_id}"}
        status = "confirmed" if outcome == "correct" else "refuted"
        conn.execute("INSERT INTO cognitive_verifications (id, prediction_id, outcome, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)", (ver_id, prediction_id, outcome, content, json.dumps({}, ensure_ascii=False), now))
        conn.execute("UPDATE cognitive_predictions SET status=?, updated_at=? WHERE id=?", (status, now, prediction_id))
        hyp_id = pred["hypothesis_id"]
    ev_result = None
    if hyp_id:
        ev_result = evidence_add(hyp_id, content or f"Prediction {prediction_id} was {outcome}", direction="for" if outcome == "correct" else "against", weight=0.8, config_path=config_path)
    saved = bridge.remember({"content": f"Verification {outcome} for {prediction_id}: {content}", "type": MemoryType.INSIGHT.value if outcome == "correct" else MemoryType.BLOCKER.value, "scope": MemoryScope.PROJECT.value, "tags": ["verification", f"outcome:{outcome}"], "source": "super-memory.reasoning", "trust_score": 0.8, "metadata": {"prediction_id": prediction_id, "verification_id": ver_id, "relation": "verified_by" if outcome == "correct" else "falsified_by"}}, config_path=config_path)
    return {"ok": True, "verification_id": ver_id, "prediction_id": prediction_id, "status": status, "hypothesis_update": ev_result, "memory": saved.get("record")}
