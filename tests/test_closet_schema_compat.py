from pathlib import Path
from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService
from super_memory.projections.closet import rebuild_closets, closet_stats


def test_closet_rebuild_marks_long_memory_and_keeps_spatial_columns(tmp_path: Path, monkeypatch):
    c = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    svc = SuperMemoryService(c)
    rec = MemoryRecord(content=("long memory evidence citation " * 120), type=MemoryType.FACT, scope=MemoryScope.PROJECT, project="super-memory")
    assert any(r.ok for r in svc.save(rec))
    import super_memory.projections.closet as closet
    monkeypatch.setattr(closet, "load_config", lambda config_path=None: c)
    out = rebuild_closets(limit=10)
    assert out["errors"] == []
    got = svc.store.get_memory(rec.id, layer="workspace_markdown")
    assert got.metadata.get("compression_policy") == "verbatim_drawers_plus_summary"
    with svc.store.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(palace_drawers)").fetchall()}
    assert {"drawer_id", "wing", "room", "hall"}.issubset(cols)
    assert closet_stats()["drawer_count"] > 0
