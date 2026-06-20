from pathlib import Path
import os

from super_memory import bridge
from super_memory.models import MemoryRecord, MemoryScope, MemoryType
from super_memory.service import SuperMemoryService
from super_memory.config import load_config


def _with_workspace(tmp_path: Path):
    old = os.environ.get("SUPER_MEMORY_WORKSPACE_ROOT")
    os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = str(tmp_path)
    return old


def _restore(old: str | None):
    if old is None:
        os.environ.pop("SUPER_MEMORY_WORKSPACE_ROOT", None)
    else:
        os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = old


def test_embedding_doctor_and_auto_select(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        doctor = bridge.embedding_doctor()
        assert doctor["ok"] is True
        assert doctor["fts_available"] is True
        selected = bridge.embedding_auto_select()
        assert selected["ok"] is True
        assert selected["selected"] in {"sqlite_fts", "sqlite_vec"}
    finally:
        _restore(old)


def test_short_term_audit_and_repair_promotes_event(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        svc = SuperMemoryService(load_config())
        rec = MemoryRecord(
            content="triển khai fix memory-core promotion workflow " + ("details " * 160),
            type=MemoryType.EVENT,
            scope=MemoryScope.SESSION,
            agent_id="lucas",
            session_id="s1",
            source="test.short-term",
        )
        svc.save(rec)
        audit = bridge.short_term_audit(limit=50)
        assert audit["candidate_count"] >= 1
        dry = bridge.short_term_repair(limit=50, dry_run=True)
        assert dry["count"] >= 1
        applied = bridge.short_term_repair(limit=50, dry_run=False)
        assert applied["count"] >= 1
    finally:
        _restore(old)


def test_dreaming_run_creates_artifact_and_memory(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        svc = SuperMemoryService(load_config())
        svc.save(MemoryRecord(content="dream event " * 120, type=MemoryType.EVENT, scope=MemoryScope.SESSION, session_id="dream", source="test.dream"))
        audit = bridge.dreaming_audit()
        assert audit["ok"] is True
        dry = bridge.dreaming_run(dry_run=True)
        assert dry["ok"] is True
        applied = bridge.dreaming_run(dry_run=False)
        assert applied["ok"] is True
        assert Path(applied["artifact_path"]).exists()
    finally:
        _restore(old)
