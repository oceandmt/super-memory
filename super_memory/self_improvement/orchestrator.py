"""Governed self-improvement control-plane orchestration.

This module consumes supplied audit/release evidence and proposes fixes. It
never executes maintenance actions or writes canonical memories. Dry-run is
strictly no-write and does not open the proposal database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..dream_governance import (
    MAX_PROPOSALS_PER_RUN,
    build_proposal,
    deterministic_run_key,
    enqueue_proposal,
)
from ..storage import SuperMemoryStore

_MAX_EVIDENCE_ITEMS = 50


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in list(sorted(value.items(), key=lambda pair: str(pair[0])))[:_MAX_EVIDENCE_ITEMS]:
        clean_key = str(key)[:100]
        if isinstance(item, str):
            result[clean_key] = item[:2_000]
        elif isinstance(item, (bool, int, float)) or item is None:
            result[clean_key] = item
        elif isinstance(item, list):
            result[clean_key] = item[:_MAX_EVIDENCE_ITEMS]
        elif isinstance(item, dict):
            result[clean_key] = _bounded_mapping(item)
        else:
            result[clean_key] = str(item)[:2_000]
    return result


def _release_summary(release_evidence: dict[str, Any] | None) -> dict[str, Any]:
    evidence = _bounded_mapping(release_evidence)
    benchmark = evidence.get("benchmark") if isinstance(evidence.get("benchmark"), dict) else {}
    results = benchmark.get("results") if isinstance(benchmark.get("results"), list) else []
    failures: list[dict[str, Any]] = []
    for result in results[:_MAX_EVIDENCE_ITEMS]:
        if not isinstance(result, dict) or result.get("ok", True):
            continue
        failures.append(
            {
                "case": str(result.get("name") or result.get("file") or result.get("query") or "unknown")[:200],
                "query": str(result.get("query") or "")[:500],
                "expected_contains": [str(item)[:100] for item in (result.get("expected_contains") or [])[:20]],
            }
        )
    return {
        "available": bool(evidence),
        "gate": str(evidence.get("gate") or "unknown")[:100],
        "ok": bool(evidence.get("ok", benchmark.get("ok", False))) if evidence else None,
        "total": int(benchmark.get("total", len(results)) or 0),
        "passed": int(benchmark.get("passed", 0) or 0),
        "failed": int(benchmark.get("failed", len(failures)) or 0),
        "failures": failures[:20],
    }


def _health_summary(health_evidence: dict[str, Any] | None) -> dict[str, Any]:
    evidence = _bounded_mapping(health_evidence)
    audit = evidence.get("audit") if isinstance(evidence.get("audit"), dict) else {}
    qualify = evidence.get("qualify") if isinstance(evidence.get("qualify"), dict) else {}
    debug = evidence.get("debug") if isinstance(evidence.get("debug"), dict) else {}
    return {
        "available": bool(evidence),
        "audit": {
            "grade": audit.get("grade"),
            "health_score": audit.get("health_score"),
            "issues": (audit.get("issues") or [])[:20] if isinstance(audit.get("issues"), list) else [],
        },
        "qualify": {
            "grade": qualify.get("grade"),
            "score": qualify.get("score"),
            "reasons": (qualify.get("reasons") or [])[:20] if isinstance(qualify.get("reasons"), list) else [],
        },
        "debug": {
            "problem_count": int(debug.get("problem_count", 0) or 0),
            "problems": (debug.get("problems") or [])[:20] if isinstance(debug.get("problems"), list) else [],
        },
    }


def _proposal_candidates(
    release: dict[str, Any],
    health: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for failure in release.get("failures", [])[:limit]:
        case = str(failure.get("case") or "unknown")[:200]
        candidates.append(
            {
                "kind": "self_improvement_fix",
                "content": f"Investigate and validate a bounded recall fix for failed release case: {case}",
                "source_ids": [f"release-case:{case}"],
                "evidence": {"release_gate": release, "failure": failure},
                "action": {"type": "investigate_recall_failure", "case": case, "auto_apply": False},
            }
        )

    for index, problem in enumerate(health.get("debug", {}).get("problems", [])[:limit]):
        if not isinstance(problem, dict):
            continue
        issue = str(problem.get("issue") or "unknown health problem")[:500]
        candidates.append(
            {
                "kind": "self_improvement_fix",
                "content": f"Review and validate a safe fix for health finding: {issue}",
                "source_ids": [f"health-debug:{index}:{issue[:100]}"],
                "evidence": {"problem": problem, "health": health},
                "action": {
                    "type": "operator_review_health_fix",
                    "suggested_fix": str(problem.get("fix") or "")[:500],
                    "auto_apply": False,
                },
            }
        )

    score = health.get("qualify", {}).get("score")
    if isinstance(score, (int, float)) and score < 70 and len(candidates) < limit:
        candidates.append(
            {
                "kind": "self_improvement_fix",
                "content": f"Review memory quality controls because qualification score is {score}.",
                "source_ids": ["health-qualify-score"],
                "evidence": {"qualify": health.get("qualify", {})},
                "action": {"type": "review_quality_controls", "auto_apply": False},
            }
        )
    return candidates[:limit]


def run_self_improvement_cycle(
    *,
    dry_run: bool = True,
    config_path: str | None = None,
    limit: int = 500,
    remember_lesson: bool = True,
    release_evidence: dict[str, Any] | None = None,
    health_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Consume evidence and create pending proposals without applying fixes.

    Evidence collection is intentionally external: historical collectors seed
    benchmark cases, write curriculum files, and run maintenance helpers. This
    orchestrator must not invoke those side effects, especially in dry-run.
    ``remember_lesson`` remains a compatibility argument but canonical lesson
    writes are disabled.
    """
    cfg = load_config(config_path)
    bounded_limit = max(1, min(int(limit), MAX_PROPOSALS_PER_RUN))
    release = _release_summary(release_evidence)
    health = _health_summary(health_evidence)
    candidates = _proposal_candidates(release, health, limit=bounded_limit)
    source_ids = [source_id for candidate in candidates for source_id in candidate["source_ids"]]
    run_key = deterministic_run_key(
        "self-improvement-orchestrator-v2",
        inputs={"release": release, "health": health, "limit": bounded_limit},
        source_ids=source_ids,
    )

    built = [
        build_proposal(
            kind=candidate["kind"],
            content=candidate["content"],
            source_ids=candidate["source_ids"],
            evidence=candidate["evidence"],
            action=candidate["action"],
            run_key=run_key,
        )
        for candidate in candidates
    ]
    proposals: list[dict[str, Any]] = []
    queued = 0
    deduplicated = 0
    if dry_run:
        proposals = [{**proposal, "would_enqueue": True} for proposal in built]
    else:
        store = SuperMemoryStore(cfg)
        for proposal in built:
            outcome = enqueue_proposal(store, proposal, dry_run=False)
            proposals.append(outcome["proposal"])
            queued += int(bool(outcome.get("created")))
            deduplicated += int(bool(outcome.get("deduplicated")))

    now = datetime.now(timezone.utc).isoformat()
    workspace = Path(cfg.workspace_root)
    return {
        "ok": True,
        "pipeline": "self_improvement_orchestrator_v2",
        "dry_run": dry_run,
        "run_key": run_key,
        "started_at": now,
        "finished_at": now,
        "audit": health.get("audit", {}),
        "qualify": health.get("qualify", {}),
        "debug": health.get("debug", {}),
        "benchmark": release,
        "proposals": proposals,
        "proposal_count": len(proposals),
        "proposals_queued": queued,
        "deduplicated": deduplicated,
        "safe_actions": [],
        "post_audit": health.get("audit", {}),
        "post_debug": health.get("debug", {}),
        "curriculum": {
            "generated": False,
            "reason": "curriculum generation requires separate explicit execution",
        },
        "governance": {
            "state": "preview" if dry_run else "pending_approval",
            "review_required": True,
            "auto_apply_disabled": True,
            "canonical_memory_writes": 0,
            "remember_lesson_requested": bool(remember_lesson),
            "remember_lesson_disabled": True,
        },
        "manual_approval_required": [
            "all generated fixes and lessons",
            "hard delete content",
            "change recall weights globally",
            "merge contradictory memories",
            "downgrade trust of human-provided facts",
        ],
        # Compatibility: older callers require an existing Path. The workspace
        # already exists; no report is created in dry-run or live mode.
        "report_path": str(workspace),
        "report_written": False,
    }
