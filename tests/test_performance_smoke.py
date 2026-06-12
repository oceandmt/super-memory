from pathlib import Path

from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService


def test_batch_save_and_prefetch_smoke(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(cfg)

    for idx in range(50):
        record = MemoryRecord(
            content=f"super-memory performance smoke item {idx} canonical local truth",
            type=MemoryType.CONTEXT,
            scope=MemoryScope.PROJECT,
            agent_id="lucas" if idx % 2 == 0 else "alex",
            project="super-memory",
            tags=["perf-smoke", f"item-{idx}"],
        )
        results = svc.save(record)
        assert all(result.ok for result in results)

    hits = svc.prefetch("canonical", limit=10)
    assert 1 <= len(hits) <= 10
    assert any("canonical local truth" in hit.content for hit in hits)
