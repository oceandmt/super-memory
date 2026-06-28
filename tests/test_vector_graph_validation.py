from pathlib import Path
from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService
from super_memory.validation import vector_coverage, graph_multihop_validation
from super_memory import graph


def test_vector_coverage_reports_shape(tmp_path: Path, monkeypatch):
    c = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(c)
    svc.save(MemoryRecord(content="vector coverage validation memory", type=MemoryType.FACT, scope=MemoryScope.PROJECT, project="test"))
    import super_memory.validation as validation
    monkeypatch.setattr(validation, "load_config", lambda config_path=None: c)
    r = vector_coverage()
    assert r["ok"] is True
    assert r["active_canonical"] >= 1
    assert "coverage" in r


def test_graph_multihop_validation_reports_stats(tmp_path: Path, monkeypatch):
    c = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(c)
    rec = MemoryRecord(content="graph multihop validation memory about alpha beta", type=MemoryType.FACT, scope=MemoryScope.PROJECT, project="test", tags=["alpha", "beta"])
    svc.save(rec)
    graph.init_tables(svc.store)
    import super_memory.validation as validation
    monkeypatch.setattr(graph, "_store", lambda config_path=None: svc.store)
    graph.project_memory(rec, config_path=None)
    monkeypatch.setattr(validation, "load_config", lambda config_path=None: c)
    monkeypatch.setattr(validation._graph, "_store", lambda config_path=None: svc.store)
    r = graph_multihop_validation(query="alpha beta", limit=5)
    assert r["ok"] is True
    assert r["neurons_total"] > 0
    assert r["synapses_total"] > 0
