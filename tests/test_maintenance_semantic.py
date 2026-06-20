from __future__ import annotations

from pathlib import Path

import yaml

from super_memory import bridge
from super_memory.config import load_config
from super_memory.memory_core import short_term_audit
from super_memory.models import MemoryRecord, MemoryScope, MemoryType
from super_memory.service import SuperMemoryService


def _cfg(tmp_path: Path) -> str:
    cfg = {
        "workspace_root": str(tmp_path),
        "sqlite_path": "data/super-memory.sqlite3",
        "daily_memory_dir": "memory",
        "long_term_file": "MEMORY.md",
        "registers_dir": "memory/registers",
        "require_canonical_first": True,
        "vector_enabled": True,
        "embedding_provider": "ollama",
        "embedding_dimension": 768,
    }
    path = tmp_path / "super-memory.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(path)


def test_semantic_doctor_bridge_honors_vector_enabled(tmp_path: Path):
    config = _cfg(tmp_path)
    result = bridge.semantic_doctor(config_path=config)
    assert result["workspace_root"] == str(tmp_path)
    assert any(c["name"] == "vector_enabled" and c["ok"] for c in result["checks"])


def test_short_term_audit_policy_filters_low_signal_noise(tmp_path: Path):
    config = _cfg(tmp_path)
    svc = SuperMemoryService(load_config(config))
    for i in range(4):
        svc.save(MemoryRecord(content="test", type=MemoryType.EVENT, scope=MemoryScope.SESSION, session_id="test-hook", metadata={"content_hash": "noise"}))
    for i in range(4):
        svc.save(MemoryRecord(content="triển khai semantic gateway qualify fix " + ("x" * 1200), type=MemoryType.EVENT, scope=MemoryScope.SESSION, session_id="real-session", metadata={"content_hash": "signal"}))
    result = short_term_audit(config_path=config)
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["session_id"] == "real-session"
    assert result["candidates"][0]["promotion_score"] >= 1.0


def test_maintenance_dry_run_shape(tmp_path: Path):
    config = _cfg(tmp_path)
    result = bridge.maintenance_run(dry_run=True, limit=20, config_path=config)
    assert result["dry_run"] is True
    assert "embedding_doctor" in result["steps"]
    assert "lifecycle_quality_cleanup" in result["steps"]
    assert "short_term_repair" in result["steps"]
    assert "dreaming_run" in result["steps"]
