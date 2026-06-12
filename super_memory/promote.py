from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .models import MemoryRecord, MemoryType, SuperMemoryConfig


PROMOTABLE_TYPES = frozenset(
    {
        MemoryType.DECISION,
        MemoryType.DOCTRINE,
        MemoryType.PREFERENCE,
        MemoryType.BLOCKER,
        MemoryType.WORKFLOW,
        MemoryType.LESSON,
    }
)

REGISTER_MAP: dict[MemoryType, str] = {
    MemoryType.DOCTRINE: "doctrine.md",
    MemoryType.PREFERENCE: "preferences.md",
    MemoryType.BLOCKER: "blockers.md",
    MemoryType.WORKFLOW: "workflows.md",
    MemoryType.DECISION: "decisions.md",
    MemoryType.LESSON: "lessons.md",
}


def promote_to_long_term(
    config: SuperMemoryConfig,
    record: MemoryRecord,
) -> str | None:
    """Promote a durable memory to MEMORY.md (curated recap).

    Only runs when the record type is in PROMOTABLE_TYPES.
    Returns the destination path or None.
    """
    if record.type not in PROMOTABLE_TYPES:
        return None

    root = Path(config.workspace_root)
    path = root / config.long_term_file
    path.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = (
        f"- {ts} [{record.agent_id}] [{record.type.value}/{record.scope.value}]: "
        f"{record.content} (project={record.project or 'global'}; id={record.id})\n"
    )

    mode = "a" if path.exists() else "w"
    content = f"{line}" if mode == "w" else (
        f"\n{line}"
        if not _line_already_present(path, record.id)
        else ""
    )
    if not content:
        return str(path)

    with open(path, mode, encoding="utf-8") as fh:
        fh.write(content)
    return str(path)


def promote_to_register(
    config: SuperMemoryConfig,
    record: MemoryRecord,
) -> str | None:
    """Promote a type-specific memory to the matching canonical register."""
    if record.type not in PROMOTABLE_TYPES:
        return None
    fname = REGISTER_MAP.get(record.type)
    if not fname:
        return None

    root = Path(config.workspace_root)
    reg_dir = root / config.registers_dir
    reg_dir.mkdir(parents=True, exist_ok=True)
    path = reg_dir / fname

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = (
        f"- {ts} [{record.agent_id}] "
        f"{record.content} "
        f"(scope={record.scope.value}; project={record.project or 'global'}; id={record.id})\n"
    )

    if _line_already_present(path, record.id):
        return str(path)

    if not path.exists():
        header = f"# {_register_title(record.type)}\n\n"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header + line)
    else:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    return str(path)


def promote_both(
    config: SuperMemoryConfig,
    record: MemoryRecord,
) -> tuple[str | None, str | None]:
    """Convenience: promote to both MEMORY.md and the type register."""
    return (
        promote_to_long_term(config, record),
        promote_to_register(config, record),
    )


def promote_daily_highlights(
    config: SuperMemoryConfig,
    *records: MemoryRecord,
) -> dict[str, tuple[str | None, str | None]]:
    out: dict[str, tuple[str | None, str | None]] = {}
    for record in records:
        out[record.id] = promote_both(config, record)
    return out


def _line_already_present(path: Path, memory_id: str) -> bool:
    if not path.exists():
        return False
    needle = f"id={memory_id}"
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if needle in line:
                return True
    except Exception:
        return False
    return False


def _register_title(memory_type: MemoryType) -> str:
    titles = {
        MemoryType.DOCTRINE: "Doctrine Register",
        MemoryType.PREFERENCE: "Preferences Register",
        MemoryType.BLOCKER: "Blocker Register",
        MemoryType.WORKFLOW: "Workflow Register",
        MemoryType.DECISION: "Decision Register",
        MemoryType.LESSON: "Lesson Register",
    }
    return titles.get(memory_type, memory_type.value.title())
