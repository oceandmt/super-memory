from __future__ import annotations

from pathlib import Path

from super_memory.benchmark import benchmark_cross_agent
from super_memory.config import load_config
from super_memory.qualify import qualify_cross_agent
from super_memory.retrieval_backends import get_retrieval_backend
from super_memory.setup_wizard import build_setup_config, write_setup_config
from super_memory.telemetry import TelemetryRegistry


def test_setup_wizard_writes_cross_agent_config(tmp_path: Path):
    cfg = build_setup_config(tmp_path, agents=["lucas", "alex"])
    out = write_setup_config(cfg, tmp_path / "super-memory.yaml")
    text = out.read_text()
    assert "cross_agent_memory" in text
    assert "cross_session_memory" in text
    assert "mcp_profile: admin" in text


def test_sqlite_exact_backend_conformance(tmp_path: Path, monkeypatch):
    from super_memory import bridge

    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    config = load_config()
    bridge.remember(
        {
            "content": "backend conformance lucas exact recall",
            "agent_id": "lucas",
            "session_id": "backend-session",
            "scope": "shared",
            "tags": ["backend-conformance"],
        }
    )
    backend = get_retrieval_backend("sqlite_exact", config)
    hits = backend.search("conformance", agent_id="lucas", session_id="backend-session", limit=5)
    assert hits
    assert hits[0].backend == "sqlite_exact"
    assert hits[0].memory.agent_id == "lucas"


def test_telemetry_prometheus_text():
    registry = TelemetryRegistry()
    registry.inc("cross_agent.qualify")
    registry.observe_ms("cross_agent.qualify.latency_ms", 12.5)
    text = registry.prometheus_text()
    assert "super_memory_cross_agent_qualify" in text
    assert "latency_ms_avg" in text


def test_qualify_cross_agent_harness(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    result = qualify_cross_agent()
    assert result["ok"], result
    names = {c["name"] for c in result["checks"]}
    assert "cross_agent_recall" in names
    assert "session_timeline" in names
    assert "handoff_lifecycle" in names


def test_cross_agent_benchmark(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    qualify_cross_agent()
    result = benchmark_cross_agent(limit=5)
    assert result["ok"], result
    assert result["results"]
    assert result["avg_latency_ms"] >= 0
