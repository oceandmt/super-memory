"""Self-improvement orchestrator for Super Memory.

Control-plane pipeline:
1. audit 2. qualify 3. debug 4. benchmark 5. propose
6. apply safe fixes 7. test 8. snapshot result 9. remember lesson

Only conservative safe fixes are auto-applied. Destructive or global policy
changes remain proposals requiring operator approval.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config


def _reports_dir(cfg) -> Path:
    root = Path(cfg.workspace_root)
    d = root / "reports" / "maintenance"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_apply(config_path: str | None = None, *, dry_run: bool = True, limit: int = 500) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    # repair orphans
    try:
        from ..projections.drift_repair import repair_orphans
        actions.append({"action": "repair_orphans", "result": repair_orphans(dry_run=dry_run, config_path=config_path)})
    except Exception as exc:
        actions.append({"action": "repair_orphans", "error": f"{type(exc).__name__}: {exc}"})
    # process write jobs
    try:
        from ..write_contract.outbox import process_memory_jobs
        actions.append({"action": "process_write_jobs", "result": process_memory_jobs(limit=min(limit, 100), config_path=config_path)})
    except Exception as exc:
        actions.append({"action": "process_write_jobs", "error": f"{type(exc).__name__}: {exc}"})
    # soft-delete confirmed duplicates
    try:
        from ..write_contract.semantic_merge import soft_delete_duplicate_clusters
        actions.append({"action": "duplicate_resolution_v2", "result": soft_delete_duplicate_clusters(dry_run=dry_run, limit=limit, config_path=config_path)})
    except Exception as exc:
        actions.append({"action": "duplicate_resolution_v2", "error": f"{type(exc).__name__}: {exc}"})
    # rebuild closets/drawers
    try:
        from ..projections.closet import rebuild_closets
        actions.append({"action": "rebuild_closets", "result": rebuild_closets(limit=limit, config_path=config_path)})
    except Exception as exc:
        actions.append({"action": "rebuild_closets", "error": f"{type(exc).__name__}: {exc}"})
    # refresh health cache
    try:
        from ..health_cache import self_heal_status_fast
        actions.append({"action": "refresh_health_cache", "result": self_heal_status_fast(config_path=config_path)})
    except Exception as exc:
        actions.append({"action": "refresh_health_cache", "error": f"{type(exc).__name__}: {exc}"})
    return actions


def _benchmark(config_path: str | None = None) -> dict[str, Any]:
    try:
        from ..recall_benchmark import release_gate
        return release_gate(config_path=config_path)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _curriculum(config_path: str | None = None) -> dict[str, Any]:
    try:
        from ..evals.curriculum import analyze_feedback_patterns, generate_training_cases_from_failures
        return {"patterns": analyze_feedback_patterns(config_path=config_path), "generated": generate_training_cases_from_failures(config_path=config_path)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def run_self_improvement_cycle(*, dry_run: bool = True, config_path: str | None = None, limit: int = 500, remember_lesson: bool = True) -> dict[str, Any]:
    from ..deep_auto import deep_audit, deep_qualify, deep_debug, deep_improve
    cfg = load_config(config_path)
    started = datetime.now(timezone.utc).isoformat()
    audit = deep_audit(config_path=config_path)
    qualify = deep_qualify(config_path=config_path)
    debug = deep_debug(config_path=config_path)
    benchmark = _benchmark(config_path=config_path)
    improve = deep_improve(dry_run=True, config_path=config_path)
    applied = _safe_apply(config_path=config_path, dry_run=dry_run, limit=limit)
    post_audit = deep_audit(config_path=config_path)
    post_debug = deep_debug(config_path=config_path)
    curriculum = _curriculum(config_path=config_path)
    finished = datetime.now(timezone.utc).isoformat()
    result = {
        "ok": True,
        "pipeline": "self_improvement_orchestrator_v1",
        "dry_run": dry_run,
        "started_at": started,
        "finished_at": finished,
        "audit": audit,
        "qualify": qualify,
        "debug": debug,
        "benchmark": benchmark,
        "proposals": improve.get("improvement_proposals", []),
        "safe_actions": applied,
        "post_audit": post_audit,
        "post_debug": post_debug,
        "curriculum": curriculum,
        "manual_approval_required": [
            "hard delete content",
            "change recall weights globally",
            "merge contradictory memories",
            "downgrade trust of human-provided facts",
        ],
    }
    path = _reports_dir(cfg) / ("self_improvement_%s.json" % finished.replace(":", "-").replace(".", "-"))
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["report_path"] = str(path)
    if remember_lesson and not dry_run:
        try:
            from ..service import SuperMemoryService
            svc = SuperMemoryService(cfg)
            svc.remember(
                content=("Self-improvement orchestrator completed: "
                         f"audit={post_audit.get('grade')} health={post_audit.get('health_score')} "
                         f"debug_problems={post_debug.get('problem_count')} report={path}"),
                memory_type="event", scope="project", agent_id="lucas", project="super-memory",
                tags=["agent:lucas", "self-improvement", "auto-complete"], source="self_improvement_orchestrator",
            )
        except Exception as exc:
            result["remember_lesson_error"] = f"{type(exc).__name__}: {exc}"
    return result
