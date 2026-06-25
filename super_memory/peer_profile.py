from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from .config import load_config
from .storage import SuperMemoryStore

def ensure_peer_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS peer_profiles (peer_id TEXT PRIMARY KEY, workspace TEXT NOT NULL DEFAULT 'openclaw', role TEXT, display_name TEXT, stable_facts_json TEXT NOT NULL DEFAULT '[]', preferences_json TEXT NOT NULL DEFAULT '[]', goals_json TEXT NOT NULL DEFAULT '[]', habits_json TEXT NOT NULL DEFAULT '[]', constraints_json TEXT NOT NULL DEFAULT '[]', confidence REAL DEFAULT 0.7, updated_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS perspective_memories (id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, observer_peer_id TEXT NOT NULL, observed_peer_id TEXT NOT NULL, workspace TEXT NOT NULL DEFAULT 'openclaw', session_id TEXT, observation_type TEXT, confidence REAL, source_ids_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}')''')

def upsert_peer_profile(peer_id:str, workspace:str='openclaw', role:str='human', facts:list[str]|None=None, preferences:list[str]|None=None, goals:list[str]|None=None, habits:list[str]|None=None, constraints:list[str]|None=None, confidence:float=.7, metadata:dict[str,Any]|None=None, config_path:str|None=None)->dict[str,Any]:
    cfg=load_config(config_path); store=SuperMemoryStore(cfg); now=datetime.now(timezone.utc).isoformat()
    with store.connect() as conn:
        ensure_peer_tables(conn)
        old=conn.execute('SELECT * FROM peer_profiles WHERE peer_id=?',(peer_id,)).fetchone()
        def merge(col, vals):
            base=json.loads(old[col] if old else '[]'); out=[]; seen=set()
            for x in [*base, *(vals or [])]:
                if x and x not in seen: seen.add(x); out.append(x)
            return out
        conn.execute('''INSERT OR REPLACE INTO peer_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(peer_id,workspace,role,peer_id,json.dumps(merge('stable_facts_json',facts),ensure_ascii=False),json.dumps(merge('preferences_json',preferences),ensure_ascii=False),json.dumps(merge('goals_json',goals),ensure_ascii=False),json.dumps(merge('habits_json',habits),ensure_ascii=False),json.dumps(merge('constraints_json',constraints),ensure_ascii=False),confidence,now,json.dumps(metadata or {},ensure_ascii=False)))
        conn.commit()
    return {'ok':True,'peer_id':peer_id,'updated_at':now}

def get_peer_profile(peer_id:str, config_path:str|None=None)->dict[str,Any]:
    cfg=load_config(config_path); store=SuperMemoryStore(cfg)
    with store.connect() as conn:
        ensure_peer_tables(conn); r=conn.execute('SELECT * FROM peer_profiles WHERE peer_id=?',(peer_id,)).fetchone()
        if not r: return {'ok':False,'error':'peer_not_found','peer_id':peer_id}
        d=dict(r)
        for k in ['stable_facts_json','preferences_json','goals_json','habits_json','constraints_json','metadata_json']:
            d[k[:-5] if k.endswith('_json') else k]=json.loads(d.pop(k) or ('{}' if k=='metadata_json' else '[]'))
        return {'ok':True,'profile':d}

def record_perspective(memory_id:str, observer_peer_id:str, observed_peer_id:str, workspace:str='openclaw', session_id:str|None=None, observation_type:str='explicit', confidence:float=.7, source_ids:list[str]|None=None, metadata:dict[str,Any]|None=None, config_path:str|None=None)->dict[str,Any]:
    import uuid
    cfg=load_config(config_path); store=SuperMemoryStore(cfg); now=datetime.now(timezone.utc).isoformat(); pid=str(uuid.uuid4())
    with store.connect() as conn:
        ensure_peer_tables(conn)
        conn.execute('INSERT INTO perspective_memories VALUES (?,?,?,?,?,?,?,?,?,?,?)',(pid,memory_id,observer_peer_id,observed_peer_id,workspace,session_id,observation_type,confidence,json.dumps(source_ids or [],ensure_ascii=False),now,json.dumps(metadata or {},ensure_ascii=False)))
        conn.commit()
    return {'ok':True,'id':pid,'memory_id':memory_id}
