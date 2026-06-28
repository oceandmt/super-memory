from pathlib import Path
from super_memory.models import SuperMemoryConfig
from super_memory.self_improvement.orchestrator import run_self_improvement_cycle


def test_self_improvement_orchestrator_dry_run_smoke(tmp_path: Path, monkeypatch):
    c = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    import super_memory.self_improvement.orchestrator as orch
    monkeypatch.setattr(orch, "load_config", lambda config_path=None: c)
    r = run_self_improvement_cycle(dry_run=True, limit=10, remember_lesson=False)
    assert r["ok"]
    assert r["dry_run"] is True
    assert "post_audit" in r
    assert Path(r["report_path"]).exists()
