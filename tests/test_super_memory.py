from pathlib import Path

from super_memory.models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService


def test_save_order_and_recall(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(cfg)
    record = MemoryRecord(
        content="Boss prefers canonical markdown first for super-memory.",
        type=MemoryType.PREFERENCE,
        scope=MemoryScope.SHARED,
        agent_id="lucas",
        project="super-memory",
        tags=["test"],
    )

    results = svc.save(record)

    assert [r.layer for r in results] == [
        MemoryLayer.WORKSPACE_MARKDOWN,
        MemoryLayer.MEMPALACE,
        MemoryLayer.HONCHO,
        MemoryLayer.NEURAL_MEMORY,
    ]
    assert all(r.ok for r in results)
    assert list((tmp_path / "memory").glob("*.md"))

    hits = svc.recall("canonical", limit=5)
    assert hits[MemoryLayer.MEMPALACE]
    assert hits[MemoryLayer.HONCHO]
    assert hits[MemoryLayer.NEURAL_MEMORY]
