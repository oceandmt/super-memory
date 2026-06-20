from __future__ import annotations

from typing import Any

from . import memory_core
from . import lifecycle
from .semantic import semantic_doctor, semantic_index, semantic_verify



def maintenance_run(*, dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Run safe Super Memory maintenance in canonical-first order.

    This is intentionally non-destructive except for soft-delete/metadata marks in
    lifecycle cleanup when dry_run is false. It never hard-deletes or truncates
    canonical markdown.
    """
    report: dict[str, Any] = {"ok": True, "dry_run": dry_run, "steps": {}}
    report["steps"]["embedding_doctor"] = memory_core.embedding_doctor(config_path=config_path)
    report["steps"]["lifecycle_quality_cleanup"] = lifecycle.quality_cleanup(dry_run=dry_run, limit=limit, config_path=config_path)

    # Semantic indexing is safe and idempotent. Keep bounded to avoid long MCP turns.
    try:
        report["steps"]["semantic_doctor"] = semantic_doctor(config_path=config_path)
        if not dry_run and report["steps"]["semantic_doctor"].get("ok"):
            vector_count = int(report["steps"]["semantic_doctor"].get("vector_count") or 0)
            # Keep MCP maintenance bounded. Full/rebuild indexing belongs to
            # super_memory_semantic_index or an external cron/background run.
            if vector_count == 0:
                report["steps"]["semantic_index"] = semantic_index(config_path=config_path, rebuild=False, batch_size=4, limit=min(limit, 25))
            else:
                report["steps"]["semantic_index"] = {"ok": True, "skipped": True, "reason": "existing vector index present", "vector_count": vector_count}
            report["steps"]["semantic_verify"] = semantic_verify(config_path=config_path, query="Super Memory durable pack OpenClaw agent role baseline", limit=5)
    except Exception as exc:  # pragma: no cover - runtime optional dependencies
        report["steps"]["semantic_error"] = str(exc)

    # Promotion remains policy-gated and bounded.
    report["steps"]["short_term_audit"] = memory_core.short_term_audit(limit=limit, config_path=config_path)
    report["steps"]["short_term_repair"] = memory_core.short_term_repair(limit=limit, dry_run=True if dry_run else False, config_path=config_path)

    # Dreaming creates at most one compact artifact per run.
    report["steps"]["dreaming_audit"] = memory_core.dreaming_audit(config_path=config_path)
    report["steps"]["dreaming_run"] = memory_core.dreaming_run(limit=min(limit, 200), dry_run=dry_run, config_path=config_path)

    from . import bridge  # local import avoids circular import at module load
    report["steps"]["cross_layer_health"] = bridge.cross_layer_health(config_path=config_path)
    report["steps"]["durable_pack_status"] = bridge.durable_pack_status(config_path=config_path)
    report["ok"] = all(not isinstance(v, dict) or v.get("ok", True) for v in report["steps"].values())
    return report
