from __future__ import annotations
from pathlib import Path
from super_memory.models import SuperMemoryConfig
from super_memory.migrations import run_migrations
from super_memory.core.envelope import build_envelope
from super_memory.core.write_gate import evaluate_write
from super_memory.projections.manifest import register_projection, audit_projection_drift
from super_memory.long_memory import compress_long_memory
from super_memory.recall.arbitration_v4 import arbitrate_v4
from super_memory.peer_profile import upsert_peer_profile, get_peer_profile, record_perspective
from super_memory.recall_benchmark import create_recall_case, run_recall_benchmark


def cfg(tmp_path: Path):
    c=SuperMemoryConfig(workspace_root=tmp_path, sqlite_path='data/test.sqlite3')
    run_migrations(c)
    cp=tmp_path/'super-memory.yaml'
    cp.write_text(f'workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n', encoding='utf-8')
    return str(cp)


def test_envelope_and_write_gate_contract():
    env=build_envelope('Decision: use projection manifest for drift repair.', memory_type='decision', scope='project', source_adapter='test')
    res=evaluate_write(env)
    assert res.allow is True
    assert res.action == 'save'
    assert env.to_memory_record()['metadata']['envelope_version'] == '1.0'


def test_projection_manifest_and_peer_profile(tmp_path):
    cp=cfg(tmp_path)
    r=register_projection('m1','graph','hello','node',config_path=cp)
    assert r['ok']
    audit=audit_projection_drift(config_path=cp)
    assert audit['ok']
    p=upsert_peer_profile('boss', facts=['likes careful DB maintenance'], config_path=cp)
    assert p['ok']
    prof=get_peer_profile('boss', config_path=cp)
    assert prof['profile']['stable_facts'] == ['likes careful DB maintenance']
    pr=record_perspective('m1','lucas','boss',config_path=cp)
    assert pr['ok']


def test_long_memory_compression_and_recall_v4(tmp_path):
    cp=cfg(tmp_path)
    from super_memory.config import load_config
    from super_memory.storage import SuperMemoryStore
    import sqlite3, json
    c=load_config(cp); store=SuperMemoryStore(c)
    text='Long memory about recall quality and semantic drawers. '*80
    with store.connect() as conn:
        conn.execute("INSERT INTO memories (id, layer, content, type, scope, agent_id, tags_json, metadata_json) VALUES (?,?,?,?,?,?,?,?)",('long1','workspace_markdown',text,'context','project','lucas','[]','{}'))
        conn.commit()
    out=compress_long_memory('long1', dry_run=False, config_path=cp)
    assert out['ok'] and out['chunks'] >= 2
    arb=arbitrate_v4('semantic drawers recall quality', {'semantic_closet':[{'id':'long1','content':out['summary'],'metadata':{'quality_score':.8,'trust_score':.8}}]})
    assert arb['answer_context'][0]['memory_id'] == 'long1'


def test_recall_benchmark_empty_and_case(tmp_path):
    cp=cfg(tmp_path)
    case=create_recall_case('projection manifest drift', expected_contains=[], config_path=cp)
    assert case['ok']
    bench=run_recall_benchmark(config_path=cp)
    assert bench['total'] == 1
