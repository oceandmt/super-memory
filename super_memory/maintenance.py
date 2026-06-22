from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import memory_core
from . import lifecycle
from .semantic import semantic_doctor, semantic_index, semantic_verify



def _was_run_recently(config_path: str | None = None, key: str = "maintenance_run", within_hours: int = 1) -> bool:
    """Check if a maintenance step was run recently to avoid redundant execution."""
    from .config import load_config
    from .storage import SuperMemoryStore
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS lifecycle_state (key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        row = conn.execute(
            "SELECT updated_at FROM lifecycle_state WHERE key = ?", (key,)
        ).fetchone()
        if row:
            try:
                last = datetime.fromisoformat(row["updated_at"])
                return (datetime.now(timezone.utc) - last).total_seconds() < within_hours * 3600
            except Exception:
                pass
    return False


def _record_run(config_path: str | None = None, key: str = "maintenance_run") -> None:
    """Record that a maintenance step was performed."""
    import json
    from .config import load_config
    from .storage import SuperMemoryStore
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS lifecycle_state (key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO lifecycle_state (key, payload_json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps({"run": True, "note": "auto-maintenance"}), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def maintenance_run(*, dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Run safe Super Memory maintenance in canonical-first order.

    This is intentionally non-destructive except for soft-delete/metadata marks in
    lifecycle cleanup when dry_run is false. It never hard-deletes or truncates
    canonical markdown.

    Auto-schedule: tracks last run time and skips if run within 1 hour.
    """
    recently = _was_run_recently(config_path, "maintenance_run")
    report: dict[str, Any] = {
        "ok": True, "dry_run": dry_run, "steps": {},
        "auto_schedule": {"skipped_recently": recently, "window_hours": 1},
    }
    if recently:
        report["note"] = "Skipped: maintenance was run within the last hour"
        return report

    report["steps"]["embedding_doctor"] = memory_core.embedding_doctor(config_path=config_path)
    try:
        report["steps"]["lifecycle_quality_cleanup"] = lifecycle.quality_cleanup(dry_run=dry_run, limit=limit, config_path=config_path)
    except Exception as exc:
        report["steps"]["lifecycle_quality_cleanup"] = {"ok": False, "error": str(exc), "retryable": "locked" in str(exc).lower()}

    # Semantic indexing is safe and idempotent. Keep bounded to avoid long MCP turns.
    try:
        report["steps"]["semantic_doctor"] = semantic_doctor(config_path=config_path)
        if not dry_run and report["steps"]["semantic_doctor"].get("ok"):
            vector_count = int(report["steps"]["semantic_doctor"].get("vector_count") or 0)
            if vector_count == 0:
                report["steps"]["semantic_index"] = semantic_index(config_path=config_path, rebuild=False, batch_size=4, limit=min(limit, 25))
            else:
                report["steps"]["semantic_index"] = {"ok": True, "skipped": True, "reason": "existing vector index present", "vector_count": vector_count}
            report["steps"]["semantic_verify"] = semantic_verify(config_path=config_path, query="Super Memory durable pack OpenClaw agent role baseline", limit=5)
    except Exception as exc:
        report["steps"]["semantic_error"] = str(exc)

    # Short-term promotion lifecycle
    report["steps"]["short_term_audit"] = memory_core.short_term_audit(limit=limit, config_path=config_path)
    report["steps"]["short_term_repair"] = memory_core.short_term_repair(limit=limit, dry_run=True, config_path=config_path)

    # Dreaming lifecycle
    report["steps"]["dreaming_audit"] = memory_core.dreaming_audit(config_path=config_path)
    if report["steps"].get("lifecycle_quality_cleanup", {}).get("retryable"):
        report["steps"]["dreaming_run"] = {"ok": True, "skipped": True, "reason": "database lock contention; retry maintenance later"}
    else:
        report["steps"]["dreaming_run"] = memory_core.dreaming_run(limit=min(limit, 200), dry_run=dry_run, config_path=config_path)

    # Self-improvement cycle (P4) — integrate preference detection
    try:
        from .self_improve import run_self_improve_cycle
        report["steps"]["self_improve"] = run_self_improve_cycle(config_path=config_path, dry_run=dry_run)
    except Exception as exc:
        report["steps"]["self_improve"] = {"ok": False, "error": str(exc)}

    # Schema assimilation (P2) — integrate with lifecycle
    try:
        if not _was_run_recently(config_path, "schema_assimilation", within_hours=4):
            from .schema_assimilation import run_schema_assimilation as _run
            from .config import load_config as _lc
            from .storage import SuperMemoryStore
            cfg = _lc(config_path)
            store = SuperMemoryStore(cfg)
            report["steps"]["schema_assimilation"] = _run(store, dry_run=dry_run)
            _record_run(config_path, "schema_assimilation")
        else:
            report["steps"]["schema_assimilation"] = {"ok": True, "skipped": True, "reason": "run within last 4 hours"}
    except Exception as exc:
        report["steps"]["schema_assimilation"] = {"ok": False, "error": str(exc)}

    # Hippocampal replay (P1) — integrate with lifecycle
    try:
        if not _was_run_recently(config_path, "hippocampal_replay", within_hours=2):
            from .hippocampal_replay import run_hippocampal_replay as _run, HippocampalReplayConfig
            from .config import load_config as _lc
            from .storage import SuperMemoryStore
            cfg = _lc(config_path)
            store = SuperMemoryStore(cfg)
            hc = HippocampalReplayConfig(dry_run=dry_run)
            report["steps"]["hippocampal_replay"] = _run(store, hc)
            _record_run(config_path, "hippocampal_replay")
        else:
            report["steps"]["hippocampal_replay"] = {"ok": True, "skipped": True, "reason": "run within last 2 hours"}
    except Exception as exc:
        report["steps"]["hippocampal_replay"] = {"ok": False, "error": str(exc)}

    from . import bridge
    report["steps"]["cross_layer_health"] = bridge.cross_layer_health(config_path=config_path)
    report["steps"]["durable_pack_status"] = bridge.durable_pack_status(config_path=config_path)
    report["ok"] = all(not isinstance(v, dict) or v.get("ok", True) for v in report["steps"].values())

    _record_run(config_path, "maintenance_run")
    return report
