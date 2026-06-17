from __future__ import annotations

from .models import MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService

LESSON_TRIGGERS = ("fixed", "resolved", "learned", "blocker", "failure", "regression", "workflow")


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
    return f"""# {title}\n\n## Lesson\n\n{lesson}\n\n## Proposed reusable procedure\n\n{steps}\n\n## Review requirement\n\nThis is a candidate procedural memory. It should be reviewed before being promoted into a live OpenClaw skill or durable doctrine register.\n"""
