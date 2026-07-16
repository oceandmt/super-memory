import json, sqlite3
from super_memory.memory_quality import evaluate_completeness, enrich_quality_metadata, ensure_quality_tables, evolve_trust, build_evidence_chain, temporal_query

def _db():
    c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE memories(id TEXT PRIMARY KEY,content TEXT,trust_score REAL,source TEXT,created_at TEXT,metadata_json TEXT)')
    ensure_quality_tables(c); return c

def test_type_aware_completeness_and_quality_contract():
    weak=evaluate_completeness('Decision: use SQLite','decision',{})
    assert 'rationale' in weak.missing and weak.score == .5
    enriched=enrich_quality_metadata('Decision: use SQLite because local-first is required.','decision',{})
    assert enriched['quality']['version']=='2.0'
    assert enriched['completeness']['score']==1.0

def test_evidence_chain_and_trust_evolution():
    c=_db(); now='2026-07-16T00:00:00Z'
    c.executemany('INSERT INTO memories VALUES(?,?,?,?,?,?)', [('a','claim',.5,'x',now,json.dumps({'quality_score':.8,'canonical':True})),('b','proof',.9,'y',now,'{}')])
    c.execute("INSERT INTO memory_evidence(memory_id,evidence_memory_id,relation,confidence) VALUES('a','b','supports',.9)")
    result=evolve_trust(c,'a'); assert result['ok'] and result['trust_score'] > .7
    chain=build_evidence_chain(c,'a'); assert chain['ok'] and len(chain['nodes'])==2 and chain['edges'][0]['relation']=='supports'

def test_temporal_query_honors_validity():
    c=_db(); c.execute('INSERT INTO memories VALUES(?,?,?,?,?,?)',('a','current',.8,'x','2026-07-01T00:00:00Z',json.dumps({'valid_until':'2026-07-31T00:00:00Z'})))
    c.execute('INSERT INTO memories VALUES(?,?,?,?,?,?)',('b','expired',.8,'x','2026-06-01T00:00:00Z',json.dumps({'valid_until':'2026-06-30T00:00:00Z'})))
    out=temporal_query(c,'2026-07-10T00:00:00Z','2026-07-20T00:00:00Z'); assert [m['id'] for m in out['memories']]==['a']

def test_bridge_completeness_api():
    from super_memory.bridge import memory_completeness
    out=memory_completeness('TODO: fix projection; status pending','todo')
    assert out['ok'] and out['score']==1.0
