from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from typing import Any
from ..config import load_config
from ..storage import SuperMemoryStore

def ensure_manifest(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS projection_manifest (
        projection_id TEXT PRIMARY KEY,
        memory_id TEXT NOT NULL,
        projection_type TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        projection_hash TEXT,
        adapter_name TEXT,
        adapter_version TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_projection_manifest_memory ON projection_manifest(memory_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_projection_manifest_type_status ON projection_manifest(projection_type,status)')

def hash_text(text:str)->str: return hashlib.sha256((text or '').encode()).hexdigest()

def register_projection(memory_id:str, projection_type:str, source_content:str='', projection_content:str='', adapter_name:str='super-memory', adapter_version:str='1', status:str='active', metadata:dict[str,Any]|None=None, config_path:str|None=None)->dict[str,Any]:
    cfg=load_config(config_path); store=SuperMemoryStore(cfg); now=datetime.now(timezone.utc).isoformat()
    source_hash=hash_text(source_content); projection_hash=hash_text(projection_content) if projection_content else None
    pid=f'{memory_id}:{projection_type}:{source_hash[:16]}'
    with store.connect() as conn:
        ensure_manifest(conn)
        conn.execute('''INSERT OR REPLACE INTO projection_manifest
        (projection_id,memory_id,projection_type,source_hash,projection_hash,adapter_name,adapter_version,status,created_at,updated_at,metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM projection_manifest WHERE projection_id=?), ?), ?, ?)''',
        (pid,memory_id,projection_type,source_hash,projection_hash,adapter_name,adapter_version,status,pid,now,now,json.dumps(metadata or {},ensure_ascii=False)))
        conn.commit()
    return {'ok':True,'projection_id':pid,'memory_id':memory_id,'projection_type':projection_type,'status':status}

def audit_projection_drift(config_path:str|None=None, limit:int=200)->dict[str,Any]:
    cfg=load_config(config_path); store=SuperMemoryStore(cfg)
    with store.connect() as conn:
        ensure_manifest(conn)
        orphans=[dict(r) for r in conn.execute('''SELECT p.* FROM projection_manifest p LEFT JOIN memories m ON m.id=p.memory_id WHERE m.id IS NULL LIMIT ?''',(limit,)).fetchall()]
        stale=[]
        for r in conn.execute('''SELECT p.*, m.content FROM projection_manifest p JOIN memories m ON m.id=p.memory_id LIMIT ?''',(limit,)).fetchall():
            d=dict(r)
            if d['source_hash'] != hash_text(d.get('content') or ''): stale.append({k:v for k,v in d.items() if k!='content'})
        missing=[]
        for r in conn.execute('''SELECT id, content FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1 LIMIT ?''',(limit,)).fetchall():
            cnt=conn.execute('SELECT COUNT(*) c FROM projection_manifest WHERE memory_id=?',(r['id'],)).fetchone()['c']
            if cnt==0: missing.append({'memory_id':r['id'],'reason':'no_projection_manifest'})
        return {'ok':True,'orphans':orphans,'stale':stale,'missing':missing,'counts':{'orphans':len(orphans),'stale':len(stale),'missing':len(missing)}}

def repair_projection_drift(config_path:str|None=None, dry_run:bool=True)->dict[str,Any]:
    audit=audit_projection_drift(config_path)
    if dry_run: return {'ok':True,'dry_run':True,'audit':audit,'changed':0}
    cfg=load_config(config_path); store=SuperMemoryStore(cfg); changed=0
    with store.connect() as conn:
        ensure_manifest(conn)
        for o in audit['orphans']:
            conn.execute("UPDATE projection_manifest SET status='orphaned', updated_at=? WHERE projection_id=?",(datetime.now(timezone.utc).isoformat(),o['projection_id'])); changed+=1
        for s in audit['stale']:
            conn.execute("UPDATE projection_manifest SET status='stale', updated_at=? WHERE projection_id=?",(datetime.now(timezone.utc).isoformat(),s['projection_id'])); changed+=1
        conn.commit()
    return {'ok':True,'dry_run':False,'audit':audit,'changed':changed}

def backfill_projection_manifest(config_path: str | None = None, limit: int = 500, projection_type: str = 'canonical_memory') -> dict[str, Any]:
    """Create baseline manifest rows for existing active memories.

    This is a safe transitional backfill: it does not create derived data, only
    records the current canonical/source hash so future drift audits can
    distinguish old untracked memories from true missing projections.
    """
    cfg = load_config(config_path); store = SuperMemoryStore(cfg); changed = 0
    with store.connect() as conn:
        ensure_manifest(conn)
        rows = conn.execute("""SELECT id, content FROM memories
            WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
            LIMIT ?""", (limit,)).fetchall()
        for r in rows:
            pid = f"{r['id']}:{projection_type}:{hash_text(r['content'] or '')[:16]}"
            exists = conn.execute('SELECT 1 FROM projection_manifest WHERE projection_id=?', (pid,)).fetchone()
            if exists: continue
            now = datetime.now(timezone.utc).isoformat()
            conn.execute('''INSERT INTO projection_manifest
                (projection_id,memory_id,projection_type,source_hash,projection_hash,adapter_name,adapter_version,status,created_at,updated_at,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (pid, r['id'], projection_type, hash_text(r['content'] or ''), None, 'backfill', '1', 'active', now, now, json.dumps({'backfill': True}, ensure_ascii=False)))
            changed += 1
        conn.commit()
    return {'ok': True, 'changed': changed, 'limit': limit, 'projection_type': projection_type}
