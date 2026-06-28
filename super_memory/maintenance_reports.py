from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .config import load_config
from .self_heal import self_heal_status, self_heal_embeddings
from .write_contract import process_memory_jobs, reconcile_memory_integrity
from .deep_auto import deep_audit, deep_qualify, deep_debug, deep_improve
from .projections.manifest import audit_projection_drift, repair_projection_drift
from .long_memory import review_long_memories
from .recall_benchmark import run_recall_benchmark

PROFILES = {
    "daily": {
        "steps": ["write_contract_reconcile", "write_contract_jobs", "self_heal", "projection_drift", "deep_qualify"],
        "description": "Lightweight daily health: heal vectors, fix drifts, quality check",
    },
    "weekly": {
        "steps": ["write_contract_reconcile", "write_contract_jobs", "self_heal", "projection_drift", "long_memory_review", "graph_cleanup", "deep_audit", "deep_qualify", "deep_debug", "recall_benchmark"],
        "description": "Full weekly maintenance: audit + qualify + debug + benchmark",
    },
    "release": {
        "steps": ["write_contract_reconcile", "write_contract_jobs", "self_heal", "projection_drift", "long_memory_review", "graph_cleanup", "deep_audit", "deep_qualify", "deep_debug", "deep_improve", "recall_benchmark", "release_gate"],
        "description": "Pre-release: full cycle + improve + benchmark gate",
    },
}


def _run_profile_step(name: str, config_path: str | None = None, dry_run: bool = False) -> dict:
    if name == "write_contract_reconcile":
        return {"action": reconcile_memory_integrity(limit=500, config_path=config_path)}
    if name == "write_contract_jobs":
        if dry_run:
            return {"action": "dry_run_skip"}
        return {"action": process_memory_jobs(limit=200, config_path=config_path)}
    if name == "graph_cleanup":
        if dry_run:
            return {"action": "dry_run_skip"}
        from . import graph
        return {"action": graph.cleanup_orphans(config_path=config_path)}
    if name == "self_heal":
        before = self_heal_status(config_path)
        out = {"before": before}
        if not dry_run and before.get("missing_vectors", 0) > 0:
            out["action"] = self_heal_embeddings(batch_size=100, config_path=config_path)
        out["after"] = self_heal_status(config_path)
        return out
    if name == "projection_drift":
        return {"audit": audit_projection_drift(config_path=config_path), "repair": repair_projection_drift(config_path, dry_run=dry_run)}
    if name == "long_memory_review":
        return {"action": review_long_memories(config_path=config_path)}
    if name == "deep_audit":
        return {"action": deep_audit(config_path)}
    if name == "deep_qualify":
        return {"action": deep_qualify(config_path)}
    if name == "deep_debug":
        return {"action": deep_debug(config_path)}
    if name == "deep_improve":
        return {"action": deep_improve(dry_run=dry_run, config_path=config_path)}
    if name == "recall_benchmark":
        return {"action": run_recall_benchmark(config_path)}
    if name == "release_gate":
        from .recall_benchmark import release_gate
        return {"action": release_gate(config_path=config_path, limit=100)}
    return {"error": f"unknown step: {name}"}


def run_scheduled_maintenance(config_path: str | None = None, dry_run: bool = False, profile: str = "daily") -> dict:
    cfg = load_config(config_path)
    ts = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    profile_def = PROFILES.get(profile, PROFILES["daily"])
    steps = profile_def["steps"]
    out = {
        "ok": True,
        "timestamp": ts,
        "profile": profile,
        "profile_description": profile_def["description"],
        "dry_run": dry_run,
        "steps": {},
    }
    for step in steps:
        out["steps"][step] = _run_profile_step(step, config_path=config_path, dry_run=dry_run)
    rdir = Path(cfg.workspace_root) / 'projects' / 'super-memory-github' / 'reports' / 'maintenance'
    rdir.mkdir(parents=True, exist_ok=True)
    fname = f'{ts}_{profile}'
    j = rdir / f'{fname}.json'
    m = rdir / f'{fname}.md'
    j.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    m.write_text(f'# Super Memory Maintenance Report ({profile})\n\n```json\n' + json.dumps(out, ensure_ascii=False, indent=2) + '\n```\n', encoding='utf-8')
    out['report_json'] = str(j)
    out['report_md'] = str(m)
    return out
