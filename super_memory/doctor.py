from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from . import bridge
from .benchmark import benchmark_cross_agent
from .config import load_config
from .migrations import run_migrations
from .qualify import qualify_cross_agent

EXPECTED_TABLES = [
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
DESTRUCTIVE_TEST_OPT_IN = "SUPER_MEMORY_ALLOW_DESTRUCTIVE_TESTS"


def _database_path(config_path: str | Path | None = None) -> tuple[Any, Path]:
    cfg = load_config(config_path)
    raw = Path(cfg.sqlite_path).expanduser()
    path = raw if raw.is_absolute() else Path(cfg.workspace_root).expanduser() / raw
    return cfg, path.resolve(strict=False)


def test_isolation_status(
    config_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Check test paths without opening the configured database.

    Known production roots are refused unless an operator explicitly sets
    SUPER_MEMORY_ALLOW_DESTRUCTIVE_TESTS. Additional roots can be supplied as
    an os.pathsep-separated SUPER_MEMORY_PRODUCTION_WORKSPACE_ROOTS value.
    """
    env = os.environ if environ is None else environ
    cfg, db_path = _database_path(config_path)
    workspace = Path(cfg.workspace_root).expanduser().resolve(strict=False)
    configured_roots = [
        item.strip()
        for item in env.get("SUPER_MEMORY_PRODUCTION_WORKSPACE_ROOTS", "").split(os.pathsep)
        if item.strip()
    ]
    production_roots = {
        (Path.home() / ".openclaw" / "workspace").resolve(strict=False),
        *(Path(item).expanduser().resolve(strict=False) for item in configured_roots),
    }

    def inside(path: Path, root: Path) -> bool:
        return path == root or root in path.parents

    matched = sorted(
        str(root)
        for root in production_roots
        if inside(workspace, root) or inside(db_path, root)
    )
    opt_in = str(env.get(DESTRUCTIVE_TEST_OPT_IN, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "i-understand",
        "i_understand",
    }
    production_target = bool(matched)
    ok = not production_target or opt_in
    return {
        "ok": ok,
        "production_target": production_target,
        "destructive_test_opt_in": opt_in,
        "workspace_root": str(workspace),
        "sqlite_path": str(db_path),
        "matched_production_roots": matched,
        "required_opt_in": DESTRUCTIVE_TEST_OPT_IN,
        "reason": (
            "isolated"
            if not production_target
            else "explicit_opt_in"
            if opt_in
            else "production_target_refused"
        ),
    }


def require_test_isolation(
    config_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Raise before a test runner can touch a production workspace or DB."""
    status = test_isolation_status(config_path, environ=environ)
    if not status["ok"]:
        raise RuntimeError(
            "refusing destructive tests against production target "
            f"{status['sqlite_path']}; set {DESTRUCTIVE_TEST_OPT_IN}=1 only for an intentional run"
        )
    return status


def _table_names(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        return {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def migration_status(
    config_path: str | Path | None = None,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Inspect migrations without mutating the configured DB by default.

    Dry-run applies migrations to a disposable SQLite copy. ``dry_run=False``
    retains the historical explicit in-place behavior.
    """
    cfg, source_path = _database_path(config_path)
    source_exists = source_path.is_file()
    current_tables = _table_names(source_path)
    current_missing = [table for table in EXPECTED_TABLES if table not in current_tables]

    if not dry_run:
        migration = run_migrations(cfg)
        final_tables = _table_names(source_path)
        missing = [table for table in EXPECTED_TABLES if table not in final_tables]
        return {
            "ok": bool(migration.get("ok")) and not missing,
            "dry_run": False,
            "source_exists": source_exists,
            "expected_tables": EXPECTED_TABLES,
            "current_missing_tables": current_missing,
            "missing_tables": missing,
            "sqlite_path": str(source_path),
            "migration": migration,
        }

    source_stat = source_path.stat() if source_exists else None
    with tempfile.TemporaryDirectory(prefix="super-memory-migration-dry-run-") as temp_dir:
        temp_root = Path(temp_dir)
        clone = temp_root / "migration-copy.sqlite3"
        if source_exists:
            # SQLite backup gives a consistent copy even when the source uses WAL.
            source_uri = f"file:{source_path.as_posix()}?mode=ro"
            with sqlite3.connect(source_uri, uri=True) as source, sqlite3.connect(clone) as target:
                source.backup(target)
        clone_cfg = cfg.model_copy(update={"workspace_root": temp_root, "sqlite_path": clone.name})
        migration = run_migrations(clone_cfg)
        post_tables = _table_names(clone)
        missing = [table for table in EXPECTED_TABLES if table not in post_tables]

    unchanged = True
    if source_stat is not None:
        after = source_path.stat()
        unchanged = (source_stat.st_size, source_stat.st_mtime_ns) == (
            after.st_size,
            after.st_mtime_ns,
        )
    return {
        "ok": bool(migration.get("ok")) and not missing and unchanged,
        "dry_run": True,
        "copy_based": True,
        "source_exists": source_exists,
        "source_unchanged": unchanged,
        "expected_tables": EXPECTED_TABLES,
        "current_missing_tables": current_missing,
        "missing_tables": missing,
        "sqlite_path": str(source_path),
        "migration": {**migration, "db_path": "<disposable-copy>"},
    }


def doctor(config_path: str | Path | None = None, run_benchmark: bool = True) -> dict[str, Any]:
    """Run a complete operational diagnosis with actionable pass/warn/fail checks."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, details: Any = None, severity: str = "error") -> None:
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "details": details})

    tasks: list[
        tuple[str, Callable[[], dict[str, Any]], Callable[[dict[str, Any]], bool], str]
    ] = [
        ("migration_status", lambda: migration_status(config_path), lambda r: bool(r.get("ok")), "error"),
        (
            "memory_slot_contract",
            lambda: bridge.memory_slot_contract(config_path=str(config_path) if config_path else None),
            lambda r: r.get("verdict", "pass") != "fail",
            "error",
        ),
        (
            "mcp_contract_admin",
            lambda: bridge.mcp_contract(profile="admin"),
            lambda r: int(r.get("tool_count", 0)) >= 100,
            "error",
        ),
        (
            "cross_layer_health",
            lambda: bridge.cross_layer_health(config_path=str(config_path) if config_path else None),
            lambda r: int(r.get("sqlite_only_ids", 0)) == 0
            and int(r.get("content_drift_count", 0)) == 0,
            "error",
        ),
        (
            "diagnostics",
            lambda: bridge.diagnostics(config_path=str(config_path) if config_path else None),
            lambda r: bool(r),
            "warn",
        ),
        (
            "qualify_cross_agent",
            lambda: qualify_cross_agent(config_path),
            lambda r: bool(r.get("ok")),
            # Qualification is an optional subsystem diagnostic. Preserve its
            # evidence, but do not make unrelated release/migration health fail.
            "warn",
        ),
    ]
    if run_benchmark:
        tasks.append(
            (
                "benchmark_cross_agent",
                lambda: benchmark_cross_agent(config_path),
                lambda r: bool(r.get("ok")),
                "warn",
            )
        )

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
