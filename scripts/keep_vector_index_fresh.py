#!/usr/bin/env python
"""Keep the vector index fresh so the operational SLO `vector_index_age_seconds`
does not flap while the system is idle.

Steps (all bounded, non-destructive; writes only vectors/job status):
  1) drain pending embed jobs (memory_jobs job_type='embed')
  2) run semantic_index() — refreshes data/vectors.sqlite3 and bumps its
     freshness marker (mtime) on a successful pass

Prints ONE compact JSON line. Safe to re-run. Never VACUUMs, never hard-deletes.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from super_memory.config import load_config
from super_memory.storage import SuperMemoryStore

BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 120


def _pending(cfg) -> int:
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        return conn.execute(
            "SELECT count(*) FROM memory_jobs WHERE status IN ('pending','retry') AND job_type='embed'"
        ).fetchone()[0]


def main() -> None:
    started = time.time()
    out: dict = {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}
    cfg = load_config(None)

    # 1) bounded embed drain
    drained = errs = 0
    try:
        from super_memory.write_contract.worker import process_memory_jobs

        while time.time() - started < BUDGET * 0.6:
            r = process_memory_jobs(limit=25)
            drained += r.get("processed", 0)
            errs += r.get("errors", 0)
            if _pending(cfg) == 0 or r.get("processed", 0) == 0:
                break
    except Exception as exc:  # pragma: no cover - runtime dependent
        out["ok"] = False
        out["drain_error"] = repr(exc)[:200]
    out["drained"] = drained
    out["drain_errors"] = errs
    out["pending_left"] = _pending(cfg)

    # 2) backfill closets for any new canonical memories (keeps coverage at 100%)
    try:
        from super_memory.projections.drift_repair import rebuild_missing_closets

        rc = rebuild_missing_closets(limit=200, config_path=None)
        out["closets_built"] = rc.get("built")
        out["closets_errors"] = rc.get("errors")
    except Exception as exc:  # pragma: no cover - runtime dependent
        out["ok"] = False
        out["closet_error"] = repr(exc)[:200]

    # 3) refresh + freshness marker
    try:
        from super_memory.semantic import semantic_index

        r = semantic_index(None)
        out["index_ok"] = r.get("ok")
        out["indexed"] = r.get("indexed")
        out["vector_count"] = r.get("vector_count")
        out["failed"] = len(r.get("failed", []) or [])
    except Exception as exc:  # pragma: no cover - runtime dependent
        out["ok"] = False
        out["index_error"] = repr(exc)[:200]

    out["elapsed_s"] = round(time.time() - started, 1)
    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
