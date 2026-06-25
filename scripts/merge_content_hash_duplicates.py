#!/usr/bin/env python3
"""Merge Super Memory exact content_hash duplicates across distinct memory IDs.

This is intentionally conservative:
- Only operates on exact content_hash groups with >1 distinct id.
- Keeps the earliest workspace_markdown row as canonical when available.
- Soft-deletes duplicate IDs by setting metadata_json.soft_deleted=1 on all layers.
- Annotates canonical rows with merged_from/merged_at.
- Does not touch the expected 4-layer projection for the kept canonical ID.

Usage:
  python scripts/merge_content_hash_duplicates.py --dry-run
  python scripts/merge_content_hash_duplicates.py --apply
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path('/home/oceandmt/.openclaw/workspace/data/super-memory.sqlite3')
ACTIVE = "(json_extract(metadata_json, '$.soft_deleted') IS NULL OR json_extract(metadata_json, '$.soft_deleted') != 1)"


def jloads(s: str | None) -> dict:
    try:
        return json.loads(s or '{}')
    except Exception:
        return {}


def choose_canonical(rows: list[sqlite3.Row]) -> str:
    # Prefer workspace_markdown, non-empty content, earliest created_at.
    candidates = sorted(
        rows,
        key=lambda r: (
            0 if r['layer'] == 'workspace_markdown' else 1,
            0 if (r['content'] or '').strip() else 1,
            r['created_at'] or '',
            r['id'],
        ),
    )
    return candidates[0]['id']


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='apply soft-delete merge')
    ap.add_argument('--dry-run', action='store_true', help='show plan only')
    ap.add_argument('--limit', type=int, default=0, help='limit number of duplicate hashes to process')
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        args.dry_run = True

    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=60000')

    groups = conn.execute(f"""
        SELECT content_hash, COUNT(DISTINCT id) AS distinct_ids, COUNT(*) AS total_rows
        FROM memories
        WHERE content_hash IS NOT NULL AND {ACTIVE}
        GROUP BY content_hash
        HAVING distinct_ids > 1
        ORDER BY distinct_ids DESC, total_rows DESC
    """).fetchall()
    if args.limit:
        groups = groups[:args.limit]

    now = datetime.now(timezone.utc).isoformat()
    plan = []
    soft_deleted_rows = 0
    duplicate_ids_total = 0

    for g in groups:
        rows = conn.execute(f"""
            SELECT id, layer, content, type, created_at, metadata_json, content_hash
            FROM memories
            WHERE content_hash=? AND {ACTIVE}
            ORDER BY created_at ASC, id ASC, layer ASC
        """, (g['content_hash'],)).fetchall()
        ids = sorted({r['id'] for r in rows})
        if len(ids) <= 1:
            continue
        canonical_id = choose_canonical(rows)
        duplicate_ids = [i for i in ids if i != canonical_id]
        duplicate_ids_total += len(duplicate_ids)
        sample = (rows[0]['content'] or '')[:100].replace('\n', '\\n')
        plan.append({
            'content_hash': g['content_hash'],
            'canonical': canonical_id,
            'duplicates': duplicate_ids,
            'duplicate_count': len(duplicate_ids),
            'rows_affected_if_apply': sum(1 for r in rows if r['id'] in duplicate_ids),
            'sample': sample,
        })

        if args.apply:
            # Annotate canonical rows in all layers.
            canon_rows = conn.execute('SELECT id, layer, metadata_json FROM memories WHERE id=?', (canonical_id,)).fetchall()
            for cr in canon_rows:
                meta = jloads(cr['metadata_json'])
                merged = list(dict.fromkeys([*meta.get('merged_from', []), *duplicate_ids]))
                meta['merged_from'] = merged
                meta['merged_at'] = now
                meta['merge_strategy'] = 'exact_content_hash'
                conn.execute('UPDATE memories SET metadata_json=? WHERE id=? AND layer=?', (json.dumps(meta, ensure_ascii=False), cr['id'], cr['layer']))

            # Soft-delete duplicate rows in all layers.
            for dup_id in duplicate_ids:
                dup_rows = conn.execute('SELECT id, layer, metadata_json FROM memories WHERE id=?', (dup_id,)).fetchall()
                for dr in dup_rows:
                    meta = jloads(dr['metadata_json'])
                    if meta.get('soft_deleted') == 1:
                        continue
                    meta['soft_deleted'] = 1
                    meta['deleted_at'] = now
                    meta['deleted_reason'] = 'merged_duplicate_exact_content_hash'
                    meta['merged_into'] = canonical_id
                    conn.execute('UPDATE memories SET metadata_json=? WHERE id=? AND layer=?', (json.dumps(meta, ensure_ascii=False), dr['id'], dr['layer']))
                    soft_deleted_rows += 1

    if args.apply:
        conn.commit()

    print(json.dumps({
        'ok': True,
        'dry_run': not args.apply,
        'db': str(DB),
        'duplicate_hash_groups': len(plan),
        'duplicate_distinct_ids_to_merge': duplicate_ids_total,
        'soft_deleted_rows': soft_deleted_rows,
        'sample_plan': plan[:20],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
