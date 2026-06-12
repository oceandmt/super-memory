from pathlib import Path

from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.promote import promote_both
from super_memory.service import SuperMemoryService


def test_promote_to_memory_and_register(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(cfg)
    record = MemoryRecord(
        id="promote-decision-1",
        content="Super Memory derived layers must remain downstream of Workspace Markdown.",
        type=MemoryType.DECISION,
        scope=MemoryScope.SHARED,
        agent_id="lucas",
        project="super-memory",
    )
    svc.save(record)

    memory_path, register_path = promote_both(cfg, record)

    assert memory_path is not None
    assert register_path is not None
    assert "promote-decision-1" in (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "promote-decision-1" in (tmp_path / "memory/registers/decisions.md").read_text(encoding="utf-8")

    # idempotent promotion
    promote_both(cfg, record)
    assert (tmp_path / "MEMORY.md").read_text(encoding="utf-8").count("promote-decision-1") == 1
