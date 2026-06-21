from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(config_path: str | None = None) -> SuperMemoryStore:
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    _init_tables(store)
    return store


def _init_tables(store: SuperMemoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lifecycle_state (
                key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def _rows(store: SuperMemoryStore, limit: int = 500, include_soft_deleted: bool = False) -> list[Any]:
    if include_soft_deleted:
        query = "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?"
    else:
        query = (
            "SELECT * FROM memories "
            "WHERE (json_extract(metadata_json, '$.soft_deleted') IS NULL "
            "OR json_extract(metadata_json, '$.soft_deleted') != 1) "
            "ORDER BY created_at DESC LIMIT ?"
        )
    with store.connect() as conn:
        return conn.execute(query, (limit,)).fetchall()


def _load_state(store: SuperMemoryStore, key: str) -> dict[str, Any] | None:
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM lifecycle_state WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return {"key": row["key"], "payload": json.loads(row["payload_json"]), "updated_at": row["updated_at"]}


def _save_state(store: SuperMemoryStore, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    updated_at = _now()
    with store.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO lifecycle_state (key, payload_json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(payload, ensure_ascii=False), updated_at),
        )
    return {"key": key, "payload": payload, "updated_at": updated_at}


def _classify_tier(rec: Any) -> str:
    tags = set(rec.normalized_tags())
    if rec.type.value in {"doctrine", "decision", "workflow", "blocker", "lesson", "preference"}:
        return "hot"
    if rec.trust_score is not None and rec.trust_score >= 0.8:
        return "hot"
    if "tier:cold" in tags or rec.type.value == "event":
        return "cold"
    return "warm"


def review(config_path: str | None = None, limit: int = 500) -> dict[str, Any]:
    store = _store(config_path)
    rows = _rows(store, limit=limit)
    tier_counts = {"hot": 0, "warm": 0, "cold": 0}
    compression_candidates: list[dict[str, Any]] = []
    content_seen: dict[str, list[str]] = {}
    type_counts: dict[str, int] = {}
    layer_counts: dict[str, int] = {}
    missing_canonical_ids: set[str] = set()
    canonical_ids: set[str] = set()
    all_ids: set[str] = set()
    for row in rows:
        rec = row_to_memory(row)
        all_ids.add(rec.id)
        if row["layer"] == "workspace_markdown":
            canonical_ids.add(rec.id)
        tier_counts[_classify_tier(rec)] += 1
        type_counts[rec.type.value] = type_counts.get(rec.type.value, 0) + 1
        layer_counts[row["layer"]] = layer_counts.get(row["layer"], 0) + 1
        norm = rec.metadata.get("content_hash") or " ".join(rec.content.lower().split())
        content_seen.setdefault(norm, []).append(rec.id)
        if len(rec.content) > 1200 and not rec.metadata.get("compression_candidate"):
            compression_candidates.append({"id": rec.id, "layer": row["layer"], "chars": len(rec.content), "reason": "long content"})
    # Canonical markdown is file-backed, not stored in SQLite. Missing canonical
    # here means a derived SQLite id has no sqlite canonical twin, not necessarily
    # that the append-only markdown line is absent.
    missing_canonical_ids = all_ids - canonical_ids if canonical_ids else set()
    duplicates = [{"ids": sorted(set(ids)), "count": len(set(ids))} for ids in content_seen.values() if len(set(ids)) > 1]
    cache = _load_state(store, "activation_cache")
    return {
        "ok": True,
        "checked": len(rows),
        "tier_distribution": tier_counts,
        "type_counts": type_counts,
        "layer_counts": layer_counts,
        "compression_candidates": compression_candidates[:20],
        "duplicates": duplicates[:20],
        "cache": {"present": bool(cache), "updated_at": cache.get("updated_at") if cache else None},
        "canonical_first_note": "Workspace Markdown remains canonical; lifecycle actions only report or annotate derived SQLite layers.",
        "derived_ids_without_sqlite_canonical_count": len(missing_canonical_ids),
    }


def cache(action: str = "status", config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    if action == "clear":
        with store.connect() as conn:
            conn.execute("DELETE FROM lifecycle_state WHERE key = 'activation_cache'")
        return {"ok": True, "action": action, "cache": None}
    if action == "save":
        payload = {"review": review(config_path=config_path), "saved_at": _now(), "kind": "local_activation_snapshot"}
        return {"ok": True, "action": action, "cache": _save_state(store, "activation_cache", payload)}
    if action == "load":
        return {"ok": True, "action": action, "cache": _load_state(store, "activation_cache")}
    return {"ok": True, "action": "status", "cache": _load_state(store, "activation_cache")}


def tier(action: str = "evaluate", dry_run: bool = True, config_path: str | None = None, limit: int = 500) -> dict[str, Any]:
    store = _store(config_path)
    proposals = []
    for row in _rows(store, limit=limit):
        rec = row_to_memory(row)
        current = rec.metadata.get("tier", "warm")
        proposed = _classify_tier(rec)
        if current != proposed:
            proposals.append({"id": rec.id, "layer": row["layer"], "current": current, "proposed": proposed, "type": rec.type.value, "content": rec.content[:160]})
    applied = 0
    if action == "apply" and not dry_run:
        with store.connect() as conn:
            for item in proposals:
                row = conn.execute("SELECT metadata_json FROM memories WHERE id=? AND layer=?", (item["id"], item["layer"])).fetchone()
                if not row:
                    continue
                metadata = json.loads(row["metadata_json"])
                metadata["tier"] = item["proposed"]
                metadata["tier_updated_at"] = _now()
                conn.execute("UPDATE memories SET metadata_json=? WHERE id=? AND layer=?", (json.dumps(metadata, ensure_ascii=False), item["id"], item["layer"]))
                applied += 1
    return {"ok": True, "action": action, "dry_run": dry_run, "proposals": proposals[:100], "applied": applied}


def quality_cleanup(dry_run: bool = True, config_path: str | None = None, limit: int = 500) -> dict[str, Any]:
    """Reduce memory-store noise by soft-deleting active duplicate IDs and marking long raw events.

    Canonical-first invariant: never removes markdown files or hard-deletes records; all actions are
    SQLite metadata annotations so audit trails remain recoverable.
    """
    store = _store(config_path)
    rows = _rows(store, limit=limit)
    groups: dict[str, list[Any]] = {}
    for row in rows:
        rec = row_to_memory(row)
        key = rec.metadata.get("content_hash") or " ".join(rec.content.lower().split())
        groups.setdefault(key, []).append(row)
    duplicate_actions: list[dict[str, Any]] = []
    compression_actions: list[dict[str, Any]] = []
    for items in groups.values():
        ids = sorted({row["id"] for row in items})
        if len(ids) > 1:
            keep = ids[0]
            for dup_id in ids[1:]:
                duplicate_actions.append({"id": dup_id, "keep": keep, "action": "would_soft_delete" if dry_run else "soft_deleted"})
    for row in rows:
        rec = row_to_memory(row)
        if rec.type.value == "event" and len(rec.content) > 1200 and not rec.metadata.get("compression_candidate"):
            compression_actions.append({"id": rec.id, "layer": row["layer"], "chars": len(rec.content), "action": "would_mark" if dry_run else "marked"})
    if not dry_run:
        with store.connect() as conn:
            for item in duplicate_actions:
                conn.execute(
                    "UPDATE memories SET metadata_json = json_set(metadata_json, '$.soft_deleted', 1, '$.deleted_reason', ?, '$.deleted_at', ?) WHERE id = ?",
                    (f"lifecycle_quality_cleanup keep={item['keep']}", _now(), item["id"]),
                )
            for item in compression_actions:
                conn.execute(
                    "UPDATE memories SET metadata_json = json_set(metadata_json, '$.compression_candidate', 1, '$.compression_reviewed_at', ?, '$.compression_reason', 'long_raw_event') WHERE id = ? AND layer = ?",
                    (_now(), item["id"], item["layer"]),
                )
            conn.commit()
    return {
        "ok": True,
        "dry_run": dry_run,
        "duplicates": duplicate_actions[:100],
        "duplicates_count": len(duplicate_actions),
        "compression_candidates": compression_actions[:100],
        "compression_count": len(compression_actions),
        "note": "Soft-delete/mark only; no hard deletes and no markdown truncation.",
    }


def compression(action: str = "review", dry_run: bool = True, config_path: str | None = None, limit: int = 500) -> dict[str, Any]:
    report = review(config_path=config_path, limit=limit)
    candidates = report["compression_candidates"]
    applied = 0
    if action == "mark" and not dry_run:
        store = _store(config_path)
        with store.connect() as conn:
            for item in candidates:
                row = conn.execute("SELECT metadata_json FROM memories WHERE id=? AND layer=?", (item["id"], item["layer"])).fetchone()
                if not row:
                    continue
                metadata = json.loads(row["metadata_json"])
                metadata["compression_candidate"] = True
                metadata["compression_reviewed_at"] = _now()
                conn.execute("UPDATE memories SET metadata_json=? WHERE id=? AND layer=?", (json.dumps(metadata, ensure_ascii=False), item["id"], item["layer"]))
                applied += 1
    return {"ok": True, "action": action, "dry_run": dry_run, "candidates": candidates, "applied": applied, "note": "No content is truncated; mark only annotates derived SQLite records."}


def reflex_status(config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    # Reflex events are stored by intelligence.reflex in intelligence_events.
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
        rows = conn.execute("SELECT * FROM intelligence_events WHERE kind LIKE 'reflex:%' ORDER BY created_at DESC LIMIT 100").fetchall()
    items = []
    for row in rows:
        memory_id = row["subject"]
        exists = bool(store.get_memory(memory_id)) if memory_id else False
        items.append({"event_id": row["id"], "kind": row["kind"], "memory_id": memory_id, "memory_exists": exists, "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]})
    return {"ok": True, "reflex_events": items, "missing_memory_refs": [i for i in items if not i["memory_exists"]], "hardening": "Reflex pins are audit events only; they do not bypass canonical-first save order."}
