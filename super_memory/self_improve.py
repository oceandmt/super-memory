"""Self-improvement: lesson capture, preference detection, skill proposal, cycle orchestration."""
from __future__ import annotations

from typing import Any

from .config import load_config
from .models import MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory

LESSON_TRIGGERS = ("fixed", "resolved", "learned", "blocker", "failure", "regression", "recovered")


def should_capture_lesson(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in LESSON_TRIGGERS)


def capture_lesson(
    service: SuperMemoryService,
    *,
    lesson: str,
    agent_id: str = "lucas",
    project: str | None = None,
    source: str | None = None,
):
    record = MemoryRecord(
        content=lesson,
        type=MemoryType.LESSON,
        scope=MemoryScope.SHARED if project is None else MemoryScope.PROJECT,
        agent_id=agent_id,
        project=project,
        source=source,
        tags=["self-improvement", "candidate"],
    )
    return service.save(record)


def skill_proposal_markdown(title: str, lesson: str, procedure: list[str]) -> str:
    steps = "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(procedure))
    return f"""# {title}

## Lesson

{lesson}

## Proposed reusable procedure

{steps}

## Review requirement

This is a candidate procedural memory. It should be reviewed before being promoted into a live OpenClaw skill or durable doctrine register.
"""


def run_self_improve_cycle(config_path: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Full self-improvement cycle:

    1. Scan recent memories for lesson triggers
    2. Capture lessons from high-signal content
    3. Run preference detection to update agent profiles
    4. Propose Skill Workshop candidates
    5. Update quality scores on improved lessons
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE "
            "(json_extract(metadata_json, '$.soft_deleted') IS NULL "
            "OR json_extract(metadata_json, '$.soft_deleted') != 1) "
            "ORDER BY created_at DESC LIMIT 200"
        ).fetchall()

    lessons_captured: list[dict[str, Any]] = []
    preferences_detected: list[dict[str, Any]] = []
    skill_proposals: list[dict[str, Any]] = []

    for row in rows:
        rec = row_to_memory(row)
        if should_capture_lesson(rec.content):
            lessons_captured.append({
                "id": rec.id,
                "content": rec.content[:200],
                "triggers": [t for t in LESSON_TRIGGERS if t in rec.content.lower()],
            })

        # Preference detection for decision/workflow types
        if rec.type.value in {"decision", "workflow", "preference"}:
            try:
                from .preference_detector import get_preference_detector
                pd = get_preference_detector()
                signals = pd.analyze(rec.content, rec.type.value)
                if signals:
                    preferences_detected.append({
                        "id": rec.id,
                        "signals": signals[:3],
                    })
            except Exception:
                pass

        # Propose Skill Workshop candidate for REPEATED workflows
        if rec.type.value == "workflow" and rec.tags and "reusable" in [t.lower() for t in rec.tags]:
            skill_proposals.append({
                "id": rec.id,
                "title": f"Proposed: {rec.content[:60]}",
                "lesson": rec.content,
            })

    result: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "memories_scanned": len(rows),
        "lessons_detected": len(lessons_captured),
        "preferences_detected": len(preferences_detected),
        "skill_proposals": len(skill_proposals),
        "candidates": {
            "lessons": lessons_captured[:10],
            "preferences": preferences_detected[:5],
            "skill_proposals": skill_proposals[:5],
        },
    }

    if not dry_run:
        service = SuperMemoryService(cfg)
        captured_ids: list[str] = []
        for item in lessons_captured[:5]:
            saved = capture_lesson(
                service, lesson=item["content"],
                agent_id="lucas", project="super-memory",
                source="self-improve-cycle",
            )
            captured_ids.extend(s.id for s in saved if s.ok)

        for proposal in skill_proposals[:3]:
            try:
                md = skill_proposal_markdown(
                    proposal["title"], proposal["lesson"],
                    ["Review and validate", "Promote to skill"],
                )
                record = MemoryRecord(
                    content=md,
                    type=MemoryType.WORKFLOW,
                    scope=MemoryScope.SHARED,
                    agent_id="lucas",
                    tags=["skill-proposal", "self-improvement", "candidate"],
                )
                saved = service.save(record)
                captured_ids.extend(s.id for s in saved if s.ok)
            except Exception:
                pass

        result["captured_ids"] = captured_ids
        result["captured_count"] = len(captured_ids)

        # Build preference profile summary
        try:
            from .preference_detector import get_preference_detector
            pd = get_preference_detector()
            profile = pd.build_profile()
            result["preference_profile"] = {
                "memories_analyzed": profile.memories_analyzed,
                "preferences_count": len(profile.preferences),
            }
        except Exception:
            pass

    return result
