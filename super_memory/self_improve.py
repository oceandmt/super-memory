"""Governed self-improvement proposal generation.

The cycle reads bounded memory and release evidence, but never captures lessons
or skills directly into canonical memory. Live mode only enqueues deterministic
pending proposals; dry-run is strictly read-only.
"""
from __future__ import annotations

import re
from typing import Any

from .config import load_config
from .dream_governance import (
    MAX_PROPOSALS_PER_RUN,
    build_proposal,
    deterministic_run_key,
    enqueue_proposal,
    is_generated_record,
    list_proposals,
    readonly_connection,
    resolve_proposal,
)
from .storage import SuperMemoryStore, row_to_memory

LESSON_TRIGGERS = ("fixed", "resolved", "learned", "blocker", "failure", "regression", "recovered")
_MAX_SCAN = 200
_MAX_CANDIDATES = 10


def should_capture_lesson(text: str) -> bool:
    lowered = (text or "")[:20_000].lower()
    return any(re.search(rf"\b{re.escape(trigger)}\b", lowered) for trigger in LESSON_TRIGGERS)

def _lesson_observation(text: str) -> dict[str, str] | None:
    """Extract bounded problem/action/outcome evidence; never invent a lesson."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text[:20_000]) if s.strip()]
    problem = next((s for s in sentences if re.search(r"\b(blocker|failure|regression|failed|error)\b", s, re.I)), "")
    action = next((s for s in sentences if re.search(r"\b(fixed|resolved|changed|implemented|reverted)\b", s, re.I)), "")
    outcome = next((s for s in sentences if re.search(r"\b(recovered|passed|verified|succeeded|working)\b", s, re.I)), "")
    # A resolved/fixed statement can carry action and outcome when no separate
    # verification sentence exists; retain that weaker provenance explicitly.
    if not outcome and action and re.search(r"\b(fixed|resolved)\b", action, re.I):
        outcome = action
    if not (problem and action and outcome):
        return None
    return {"problem": problem[:1000], "action": action[:1000], "outcome": outcome[:1000]}


def _release_summary(release_evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Reduce arbitrary release evidence to stable, bounded decision signals."""
    evidence = release_evidence or {}
    benchmark = evidence.get("benchmark") if isinstance(evidence.get("benchmark"), dict) else {}
    results = benchmark.get("results") if isinstance(benchmark.get("results"), list) else []
    failures = []
    for result in results[:50]:
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
        "gate": str(evidence.get("gate") or "unknown")[:100],
        "ok": bool(evidence.get("ok", benchmark.get("ok", False))),
        "total": int(benchmark.get("total", len(results)) or 0),
        "passed": int(benchmark.get("passed", 0) or 0),
        "failed": int(benchmark.get("failed", len(failures)) or 0),
        "failures": failures[:20],
    }


def _enqueue_candidates(
    store: SuperMemoryStore,
    candidates: list[dict[str, Any]],
    *,
    run_key: str,
    dry_run: bool,
) -> tuple[list[dict[str, Any]], int, int]:
    proposals: list[dict[str, Any]] = []
    queued = 0
    deduplicated = 0
    for candidate in candidates[:MAX_PROPOSALS_PER_RUN]:
        proposal = build_proposal(
            kind=candidate["kind"],
            content=candidate["content"],
            source_ids=candidate.get("source_ids", []),
            evidence=candidate.get("evidence", {}),
            action=candidate.get("action", {}),
            run_key=run_key,
        )
        outcome = enqueue_proposal(store, proposal, dry_run=dry_run)
        proposals.append(outcome["proposal"])
        queued += int(bool(outcome.get("created")))
        deduplicated += int(bool(outcome.get("deduplicated")))
    return proposals, queued, deduplicated


def capture_lesson(
    service: Any,
    *,
    lesson: str,
    agent_id: str = "lucas",
    project: str | None = None,
    source: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Compatibility API: propose a lesson instead of saving it canonically."""
    store = service.store
    proposal = build_proposal(
        kind="self_improvement_lesson",
        content=(lesson or "")[:4_000],
        source_ids=[source] if source else [],
        evidence={"requested_agent_id": agent_id, "project": project},
        action={"type": "create_memory", "memory_type": "lesson", "scope": "project" if project else "shared"},
    )
    return enqueue_proposal(store, proposal, dry_run=dry_run)


def skill_proposal_markdown(title: str, lesson: str, procedure: list[str]) -> str:
    bounded_steps = [str(step)[:500] for step in procedure[:20]]
    steps = "\n".join(f"{index + 1}. {step}" for index, step in enumerate(bounded_steps))
    return f"""# {str(title)[:200]}

## Lesson

{str(lesson)[:2_000]}

## Proposed reusable procedure

{steps}

## Review requirement

This is a candidate procedural memory. It requires explicit approval before promotion into a live skill or durable doctrine register.
"""[:4_000]


def run_self_improve_cycle(
    config_path: str | None = None,
    dry_run: bool = True,
    *,
    release_evidence: dict[str, Any] | None = None,
    limit: int = _MAX_SCAN,
) -> dict[str, Any]:
    """Detect lessons and safe fixes, returning or enqueuing proposals only."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    bounded_limit = max(1, min(int(limit), _MAX_SCAN))
    with readonly_connection(store) as conn:
        if conn is None:
            rows = []
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE "
                "COALESCE(json_extract(metadata_json, '$.soft_deleted'), 0) != 1 "
                "ORDER BY created_at DESC, id LIMIT ?",
                (bounded_limit,),
            ).fetchall()

    lesson_candidates: list[dict[str, Any]] = []
    preference_candidates: list[dict[str, Any]] = []
    skill_candidates: list[dict[str, Any]] = []
    consumed_ids: list[str] = []
    seen_memory_ids: set[str] = set()
    for row in rows:
        rec = row_to_memory(row)
        if rec.id in seen_memory_ids:
            continue
        seen_memory_ids.add(rec.id)
        if is_generated_record(agent_id=rec.agent_id, source=rec.source, metadata=rec.metadata):
            continue
        consumed_ids.append(rec.id)
        observation = _lesson_observation(rec.content)
        if observation and len(lesson_candidates) < _MAX_CANDIDATES:
            triggers = [trigger for trigger in LESSON_TRIGGERS if re.search(rf"\b{re.escape(trigger)}\b", rec.content, re.I)]
            lesson_candidates.append(
                {
                    "kind": "self_improvement_lesson",
                    "content": "Proposed lesson candidate from trigger-matched source. "
                               f"Problem: {observation['problem']} Action: {observation['action']} Outcome: {observation['outcome']}",
                    "source_ids": [rec.id],
                    "evidence": {"triggers": triggers, "source_type": rec.type.value, "extraction": observation, "label": "trigger-matched source"},
                    "action": {"type": "create_memory", "memory_type": "lesson", "scope": "project"},
                }
            )

        if rec.type.value in {"decision", "workflow", "preference"} and len(preference_candidates) < 5:
            # Detection is read-only. Signals remain evidence and are not applied
            # to an agent profile by this cycle.
            try:
                from .preference_detector import get_preference_detector

                signals = get_preference_detector().analyze(rec.content[:4_000], rec.type.value)
            except Exception:
                signals = []
            if signals:
                preference_candidates.append(
                    {
                        "id": rec.id,
                        "signals": signals[:3],
                        "status": "observed_not_applied",
                    }
                )

        if (
            rec.type.value == "workflow"
            and "reusable" in {tag.lower() for tag in (rec.tags or [])}
            and len(skill_candidates) < 5
        ):
            title = f"Proposed: {rec.content[:60]}"
            skill_candidates.append(
                {
                    "kind": "self_improvement_skill",
                    "content": skill_proposal_markdown(
                        title,
                        rec.content,
                        ["Review source evidence", "Validate in isolation", "Promote only after approval"],
                    ),
                    "source_ids": [rec.id],
                    "evidence": {"source_type": rec.type.value, "source_tags": (rec.tags or [])[:20]},
                    "action": {"type": "propose_skill", "promotion_requires_separate_action": True},
                }
            )

    release = _release_summary(release_evidence)
    release_candidates: list[dict[str, Any]] = []
    for failure in release["failures"][:10]:
        source_id = f"release-case:{failure['case']}"
        release_candidates.append(
            {
                "kind": "self_improvement_fix",
                "content": f"Propose a bounded recall fix for failed release case: {failure['case']}",
                "source_ids": [source_id],
                "evidence": {"release_gate": release, "failure": failure},
                "action": {
                    "type": "investigate_recall_failure",
                    "case": failure["case"],
                    "auto_apply": False,
                },
            }
        )

    all_candidates = [*lesson_candidates, *skill_candidates, *release_candidates][:MAX_PROPOSALS_PER_RUN]
    run_key = deterministic_run_key(
        "self-improve-cycle-v2",
        inputs={
            "limit": bounded_limit,
            "release": release,
            "candidate_kinds": [candidate["kind"] for candidate in all_candidates],
        },
        source_ids=[source_id for candidate in all_candidates for source_id in candidate.get("source_ids", [])],
    )
    proposals, queued, deduplicated = _enqueue_candidates(
        store,
        all_candidates,
        run_key=run_key,
        dry_run=dry_run,
    )

    return {
        "ok": True,
        "dry_run": dry_run,
        "run_key": run_key,
        "governance": {
            "state": "preview" if dry_run else "pending_approval",
            "canonical_mutation_disabled": True,
            "review_required": True,
        },
        "memories_scanned": len(seen_memory_ids),
        "source_memories_consumed": len(consumed_ids),
        "lessons_detected": len(lesson_candidates),
        "preferences_detected": len(preference_candidates),
        "skill_proposals": len(skill_candidates),
        "release_evidence": release,
        "release_fix_proposals": len(release_candidates),
        "proposals_queued": queued,
        "deduplicated": deduplicated,
        "captured_count": 0,
        "captured_ids": [],
        "candidates": {
            "lessons": lesson_candidates,
            "preferences": preference_candidates,
            "skill_proposals": skill_candidates,
            "release_fixes": release_candidates,
        },
        "proposals": proposals,
    }


def self_improvement_list_pending(
    store: SuperMemoryStore,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    proposals: list[dict[str, Any]] = []
    for kind in ("self_improvement_lesson", "self_improvement_skill", "self_improvement_fix"):
        proposals.extend(list_proposals(store, kind=kind, status="pending", limit=limit))
    proposals.sort(key=lambda item: (item.get("created_at") or "", item["id"]), reverse=True)
    bounded = proposals[: max(1, min(int(limit), 500))]
    return {"ok": True, "pending": bounded, "count": len(bounded)}


def self_improvement_resolve(
    store: SuperMemoryStore,
    proposal_id: str,
    *,
    decision: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Resolve review state only; applying a fix remains a separate operator action."""
    apply = (lambda _proposal: None) if decision == "approved" else None
    return resolve_proposal(store, proposal_id, decision=decision, apply=apply, note=note)
