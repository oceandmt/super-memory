from super_memory.quality_gate import apply_quality_gate
from super_memory.recall_arbitration import arbitrate
from super_memory.self_training import capture_failed_recall
from super_memory.semantic_taxonomy import normalize_relations

def test_quality_gate_adds_metadata():
    p=apply_quality_gate({'content':'Decision: use projects/super-memory-github for Super Memory v2.0.0 config','type':'context','source':'test'})
    assert p['type'] == 'decision'
    assert p['metadata']['quality_score'] > 0
    assert p['metadata']['entities']

def test_recall_arbitration_explainable():
    layered={'workspace_markdown':[{'id':'1','content':'Super Memory installed at projects/super-memory-github','type':'fact','source':'test','metadata':{'quality_score':.9},'trust_score':.9}]}
    r=arbitrate('where is super memory installed', layered)
    assert r['winner_policy']=='workspace_markdown'
    assert r['answer_context'][0]['why_selected']

def test_semantic_taxonomy_normalizes():
    rel=normalize_relations([{'type':'synced_with','source':'Super Memory','target':'oceandmt/super-memory'}])[0]
    assert rel['type']=='SYNCED_WITH'
    assert rel['source']=='super-memory'

def test_failed_recall_capture_tmp(tmp_path, monkeypatch):
    from super_memory.models import SuperMemoryConfig
    import super_memory.self_training as st
    monkeypatch.setattr(st, 'load_config', lambda config_path=None: SuperMemoryConfig(workspace_root=tmp_path))
    r=capture_failed_recall('q','bad','good')
    assert r['ok']
