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
        "compressor", "dedup", "entity_detector", "entity_registry",
        "extractor", "fact_checker", "hallways", "knowledge_graph",
        "loader", "searcher", "spatial", "spellcheck", "tools",
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
        if desc_count < 31:
            issues.append(f"MCP descriptors: {desc_count} (expected >= 31)")
    except Exception as e:
        issues.append(f"tools count check: FAIL ({e})")

    # 4. Quick integration test
    try:
        from super_memory.mempalace import (
            EntityRegistry, KnowledgeGraph, search_sqlite,
            deduplicate, build_hallways, fact_check,
            spellcheck_user_text,
        )
        # Entity Registry smoke test
        r = EntityRegistry.load()
        r.add("_audit_test_", kind="test", source="audit")
        result = r.lookup("_audit_test_")
        r.remove("_audit_test_")
        if result["type"] != "test":
            issues.append("EntityRegistry lookup: FAIL")
    except Exception as e:
        issues.append(f"integration test: FAIL ({e})")

    # Print & exit
    if issues:
        print(f"[FAIL] super-memory audit: {len(issues)} issues")
        for i in issues:
            print(f"  - {i}")
        return 1
    else:
        ok_count = len(modules) + len(core_modules)
        print(f"[OK] super-memory audit passed ({ok_count} modules, 31 tools, all healthy)")
        return 0


if __name__ == "__main__":
    sys.exit(audit())
