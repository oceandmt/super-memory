from pathlib import Path
from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService
from super_memory.project_inference import backfill_projects


def cfg(tmp_path: Path) -> SuperMemoryConfig:
    return SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")


def test_save_infers_project_from_source_path(tmp_path: Path):
    c = cfg(tmp_path)
    svc = SuperMemoryService(c)
    rec = MemoryRecord(content="Project path inference test", type=MemoryType.FACT, scope=MemoryScope.PROJECT, source="/x/projects/alpha-repo/file.md")
    out = svc.save(rec)
    assert any(r.ok for r in out)
    got = svc.store.get_memory(rec.id, layer="workspace_markdown")
    assert got.project == "alpha-repo"
    assert got.metadata.get("project_inferred") is True


def test_backfill_projects_infers_super_memory(tmp_path: Path):
    c = cfg(tmp_path)
    svc = SuperMemoryService(c)
    rec = MemoryRecord(content="Super Memory backfill project inference", type=MemoryType.FACT, scope=MemoryScope.PROJECT)
    assert any(r.ok for r in svc.save(rec))
    # clear project to simulate legacy row
    with svc.store.connect() as conn:
        conn.execute("UPDATE memories SET project=NULL WHERE id=?", (rec.id,))
        conn.commit()
    import super_memory.project_inference as pi
    old = pi.load_config
    pi.load_config = lambda config_path=None: c
    try:
        res = backfill_projects(dry_run=False)
    finally:
        pi.load_config = old
    assert res["updated"] >= 1
    got = svc.store.get_memory(rec.id, layer="workspace_markdown")
    assert got.project in {"super-memory", "super-memory-github"}
