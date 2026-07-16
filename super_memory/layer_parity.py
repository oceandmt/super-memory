from __future__ import annotations

from typing import Any

from .config import load_config
from .layers import SQLiteLayerBackend
from .models import MemoryLayer
from .storage import SuperMemoryStore, row_to_memory

CANONICAL = MemoryLayer.WORKSPACE_MARKDOWN
DERIVED = (MemoryLayer.MEMPALACE, MemoryLayer.HONCHO, MemoryLayer.NEURAL_MEMORY)


def _bounded_limit(limit: int | None, default: int = 100, maximum: int = 5000) -> int:
    try:
        value = int(limit or default)
    except Exception:
        value = default
    return max(1, min(value, maximum))


def audit_layer_parity(config_path: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Audit bounded canonical→derived row parity without mutating state.

    This mirrors the readiness `/health` layer_projection_drift check but returns
    the exact missing IDs and metadata operators need for debugging.
    """
    limit = _bounded_limit(limit)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM memories
             WHERE layer=?
               AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
             ORDER BY rowid DESC LIMIT ?
            """,
            (CANONICAL.value, limit),
        ).fetchall()
        canonical_ids = [row["id"] for row in rows]
        missing: dict[str, list[dict[str, Any]]] = {layer.value: [] for layer in DERIVED}
        if canonical_ids:
            placeholders = ",".join("?" for _ in canonical_ids)
            for layer in DERIVED:
                have = {
                    row["id"]
                    for row in conn.execute(
                        f"SELECT id FROM memories WHERE layer=? AND id IN ({placeholders})",
                        (layer.value, *canonical_ids),
                    ).fetchall()
                }
                for row in rows:
                    if row["id"] not in have:
                        missing[layer.value].append(
                            {
                                "memory_id": row["id"],
                                "created_at": row["created_at"],
                                "type": row["type"],
                                "scope": row["scope"],
                                "agent_id": row["agent_id"],
                                "session_id": row["session_id"],
                                "project": row["project"],
                                "content_preview": (row["content"] or "")[:160],
                            }
                        )
    counts = {layer: len(items) for layer, items in missing.items()}
    return {
        "ok": True,
        "dry_run": True,
        "bounded": True,
        "limit": limit,
        "sample_size": len(canonical_ids),
        "canonical_layer": CANONICAL.value,
        "derived_layers": [layer.value for layer in DERIVED],
        "missing_by_layer": missing,
        "counts": counts,
        "has_drift": any(counts.values()),
    }


def repair_layer_parity(config_path: str | None = None, limit: int = 100, dry_run: bool = True) -> dict[str, Any]:
    """Backfill bounded missing derived layer rows from canonical rows.

    Dry-run by default. Non-destructive: it only writes missing derived rows using
    the same SQLiteLayerBackend projection path as normal canonical saves.
    """
    limit = _bounded_limit(limit)
    audit = audit_layer_parity(config_path=config_path, limit=limit)
    plan = [
        {"layer": layer, "memory_id": item["memory_id"]}
        for layer, items in audit["missing_by_layer"].items()
        for item in items
    ]
    if dry_run or not plan:
        return {"ok": True, "dry_run": True, "audit": audit, "repair_plan": plan, "changed": 0}

    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    changed = 0
    errors: list[dict[str, str]] = []
    with store.connect() as conn:
        row_by_id = {
            row["id"]: row
            for row in conn.execute(
                """
                SELECT * FROM memories
                 WHERE layer=?
                   AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
                 ORDER BY rowid DESC LIMIT ?
                """,
                (CANONICAL.value, limit),
            ).fetchall()
        }
    for item in plan:
        row = row_by_id.get(item["memory_id"])
        if row is None:
            errors.append({"layer": item["layer"], "memory_id": item["memory_id"], "error": "canonical_missing"})
            continue
        try:
            result = SQLiteLayerBackend(cfg, MemoryLayer(item["layer"])).save(row_to_memory(row))
            if result.ok:
                changed += 1
            else:
                errors.append({"layer": item["layer"], "memory_id": item["memory_id"], "error": result.error or "save_failed"})
        except Exception as exc:
            errors.append({"layer": item["layer"], "memory_id": item["memory_id"], "error": f"{type(exc).__name__}: {exc}"})
    post_audit = audit_layer_parity(config_path=config_path, limit=limit)
    return {
        "ok": not errors and not post_audit["has_drift"],
        "dry_run": False,
        "audit": audit,
        "repair_plan": plan,
        "changed": changed,
        "errors": errors,
        "post_audit": post_audit,
    }
