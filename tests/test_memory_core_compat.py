from pathlib import Path

from super_memory.compat import memory_get_compatible, memory_search_compatible
from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService


def test_memory_search_and_get_compatible_shapes(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(cfg)
    record = MemoryRecord(
        id="compat-decision-1",
        content="Super Memory must become a memory-slot replacement for OpenClaw memory-core.",
        type=MemoryType.DECISION,
        scope=MemoryScope.SHARED,
        agent_id="lucas",
        project="super-memory",
        tags=["memory-slot", "compat"],
    )
    assert all(result.ok for result in svc.save(record))

    payload = memory_search_compatible("memory-slot replacement", max_results=5, corpus="all", config=cfg)

    assert payload["provider"] == "super-memory"
    assert payload["results"]
    hit = payload["results"][0]
    for key in ["id", "path", "startLine", "endLine", "score", "textScore", "snippet", "source", "corpus"]:
        assert key in hit

    virtual = memory_get_compatible(f"super-memory://neural_memory/{record.id}", config=cfg)
    assert virtual["source"] == "super-memory"
    assert "memory-slot replacement" in virtual["content"]

    file_payload = memory_get_compatible("memory/2099-01-01.md", config=cfg)
    assert file_payload["error"] == "file not found"
