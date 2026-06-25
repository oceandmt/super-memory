from __future__ import annotations
import hashlib, json, textwrap
from datetime import datetime, timezone
from typing import Any
from .config import load_config
from .storage import SuperMemoryStore
from .projections.manifest import register_projection

def _chunks(text:str, size:int=1200, overlap:int=160):
    i=0; n=len(text)
    while i<n:
        yield i, min(n,i+size), text[i:min(n,i+size)]
        if i+size>=n: break
        i += max(1,size-overlap)

def review_long_memories(threshold:int=2000, limit:int=100, config_path:str|None=None)->dict[str,Any]:
    cfg=load_config(config_path); store=SuperMemoryStore(cfg)
    with store.connect() as conn:
        rows=[dict(r) for r in conn.execute('''SELECT id, layer, length(content) len, type, created_at FROM memories
        WHERE length(content)>?
          AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
          AND NOT (json_extract(metadata_json,'$.compression_policy')='verbatim_drawers_plus_summary'
                   AND COALESCE(json_extract(metadata_json,'$.canonical_retained'),0) IN (1, 'true'))
        ORDER BY length(content) DESC LIMIT ?''',(threshold,limit)).fetchall()]
    return {'ok':True,'threshold':threshold,'count':len(rows),'candidates':rows}

def compress_long_memory(memory_id:str, layer:str='workspace_markdown', chunk_size:int=1200, overlap:int=160, config_path:str|None=None, dry_run:bool=True)->dict[str,Any]:
    cfg=load_config(config_path); store=SuperMemoryStore(cfg)
    with store.connect() as conn:
        row=conn.execute('SELECT rowid,* FROM memories WHERE id=? AND layer=?',(memory_id,layer)).fetchone()
        if not row: return {'ok':False,'error':'memory_not_found'}
        content=row['content'] or ''
        pieces=[]
        for start,end,chunk in _chunks(content,chunk_size,overlap):
            did=f"drawer:{memory_id}:{start}:{end}:{hashlib.sha256(chunk.encode()).hexdigest()[:12]}"
            closet=' '.join(chunk.split()[:40])
            pieces.append({'drawer_id':did,'start':start,'end':end,'content':chunk,'closet':closet})
        summary=textwrap.shorten(' '.join(content.split()), width=700, placeholder=' …')
        if dry_run:
            return {'ok':True,'dry_run':True,'memory_id':memory_id,'chunks':len(pieces),'summary':summary,'drawer_ids':[p['drawer_id'] for p in pieces]}
        conn.execute('''CREATE TABLE IF NOT EXISTS semantic_drawers (drawer_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, layer TEXT, start_offset INTEGER, end_offset INTEGER, content TEXT NOT NULL, created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS semantic_closets (closet_id TEXT PRIMARY KEY, drawer_id TEXT NOT NULL, memory_id TEXT NOT NULL, closet_text TEXT NOT NULL, created_at TEXT NOT NULL)''')
        now=datetime.now(timezone.utc).isoformat()
        for p in pieces:
            conn.execute('INSERT OR REPLACE INTO semantic_drawers VALUES (?,?,?,?,?,?,?)',(p['drawer_id'],memory_id,layer,p['start'],p['end'],p['content'],now))
            cid='closet:'+p['drawer_id']
            conn.execute('INSERT OR REPLACE INTO semantic_closets VALUES (?,?,?,?,?)',(cid,p['drawer_id'],memory_id,p['closet'],now))
        meta=json.loads(row['metadata_json'] or '{}'); meta.update({'compression_candidate':True,'compression_policy':'verbatim_drawers_plus_summary','drawer_count':len(pieces),'compressed_at':now,'canonical_retained':True,'summary':summary})
        conn.execute('UPDATE memories SET metadata_json=? WHERE id=? AND layer=?',(json.dumps(meta,ensure_ascii=False),memory_id,layer))
        conn.commit()
    register_projection(memory_id,'semantic_drawers',content,summary,adapter_name='long_memory',adapter_version='1',metadata={'drawer_count':len(pieces)},config_path=config_path)
    return {'ok':True,'dry_run':False,'memory_id':memory_id,'chunks':len(pieces),'summary':summary,'drawer_ids':[p['drawer_id'] for p in pieces]}

def compress_long_memories(limit:int=20, config_path:str|None=None, dry_run:bool=True)->dict[str,Any]:
    cands=review_long_memories(limit=limit,config_path=config_path)['candidates']; items=[]
    seen=set()
    for c in cands:
        if c['id'] in seen: continue
        seen.add(c['id']); items.append(compress_long_memory(c['id'],c['layer'],config_path=config_path,dry_run=dry_run))
    return {'ok':all(i.get('ok') for i in items),'dry_run':dry_run,'processed':len(items),'items':items}
