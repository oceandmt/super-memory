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

def test_cjk_search_respects_requested_corpus_and_actual_layer(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(cfg)
    record = MemoryRecord(
        id="compat-cjk-1",
        content="持久記憶需要保留正確的語料範圍以確保檢索準確性和一致性，這是測試目的",
        type=MemoryType.FACT,
        scope=MemoryScope.SHARED,
        agent_id="lucas",
        project="super-memory",
        tags=["cjk", "corpus"],
    )
    assert all(result.ok for result in svc.save(record))

    memory = memory_search_compatible(
        "持久記憶", max_results=10, corpus="memory", config=cfg
    )
    assert memory["results"]
    assert {hit["corpus"] for hit in memory["results"]} == {"memory"}
    assert {hit["layer"] for hit in memory["results"]} == {"workspace_markdown"}

    derived = memory_search_compatible(
        "持久記憶", max_results=10, corpus="super-memory", config=cfg
    )
    assert derived["results"]
    assert {hit["corpus"] for hit in derived["results"]} == {"super-memory"}
    assert all(hit["layer"] != "workspace_markdown" for hit in derived["results"])

    sessions = memory_search_compatible(
        "持久記憶", max_results=10, corpus="sessions", config=cfg
    )
    assert sessions["results"] == []
