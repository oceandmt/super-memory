from datetime import datetime, timedelta, timezone
from pathlib import Path

from super_memory.models import SuperMemoryConfig


def _cfg(tmp_path: Path) -> SuperMemoryConfig:
    return SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/ops.sqlite3")


def test_grade_a_requires_integration_and_no_errors():
    from super_memory.auto_deep import DeepQualifyResult
    base = dict(smoke_tests={"s": True}, edge_cases={"e": True})
    assert DeepQualifyResult(**base, integration_ok=False).grade == "F"
    assert DeepQualifyResult(**base, integration_ok=True, errors=["boom"]).grade == "F"
    assert DeepQualifyResult(**base, integration_ok=True).grade == "A"


def test_expired_job_lease_is_recovered(tmp_path, monkeypatch):
    import super_memory.maintenance_jobs as jobs
    from super_memory.storage import SuperMemoryStore

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(jobs, "load_config", lambda config_path=None: cfg)
    monkeypatch.setattr(jobs, "_run", lambda *args, **kwargs: {"ok": True})
    job = jobs.enqueue("deep_improve")
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with SuperMemoryStore(cfg).connect() as conn:
        conn.execute(
            "UPDATE maintenance_jobs SET status='running', lease_owner='dead-worker', lease_expires_at=? WHERE id=?",
            (expired, job["job_id"]),
        )
    assert jobs.process_jobs(limit=1)["processed"] == 1
    assert jobs.status(job["job_id"])["status"] == "done"


def test_tests_do_not_embed_live_database_paths():
    root = Path(__file__).resolve().parent
    forbidden = "/home/" + "oceandmt/.openclaw/workspace/data/"
    offenders = [str(path) for path in root.glob("test_*.py") if forbidden in path.read_text()]
    assert offenders == []
