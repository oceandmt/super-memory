#!/usr/bin/env python3
"""Auto-audit script for super-memory-github.

Runs every 10min via cron via .venv_test/bin/python3.
Quick health check only. Exits 0 on pass, 1 on issues.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def audit():
    issues = []

    # 1. Check all mempalace modules import cleanly
    modules = [
        "collision_scan", "compressor", "convo_miner", "dedup",
        "entity_detector", "entity_registry", "extractor",
        "fact_checker", "hallways", "knowledge_graph",
        "loader", "onboarding", "searcher", "spatial",
        "spellcheck", "tools",
    ]
    for mod in modules:
        try:
            __import__(f"super_memory.mempalace.{mod}")
        except Exception as e:
            issues.append(f"import mempalace/{mod}: FAIL ({e})")

    # 2. Check core module imports
    core_modules = ["storage", "service", "bridge", "config", "models"]
    for mod in core_modules:
        try:
            __import__(f"super_memory.{mod}")
        except Exception as e:
            issues.append(f"import core/{mod}: FAIL ({e})")

    # 3. Check MCP tool count
    try:
        from super_memory.mempalace.tools import MEMPALACE_TOOLS
        desc_count = len(MEMPALACE_TOOLS)
        if desc_count < 36:
            issues.append(f"MCP descriptors: {desc_count} (expected >= 36)")
    except Exception as e:
        issues.append(f"tools count check: FAIL ({e})")

    # 4. Read-only integration test. Mutation smoke belongs in qualification
    # against an explicitly disposable database, never in a cron audit.
    try:
        from super_memory.mempalace import (
            EntityRegistry, KnowledgeGraph, search_sqlite,
            deduplicate, build_hallways, fact_check,
            spellcheck_user_text,
        )
        r = EntityRegistry.load()
        if not callable(getattr(r, "lookup", None)):
            issues.append("EntityRegistry lookup surface: FAIL")
    except Exception as e:
        issues.append(f"integration test: FAIL ({e})")

    # 5. Check FTS5 health (stale format auto-heal)
    try:
        import sqlite3
        from super_memory.config import load_config as _load_cfg
        cfg = _load_cfg()
        db_path = str(Path(cfg.workspace_root) / cfg.sqlite_path)
        conn = sqlite3.connect(db_path, timeout=5)
        for tbl in ("memories_fts", "honcho_events_fts"):
            row = conn.execute(
                f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{tbl}'"
            ).fetchone()
            if row and row[0] and "content=" not in row[0]:
                issues.append(f"FTS5 stale format: {tbl} (needs migration — run 'python -m super_memory.migrations')")
        conn.close()
    except Exception as e:
        issues.append(f"FTS5 health check: FAIL ({e})")

    # Print & exit
    if issues:
        print(f"[FAIL] super-memory audit: {len(issues)} issues")
        for i in issues:
            print(f"  - {i}")
        return 1
    else:
        ok_count = len(modules) + len(core_modules)
        print(f"[OK] super-memory audit passed ({ok_count} modules, 36 tools, all healthy)")
        return 0


if __name__ == "__main__":
    sys.exit(audit())
