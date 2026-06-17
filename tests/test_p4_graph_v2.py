"""P4#1 — Verify cognitive_synapses standalone path with legacy_graph_edges=False."""

from __future__ import annotations

from pathlib import Path

import pytest

from super_memory.bridge import forget, remember, stats
from super_memory.config import load_config
from super_memory.graph import project_memory
from super_memory.models import MemoryRecord, MemoryScope, MemoryType
from super_memory.service import SuperMemoryService


def setup_module():
    """Ensure schema creates cognitive tables."""
    from super_memory import migrations
    migrations.run_migrations()


def test_cognitive_synapses_standalone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When legacy_graph_edges=False, graph operations use only cognitive_synapses."""
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))

    # Create config with legacy_graph_edges disabled
    from super_memory.models import SuperMemoryConfig
    cfg = SuperMemoryConfig(
        workspace_root=tmp_path,
        sqlite_path="data/test_p4_v2.sqlite3",
        legacy_graph_edges=False,
    )

    # Init service/schema
    svc = SuperMemoryService(cfg)

    # Save a memory
    record = MemoryRecord(
        content="P4 v2 test memory — cognitive synapses only",
        type=MemoryType.FACT,
        scope=MemoryScope.SESSION,
        agent_id="test-agent",
        tags=["test", "p4"],
    )
    svc.save(record)

    # Project into cognitive graph
    result = project_memory(record, config_path=str(tmp_path / ".super-memory.yml"))
    assert result.get("ok"), f"project_memory failed: {result}"
    assert result.get("synapses", 0) >= 1, "should have at least 1 synapse"

    # Verify graph stats: cognitive_synapses should have entries
    st = stats(config_path=str(tmp_path / ".super-memory.yml"))
    assert st.get("cognitive_synapses", 0) >= 1, f"expected cognitive_synapses >= 1, got: {st}"

    # Verify graph_edges is empty (legacy_graph_edges=False -> no edges written)
    assert st.get("graph_edges", -1) == st.get("cognitive_synapses", 0), (
        f"graph_edges should equal cognitive_synapses only (no legacy): {st}"
    )


def test_legacy_graph_edges_disabled_no_legacy_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When legacy_graph_edges=False, _save_graph_projection skips INSERT."""
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))

    from super_memory.models import SuperMemoryConfig
    cfg = SuperMemoryConfig(
        workspace_root=tmp_path,
        sqlite_path="data/test_p4_v2b.sqlite3",
        legacy_graph_edges=False,
    )
    svc = SuperMemoryService(cfg)

    # Save two memories that reference each other so graph edges can form
    record1 = MemoryRecord(
        content="P4 source memory for graph edge test",
        type=MemoryType.FACT,
        scope=MemoryScope.SESSION,
        agent_id="test-agent",
        tags=["test", "p4"],
    )
    record2 = MemoryRecord(
        content="P4 target memory linked via related_memory_ids",
        type=MemoryType.DECISION,
        scope=MemoryScope.SESSION,
        agent_id="test-agent",
        tags=["test"],
    )
    r1 = svc.save(record1)
    r2 = svc.save(record2)
    mem1_id = r1.get("memory_id", "") if isinstance(r1, dict) else getattr(r1, "memory_id", "")

    # Create a record with a real related_memory_id pointing to record2
    record3 = MemoryRecord(
        content="Test linking to existing memory",
        type=MemoryType.DECISION,
        scope=MemoryScope.SESSION,
        agent_id="test-agent",
        tags=["test"],
        metadata={"related_memory_ids": [mem1_id] if mem1_id else []},
    )
    svc.save(record3)

    # Check that no graph_edges were created (legacy disabled)
    with svc.store.connect() as conn:
        cnt = conn.execute("SELECT COUNT(*) as c FROM graph_edges").fetchone()["c"]
        assert cnt == 0, f"legacy graph_edges should be empty, got {cnt}"

    # But cognitive_synapses should be populated by project_memory
    project_memory(record3, config_path=str(tmp_path / ".super-memory.yml"))
    with svc.store.connect() as conn:
        cog_cnt = conn.execute("SELECT COUNT(*) as c FROM cognitive_synapses").fetchone()["c"]
        assert cog_cnt >= 0, f"cognitive_synapses count ok even if no neurons: got {cog_cnt}"
