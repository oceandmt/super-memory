from pathlib import Path

from super_memory.models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType, SaveResult, SuperMemoryConfig
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


def test_markdown_failure_falls_back_to_sqlite_layers(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(cfg)

    class FailingMarkdownBackend:
        def save(self, record: MemoryRecord) -> SaveResult:
            raise PermissionError("markdown path unavailable")

        def recall(self, query: str, limit: int = 10) -> list[MemoryRecord]:
            return []

    svc.backends[MemoryLayer.WORKSPACE_MARKDOWN] = FailingMarkdownBackend()
    record = MemoryRecord(
        content="fallback save should still preserve data in sqlite layers",
        type=MemoryType.EVENT,
        scope=MemoryScope.SESSION,
        agent_id="lucas",
        project="super-memory",
    )

    results = svc.save(record)

    assert results[0].layer == MemoryLayer.WORKSPACE_MARKDOWN
    assert not results[0].ok
    assert [r.layer for r in results[1:]] == [
        MemoryLayer.MEMPALACE,
        MemoryLayer.HONCHO,
        MemoryLayer.NEURAL_MEMORY,
    ]
    assert all(r.ok for r in results[1:])
    assert all(r.pending_canonical_sync for r in results[1:])

    hits = svc.recall("fallback", limit=5)
    assert hits[MemoryLayer.MEMPALACE]
    assert hits[MemoryLayer.HONCHO]
    assert hits[MemoryLayer.NEURAL_MEMORY]
