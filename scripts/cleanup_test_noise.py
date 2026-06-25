#!/usr/bin/env python3
"""Soft-delete clearly identifiable test/debug/noise memory entries.
Safe to run concurrently with read-only API server.
"""
import sqlite3, json, sys, time
from datetime import datetime, timezone

DB = '/home/oceandmt/.openclaw/workspace/data/super-memory.sqlite3'

JUNK_IDS = [
    'wq2','wq3','wq5','wq6','wq7',
    '2ad5b4a2-9197-420b-adb0-a06be02fc6b7',  # "edited content"
    'bcf23a24-a436-446f-a2d6-01e9e4006880',  # "pin target"
    '9bff7009-3b63-4bc7-8cd6-d0c2f4d18917',  # "forget soft debug"
    '057f3e54-2c33-444b-bf65-2bdd66e00c7b',  # "recall-remember"
    '6bf49a33-9347-4108-97b1-bad8d5301d10',  # "remember-recall"
    '286e93fd-25c7-4d34-8567-ae061d7de3a3',  # "remember-remember"
    '814af87b-97e1-40ba-80c7-056855c832f8',  # "recall-recall"
    'f81ff478-26f3-41e4-9b2f-7b53c3d9e5b2',  # "recall | remember"
    'cc644ce6-92c5-4be4-bbad-06e7b0d56b11',  # "TEST2 error alias"
    '74d72ff4-e8d1-4f71-aaa0-a91757583486',  # "TEST2 todo alias"
    'e3ce5edb-bba4-4dc3-b0d3-c6fbf09bef2c',  # "None type test"
    'e511b4b5-81f1-4f4d-8b64-cd3dd97e0699',  # "p2 edited"
    'c1254695-1950-4563-ac89-b7a5e64e0d24',  # "user: Làm tiếp đi"
    'ec3a9ecf-7fe6-459e-9a27-de863fe7aa59',  # "user: làm tiếp đi"
    'e5ea1e63-9954-4f60-bed8-5d64de0e932f',  # "deferred test memory"
]

# Also cleanup empty-content entries that weren't caught by merge script
# (keep if they have meaningful IDs/layers)

dry_run = '--dry-run' in sys.argv

conn = sqlite3.connect(DB, timeout=60)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA busy_timeout=60000')
now = datetime.now(timezone.utc).isoformat()

deleted = 0
skipped = 0
for id in JUNK_IDS:
    rows = conn.execute(
        "SELECT id, layer, metadata_json FROM memories WHERE id=? AND "
        "(json_extract(metadata_json,'$.soft_deleted') IS NULL OR json_extract(metadata_json,'$.soft_deleted')!=1)",
        (id,)
    ).fetchall()
    if not rows:
        skipped += 1
        continue
    for r in rows:
        meta = json.loads(r['metadata_json'] or '{}')
        if not dry_run:
            meta['soft_deleted'] = 1
            meta['deleted_at'] = now
            meta['deleted_reason'] = 'cleanup_test_noise'
            conn.execute('UPDATE memories SET metadata_json=? WHERE id=? AND layer=?',
                         (json.dumps(meta, ensure_ascii=False), r['id'], r['layer']))
        deleted += 1

if not dry_run:
    conn.commit()

print(json.dumps({
    'ok': True,
    'dry_run': dry_run,
    'targeted_ids': len(JUNK_IDS),
    'deleted_rows': deleted,
    'skipped_already_deleted': skipped,
}, indent=2))
