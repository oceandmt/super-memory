from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import bridge
from .benchmark import benchmark_cross_agent
from .config import load_config
from .qualify import qualify_cross_agent
from .migrations import run_migrations
from .storage import SuperMemoryStore


def migration_status(config_path: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    run_migrations(cfg)
    store = SuperMemoryStore(cfg)
    expected_tables = [
        "memories",
        "honcho_events",
        "session_archives",
        "handoff_bundles",
        "cross_agent_claims",
        "cross_agent_conflicts",
        "palace_drawers",
        "graph_edges",
        "cognitive_synapses",
    ]
    with store.connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    existing = {str(r["name"]) for r in rows}
    missing = [t for t in expected_tables if t not in existing]
    return {"ok": not missing, "expected_tables": expected_tables, "missing_tables": missing, "sqlite_path": str(store.path)}


def doctor(config_path: str | Path | None = None, run_benchmark: bool = True) -> dict[str, Any]:
    """Run a complete operational diagnosis with actionable pass/warn/fail checks."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, details: Any = None, severity: str = "error") -> None:
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "details": details})

    tasks: list[tuple[str, Callable[[], dict[str, Any]], Callable[[dict[str, Any]], bool], str]] = [
        ("migration_status", lambda: migration_status(config_path), lambda r: bool(r.get("ok")), "error"),
        ("memory_slot_contract", lambda: bridge.memory_slot_contract(config_path=str(config_path) if config_path else None), lambda r: r.get("verdict", "pass") != "fail", "error"),
        ("mcp_contract_admin", lambda: bridge.mcp_contract(profile="admin"), lambda r: int(r.get("tool_count", 0)) >= 100, "error"),
        ("cross_layer_health", lambda: bridge.cross_layer_health(config_path=str(config_path) if config_path else None), lambda r: int(r.get("sqlite_only_ids", 0)) == 0 and int(r.get("content_drift_count", 0)) == 0, "error"),
        ("diagnostics", lambda: bridge.diagnostics(config_path=str(config_path) if config_path else None), lambda r: bool(r), "warn"),
        ("qualify_cross_agent", lambda: qualify_cross_agent(config_path), lambda r: bool(r.get("ok")), "error"),
    ]
    if run_benchmark:
        tasks.append(("benchmark_cross_agent", lambda: benchmark_cross_agent(config_path), lambda r: bool(r.get("ok")), "warn"))

    for name, fn, predicate, severity in tasks:
        try:
            result = fn()
            add(name, predicate(result), result, severity)
        except Exception as exc:  # pragma: no cover - diagnostic surface
            add(name, False, f"{type(exc).__name__}: {exc}", severity)

    failed_errors = [c for c in checks if not c["ok"] and c["severity"] == "error"]
    failed_warnings = [c for c in checks if not c["ok"] and c["severity"] == "warn"]
    verdict = "fail" if failed_errors else "warn" if failed_warnings else "pass"
    return {"ok": verdict == "pass", "verdict": verdict, "checks": checks}
