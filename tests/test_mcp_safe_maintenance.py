from pathlib import Path

from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService


def cfg(tmp_path: Path) -> SuperMemoryConfig:
    return SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")


def test_self_heal_status_fast_bounded(tmp_path: Path, monkeypatch):
    c = cfg(tmp_path)
    svc = SuperMemoryService(c)
    rec = MemoryRecord(id="fast-1", content="fast status memory", type=MemoryType.FACT, scope=MemoryScope.PROJECT)
    assert all(r.ok for r in svc.save(rec))
    import super_memory.health_cache as hc
    monkeypatch.setattr(hc, "load_config", lambda config_path=None: c)
    out = hc.self_heal_status_fast()
    assert out["ok"]
    assert out["mode"] == "fast"
    assert out["bounded"] is True
    cached = hc.get_cache("self_heal_status")
    assert cached and cached["cached"] is True


def test_deep_improve_async_returns_job_id(tmp_path: Path, monkeypatch):
    c = cfg(tmp_path)
    import super_memory.maintenance_jobs as mj
    monkeypatch.setattr(mj, "load_config", lambda config_path=None: c)
    out = mj.deep_improve_mcp_safe(dry_run=True, async_mode=True)
    assert out["ok"]
    assert out["mode"] == "async"
    assert out["job_id"].startswith("maint_")


def test_process_maintenance_job_saves_result(tmp_path: Path, monkeypatch):
    c = cfg(tmp_path)
    import super_memory.maintenance_jobs as mj
    monkeypatch.setattr(mj, "load_config", lambda config_path=None: c)
    monkeypatch.setattr(mj, "_run", lambda job_type, args, config_path=None: {"ok": True, "summary": "done", "heavy_details": [1, 2, 3]})
    job = mj.enqueue("deep_improve", {"dry_run": True})
    processed = mj.process_jobs(limit=1)
    assert processed["processed"] == 1
    st = mj.status(job["job_id"])
    assert st["status"] == "done"
    assert st["result"]["summary"] == "done"


def test_compact_response_excludes_heavy_details(tmp_path: Path, monkeypatch):
    c = cfg(tmp_path)
    import super_memory.bridge as bridge
    class FakeDeep:
        @staticmethod
        def deep_improve(dry_run=True, config_path=None):
            return {"ok": True, "summary": "compact ok", "audit_grade": "A", "qualify_grade": "A", "problems_found": 0, "applied": [], "improvement_proposals": [], "heavy_details": [1] * 1000}
    import super_memory.deep_auto as da
    monkeypatch.setattr(da, "deep_improve", FakeDeep.deep_improve)
    out = bridge.deep_improve(dry_run=True, config_path=None, compact=True, async_mode=False)
    assert out["compact"] is True
    assert "heavy_details" not in out
    assert out["summary"] == "compact ok"
