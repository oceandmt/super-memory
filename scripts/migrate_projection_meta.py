#!/usr/bin/env python
"""Migrate/backfill projection_meta registrations for active canonical memories.

Context: `projection_meta` is the drift-tracking registry for derived
projections. Pre-P0 canonical memories were never registered, so the drift
audit reports "N active memories without projection_meta registration".

This migration registers ONE canonical projection row per active
workspace_markdown memory:
    table_name      = 'canonical'
    memory_id       = <memory id>
    projection_key  = <memory id>
    content_hash    = <memories.content_hash>
    last_verified   = now

Properties:
  * idempotent   — INSERT OR REPLACE keyed by (table_name, projection_key)
  * non-destructive — only INSERTs into projection_meta (no deletes/updates
                      to any other table)
  * reversible   — DELETE FROM projection_meta WHERE table_name='canonical'
  * bounded      — batched commits

Usage:
    python migrate_projection_meta.py --dry-run   (default)
    python migrate_projection_meta.py --apply
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from super_memory.config import load_config
from super_memory.storage import SuperMemoryStore

TABLE = "canonical"
BATCH = 500


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="apply the migration (default: dry-run)")
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    store = SuperMemoryStore(cfg)
    now = datetime.now(timezone.utc).isoformat()
    started = time.time()

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT m.id AS id, m.content_hash AS ch FROM memories m "
            "WHERE m.layer='workspace_markdown' "
            "AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0)=0 "
            "AND NOT EXISTS (SELECT 1 FROM projection_meta pm WHERE pm.memory_id=m.id) "
            "ORDER BY m.created_at DESC"
        ).fetchall()

        total_missing = len(rows)
        already = conn.execute(
            "SELECT COUNT(DISTINCT memory_id) FROM projection_meta WHERE memory_id IS NOT NULL"
        ).fetchone()[0]

        if not args.apply:
            print(json.dumps({
                "mode": "dry-run",
                "missing_registrations": total_missing,
                "already_registered": already,
                "table_name": TABLE,
                "would_insert_rows": total_missing,
                "sample": [{"memory_id": r["id"], "content_hash": (r["ch"] or "")[:12]} for r in rows[:5]],
                "elapsed_s": round(time.time() - started, 2),
            }, ensure_ascii=False, indent=2))
            return

        inserted = 0
        buf = []
        for r in rows:
            buf.append((TABLE, r["id"], r["id"], r["ch"], now, now))
            if len(buf) >= args.batch:
                conn.executemany(
                    "INSERT OR REPLACE INTO projection_meta "
                    "(table_name, memory_id, projection_key, content_hash, last_verified, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    buf,
                )
                conn.commit()
                inserted += len(buf)
                buf = []
        if buf:
            conn.executemany(
                "INSERT OR REPLACE INTO projection_meta "
                "(table_name, memory_id, projection_key, content_hash, last_verified, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                buf,
            )
            conn.commit()
            inserted += len(buf)

        still_missing = conn.execute(
            "SELECT COUNT(*) FROM memories m WHERE m.layer='workspace_markdown' "
            "AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0)=0 "
            "AND NOT EXISTS (SELECT 1 FROM projection_meta pm WHERE pm.memory_id=m.id)"
        ).fetchone()[0]
        total_pm = conn.execute("SELECT COUNT(*) FROM projection_meta").fetchone()[0]

    print(json.dumps({
        "mode": "apply",
        "inserted": inserted,
        "still_missing": still_missing,
        "projection_meta_total": total_pm,
        "elapsed_s": round(time.time() - started, 2),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
