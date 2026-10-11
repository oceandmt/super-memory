#!/usr/bin/env python
"""P0 drain: process pending embed jobs into BOTH the legacy memory_vectors
cache and the authoritative data/vectors.sqlite3 store.

Bounded + resumable: processes in chunks until no pending jobs remain or a
wall-clock budget is hit. Safe to re-run. Writes only vectors/job status.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from super_memory.write_contract.worker import process_memory_jobs
from super_memory.config import load_config
from super_memory.storage import SuperMemoryStore

CHUNK = 25
MAX_SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3300


def pending(cfg) -> int:
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        return conn.execute(
            "SELECT count(*) FROM memory_jobs WHERE status IN ('pending','retry') AND job_type='embed'"
        ).fetchone()[0]


def main() -> None:
    cfg = load_config(None)
    started = time.time()
    total_proc = total_rep = total_auth = total_err = 0
    rounds = 0
    print(f"[{datetime.now(timezone.utc).isoformat()}] start pending={pending(cfg)}", flush=True)
    while time.time() - started < MAX_SECONDS:
        rounds += 1
        r = process_memory_jobs(limit=CHUNK)
        total_proc += r.get("processed", 0)
        total_rep += r.get("repaired", 0)
        total_auth += r.get("authoritative_repaired", 0)
        total_err += r.get("errors", 0)
        left = pending(cfg)
        print(
            f"[{datetime.now(timezone.utc).isoformat()}] round={rounds} "
            f"chunk={r.get('processed')}/{r.get('repaired')} auth={r.get('authoritative_repaired')} "
            f"err={r.get('errors')} left={left}",
            flush=True,
        )
        if left == 0:
            break
        if r.get("processed", 0) == 0:
            # nothing claimed (all lease-locked or none due) -> small backoff
            time.sleep(2)
    print(json.dumps({
        "done": True,
        "total_processed": total_proc,
        "legacy_repaired": total_rep,
        "authoritative_repaired": total_auth,
        "errors": total_err,
        "pending_left": pending(cfg),
        "elapsed_s": round(time.time() - started, 1),
    }), flush=True)


if __name__ == "__main__":
    main()
