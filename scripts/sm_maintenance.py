#!/usr/bin/env python
"""Deterministic Super Memory maintenance runner.

Runs the bounded health/parity/write-contract/consolidate pipeline IN-PROCESS
(no LLM, no giant context) and prints ONE compact JSON report. Designed to be
invoked by cron via a thin agentTurn so weekly maintenance can no longer time
out on model/context bloat.

Phases:
  hygiene        report-only (health, parity audit, vector coverage, dry-run consolidate)
  cleanup        hygiene + bounded repairs (parity repair, orphan cleanup, self-heal)
  embed-drain    drain pending embed jobs (bounded)

Safety:
  * dry-run by default; bounded real mutations only with --apply
  * hard per-phase deadline so a slow host can never hang the cron
  * never hard-deletes; never VACUUMs
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from super_memory import bridge

START = time.time()


def _j(v):
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        return str(v)


def _short(d, keys):
    if not isinstance(d, dict):
        return {"raw": str(d)[:200]}
    return {k: d.get(k) for k in keys if k in d}


def _step(out: dict, name: str, fn, deadline: float, keys: list[str]):
    """Run one bounded step; skip if past deadline; never raise.

    Retries briefly on SQLite 'database is locked' so a concurrent embed drain
    cannot make the report flaky.
    """
    if time.time() > deadline:
        out[name] = {"skipped": "budget"}
        return None
    s = time.time()
    last_err = None
    for attempt in range(3):
        try:
            r = fn()
            out[name] = _short(r, keys)
            return r
        except Exception as e:  # noqa: BLE001
            last_err = e
            if "locked" in str(e).lower() and attempt < 2 and time.time() < deadline:
                time.sleep(2)
                continue
            break
    out[name] = {"error": f"{type(last_err).__name__}: {last_err}"[:200]}
    out.setdefault("_timing", {})[name] = round(time.time() - s, 2)
    return None


def run_hygiene(deadline: float) -> dict:
    out: dict = {"phase": "hygiene", "ts": datetime.now(timezone.utc).isoformat()}
    _step(out, "health", bridge.health, deadline, ["ready", "degraded", "warnings", "blocking"])
    _step(out, "stats", bridge.stats, deadline, ["total_memories", "layers", "graph_edges"])
    _step(out, "vector_coverage", bridge.vector_coverage, deadline, ["ok", "coverage", "vectorized", "eligible"])
    _step(out, "graph", bridge.graph_stats, deadline, ["neurons", "synapses", "fibers"])
    _step(out, "parity_audit", lambda: bridge.layer_parity_audit(limit=500), deadline,
          ["ok", "missing_by_layer", "repairable"])
    _step(out, "consolidate_dry", lambda: bridge.consolidate(strategy="all", dry_run=True), deadline,
          ["ok", "duplicate_clusters", "promotion_candidates", "contradictions", "checked"])
    return out


def run_cleanup(deadline: float, apply: bool = False) -> dict:
    out = run_hygiene(deadline)
    out["phase"] = "cleanup"

    # 1) layer parity repair — only when the audit shows drift
    missing = (out.get("parity_audit") or {}).get("missing_by_layer") if isinstance(out.get("parity_audit"), dict) else None
    drift = bool(missing) and any(v for v in missing.values())
    if drift:
        _step(out, "parity_repair_dry", lambda: bridge.layer_parity_repair(limit=500, dry_run=True), deadline,
              ["ok", "would_backfill", "repaired", "missing_by_layer"])
        if apply:
            _step(out, "parity_repair", lambda: bridge.layer_parity_repair(limit=500, dry_run=False), deadline,
                  ["ok", "repaired", "missing_by_layer"])
    else:
        out["parity_repair"] = {"ok": True, "note": "no drift"}

    # 2) write-contract: reconcile then process a bounded batch (embeds both stores)
    _step(out, "wc_reconcile", lambda: bridge.write_contract_reconcile(limit=200), deadline,
          ["ok", "created_embed_jobs"])
    _step(out, "wc_process", lambda: bridge.write_contract_process_jobs(limit=50), deadline,
          ["ok", "processed", "repaired", "authoritative_repaired", "errors", "provider"])

    # 3) self-heal embeddings (bounded)
    _step(out, "self_heal", lambda: bridge.self_heal_embeddings(batch_size=50), deadline,
          ["ok", "detected", "repaired", "errors", "provider"])

    # 4) closet snapshot
    _step(out, "closet", lambda: (bridge.diagnostics() or {}).get("closet", {}), deadline,
          ["coverage_pct", "drawer_count", "memories_indexed"])

    # 5) orphan cleanup + real consolidation — apply-only
    if apply:
        _step(out, "orphan_cleanup", bridge.graph_cleanup_orphans, deadline, ["ok", "removed", "neurons"])
        _step(out, "consolidate_apply", lambda: bridge.consolidate(strategy="all", dry_run=False), deadline,
              ["ok", "merged_clusters", "links_created", "promotions"])
    return out


def run_embed_drain(budget_s: int) -> dict:
    from super_memory.write_contract.worker import process_memory_jobs
    started = time.time()
    proc = rep = auth = err = 0
    rounds = 0
    while time.time() - started < budget_s:
        rounds += 1
        r = process_memory_jobs(limit=25)
        proc += r.get("processed", 0); rep += r.get("repaired", 0)
        auth += r.get("authoritative_repaired", 0); err += r.get("errors", 0)
        if r.get("processed", 0) == 0:
            break
    return {"phase": "embed-drain", "rounds": rounds, "processed": proc, "repaired": rep,
            "authoritative_repaired": auth, "errors": err, "elapsed_s": round(time.time() - started, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["hygiene", "cleanup", "embed-drain"])
    ap.add_argument("--apply", action="store_true", help="allow bounded real mutations")
    ap.add_argument("--budget", type=int, default=600, help="total wall-clock budget (s)")
    ap.add_argument("--out", default=None, help="also write the JSON report to this path")
    args = ap.parse_args()
    deadline = START + max(30, args.budget)
    if args.phase == "hygiene":
        res = run_hygiene(deadline)
    elif args.phase == "cleanup":
        res = run_cleanup(deadline, apply=args.apply)
    else:
        res = run_embed_drain(budget_s=args.budget)
    res["elapsed_s"] = round(time.time() - START, 1)
    text = _j(res)
    if args.out:
        try:
            from pathlib import Path
            p = Path(args.out)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(_j({"warn": f"could not write --out: {e}"}))
    print(text)


if __name__ == "__main__":
    main()
