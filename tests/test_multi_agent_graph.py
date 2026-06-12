from pathlib import Path

from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService


def test_multi_agent_graph_recall(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(cfg)

    lucas = MemoryRecord(
        id="m-lucas-decision",
        content="Lucas decided Workspace Markdown remains canonical truth.",
        type=MemoryType.DECISION,
        scope=MemoryScope.SHARED,
        agent_id="lucas",
        project="super-memory",
    )
    alex = MemoryRecord(
        id="m-alex-workflow",
        content="Alex should use Super Memory sync_turn after durable implementation updates.",
        type=MemoryType.WORKFLOW,
        scope=MemoryScope.CROSS_AGENT,
        agent_id="alex",
        project="super-memory",
        metadata={"related_memory_ids": ["m-lucas-decision"], "relation": "related_to"},
    )
    maxm = MemoryRecord(
        id="m-max-blocker",
        content="Max noted derived layers must not outrank canonical markdown.",
        type=MemoryType.BLOCKER,
        scope=MemoryScope.CROSS_AGENT,
        agent_id="max",
        project="super-memory",
        metadata={"related_memory_ids": ["m-alex-workflow"], "relation": "caused_by"},
    )

    for record in [lucas, alex, maxm]:
        results = svc.save(record)
        assert all(result.ok for result in results)

    graph_hits = svc.recall_graph("m-max-blocker", depth=2)
    ids = [record.id for record in graph_hits]

    assert "m-max-blocker" in ids
    assert "m-alex-workflow" in ids
    assert "m-lucas-decision" in ids

    prefetch = svc.prefetch("canonical", limit=10)
    assert any(record.agent_id in {"lucas", "alex", "max"} for record in prefetch)
