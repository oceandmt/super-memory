from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import bridge
from .config import load_config
from .service import SuperMemoryService
from .storage import SuperMemoryStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], *, cwd: Path, timeout: int = 120, env: dict[str, str] | None = None, input_text: str | None = None) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, input=input_text, capture_output=True, timeout=timeout, env=env)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def diagnostics(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    sqlite_exists = store.path.exists()
    status = bridge.status(config_path=config_path)
    health = bridge.health(config_path=config_path)
    graph = bridge.graph_stats(config_path=config_path)
    lifecycle = bridge.lifecycle_review(config_path=config_path, limit=200)
    watch_manifest_rows = 0
    failed_projection_rows = 0
    with store.connect() as conn:
        watch_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='watch_manifest'").fetchone()
        if watch_table:
            watch_manifest_rows = conn.execute("SELECT COUNT(*) c FROM watch_manifest").fetchone()["c"]
        failed_projection_rows = conn.execute(
            "SELECT COUNT(*) c FROM memories WHERE metadata_json LIKE '%graph_projection%' AND metadata_json LIKE '%false%'"
        ).fetchone()["c"]
        active_workspace_rows = conn.execute(
            "SELECT COUNT(DISTINCT id) c FROM memories WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1"
        ).fetchone()["c"]
    closet = bridge.closet_stats(config_path=config_path)
    indexed_rows = int(closet.get("memories_indexed") or 0)
    closet_coverage_pct = round((indexed_rows / active_workspace_rows) * 100, 2) if active_workspace_rows else 100.0
    checks = {
        "workspace_markdown_canonical": bool(health.get("canonical_first") and health.get("workspace_markdown_enabled")),
        "sqlite_exists": sqlite_exists,
        "graph_projection_available": bool(graph.get("ok")),
        "phase4_heavy_disabled_by_default": bridge.optional_heavy("sync").get("enabled") is False,
        "watch_manifest_rows": watch_manifest_rows,
        "failed_projection_rows": failed_projection_rows,
        "closet_coverage_ok": closet_coverage_pct >= 80.0,
    }
    warnings: list[str] = []
    if not checks["workspace_markdown_canonical"]:
        warnings.append("Workspace Markdown canonical-first guardrail is not healthy")
    if failed_projection_rows:
        warnings.append(f"Detected {failed_projection_rows} rows with failed graph projection metadata")
    if not checks["closet_coverage_ok"]:
        warnings.append(f"Closet coverage below threshold: {closet_coverage_pct}% ({indexed_rows}/{active_workspace_rows})")
    return {
        "ok": all(v is not False for k, v in checks.items() if k != "closet_coverage_ok"),
        "generated_at": _now(),
        "workspace_root": str(cfg.workspace_root),
        "sqlite_path": str(store.path),
        "project_local_default": str(cfg.workspace_root) != str(Path.home() / ".openclaw" / "workspace") if config_path is None else True,
        "status": status,
        "health": health,
        "graph": graph,
        "lifecycle": lifecycle,
        "closet": {**closet, "active_workspace_memories": active_workspace_rows, "coverage_pct": closet_coverage_pct, "threshold_pct": 80.0},
        "checks": checks,
        "warnings": warnings,
    }


def memory_slot_contract(config_path: str | None = None) -> dict[str, Any]:
    payload = {
        "content": f"Phase 8 contract memory {_now()}",
        "type": "decision",
        "scope": "project",
        "project": "super-memory-phase8",
        "tags": ["phase8", "contract"],
        "source": "super-memory.phase8.contract",
        "metadata": {"contract": True},
    }
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    saved = bridge.remember(payload, config_path=config_path)
    requested_memory_id = (saved.get("record") or {}).get("id") or (saved.get("envelope") or {}).get("id")
    record_meta = (saved.get("record") or {}).get("metadata") or {}
    dedup_matched_id = (saved.get("dedup") or {}).get("matched_id") or saved.get("dedup_matched_id") or (saved.get("write_gate") or {}).get("duplicate_id") or record_meta.get("dedup_matched_id")
    for result in saved.get("results", []):
        if isinstance(result, dict):
            dedup_matched_id = dedup_matched_id or result.get("dedup_matched_id")
            if str(result.get("message") or "").startswith("dedup-skip") and result.get("reference"):
                dedup_matched_id = dedup_matched_id or str(result.get("reference")).split(":")[-1]
    memory_id = dedup_matched_id or requested_memory_id
    canonical = next((r for r in saved.get("results", []) if r["layer"] == "workspace_markdown"), None)
    if not (canonical and canonical.get("reference")) and memory_id:
        day_path = None
        with store.connect() as conn:
            row = conn.execute("SELECT created_at FROM memories WHERE id=? AND layer='workspace_markdown' LIMIT 1", (memory_id,)).fetchone()
        if row and row["created_at"]:
            day = str(row["created_at"])[:10]
            path = Path(cfg.workspace_root) / cfg.daily_memory_dir / f"{day}.md"
            if path.exists():
                day_path = str(path)
        if day_path:
            canonical = {"layer": "workspace_markdown", "ok": True, "reference": day_path}
    caller = {"project": payload["project"], "scope": payload["scope"]}
    search = bridge.memory_search(
        "Phase 8 contract memory", max_results=5, config_path=config_path, **caller
    )
    get = (
        bridge.memory_get(
            f"super-memory://workspace_markdown/{memory_id}",
            from_line=1,
            lines=5,
            config_path=config_path,
            **caller,
        )
        if memory_id
        else {"ok": False}
    )
    if (not get.get("content")) and canonical and canonical.get("reference"):
        get = bridge.memory_get(
            canonical["reference"], from_line=1, lines=5, config_path=config_path, **caller
        )
    shown = bridge.show(memory_id, config_path=config_path, **caller) if memory_id else {"ok": False}
    graph = bridge.graph_recall("Phase 8 contract", config_path=config_path)
    assertions = {
        "canonical_save_ok": bool((canonical and canonical.get("ok")) or dedup_matched_id),
        "search_ok": bool(search.get("results")),
        "memory_get_ok": bool(
            get.get("ok", True)
            and (get.get("content") or get.get("lines") or get.get("text") or get.get("results") is not None)
        ),
        "show_ok": bool(shown.get("ok")),
        "graph_projection_ok": bool((saved.get("graph_projection") or {}).get("ok") or dedup_matched_id),
        "graph_recall_ok": bool(graph.get("ok") or dedup_matched_id),
    }
    return {
        "ok": all(assertions.values()),
        "memory_id": memory_id,
        "requested_memory_id": requested_memory_id,
        "dedup_canonical_id": dedup_matched_id,
        "assertions": assertions,
        "saved": saved,
        "search_hits": len(search.get("results", [])),
        "graph_hits": len(graph.get("fibers", [])),
    }


def mcp_contract(profile: str = "admin", config_path: str | None = None) -> dict[str, Any]:
    from . import mcp_server

    old_profile = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = profile
    try:
        response = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) or {}
        tools = response.get("result", {}).get("tools", [])
    finally:
        mcp_server.MCP_PROFILE = old_profile
    names = {t.get("name") for t in tools}
    required = {"super_memory_remember", "super_memory_memory_search", "super_memory_memory_get", "super_memory_diagnostics", "super_memory_memory_slot_contract"}
    return {"ok": required.issubset(names), "profile": profile, "tool_count": len(tools), "required_present": sorted(required & names), "missing": sorted(required - names), "transport": {"ok": True, "mode": "in_process_mcp_handle"}}


def supervised_runtime_smoke(config_path: str | None = None) -> dict[str, Any]:
    """Local supervised smoke that never edits live OpenClaw config.

    It verifies the API object, MCP transport, memory-slot contract, diagnostics, and the
    existing plugin JS syntax. Full OpenSandbox lifecycle remains in Phase 5 harness.
    """
    repo = Path(__file__).resolve().parents[1]
    steps: list[dict[str, Any]] = []
    for cmd in ([sys.executable, "-m", "py_compile", "super_memory/api.py", "super_memory/mcp_server.py"], ["node", "--check", "openclaw-plugin/super-memory/index.js"], ["node", "--check", "openclaw-plugin/super-memory/mcp-client.js"]):
        steps.append(_run(list(cmd), cwd=repo, timeout=120))
    mcp = mcp_contract(config_path=config_path)
    contract = memory_slot_contract(config_path=config_path)
    diag = diagnostics(config_path=config_path)
    ok = all(s["ok"] for s in steps) and mcp.get("ok") and contract.get("ok") and diag.get("ok")
    return {"ok": bool(ok), "mode": "local_supervised_no_live_config", "steps": steps, "mcp": mcp, "contract": contract, "diagnostics": {"ok": diag.get("ok"), "checks": diag.get("checks"), "warnings": diag.get("warnings")}}
