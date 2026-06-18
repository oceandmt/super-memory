from __future__ import annotations

from pathlib import Path

from super_memory.doctor import doctor, migration_status
from super_memory.entity_registry import collision_report, resolve_entity, upsert_entity
from super_memory.lifecycle_hooks import post_turn_capture, session_end_summary, session_start_context
from super_memory.retrieval_backends import ChromaBackend, get_retrieval_backend
from super_memory.telemetry import record_event, telemetry_history


def test_doctor_and_migration_status(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    status = migration_status()
    assert status["ok"]
    result = doctor(run_benchmark=False)
    assert result["verdict"] in {"pass", "warn"}
    assert {c["name"] for c in result["checks"]} >= {"migration_status", "qualify_cross_agent"}


def test_entity_registry_identity_resolution(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    entity = upsert_entity("agent", "lucas", ["Lucas", "lucas-discord"])
    assert entity["ok"]
    resolved = resolve_entity("Lucas", "agent")
    assert resolved["ok"]
    assert resolved["canonical_name"] == "lucas"
    assert collision_report()["ok"]


def test_lifecycle_hooks(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    captured = post_turn_capture("hello", "hi", "session-1", "lucas", "boss")
    assert captured["ok"]
    context = session_start_context("session-1", "lucas", "hello")
    assert context["ok"]
    summary = session_end_summary("session-1")
    assert summary["ok"]


def test_persistent_telemetry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    assert record_event("doctor.run", 1, {"verdict": "pass"})["ok"]
    history = telemetry_history("doctor.run")
    assert history["ok"]
    assert history["events"]


def test_chroma_backend_skeleton_or_clear_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    sqlite_backend = get_retrieval_backend("sqlite_exact", __import__("super_memory.config", fromlist=["load_config"]).load_config())
    assert sqlite_backend.name == "sqlite_exact"
    try:
        backend = get_retrieval_backend("chroma", __import__("super_memory.config", fromlist=["load_config"]).load_config())
        assert backend.name == "chroma"
    except RuntimeError as exc:
        assert "chromadb is not installed" in str(exc)
