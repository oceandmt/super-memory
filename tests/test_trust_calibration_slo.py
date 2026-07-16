import json, sqlite3
from datetime import datetime, timezone, timedelta

import pytest
from super_memory.trust_calibration import (CalibrationModel, TrustEvidence, brier_score,
 expected_calibration_error, evaluate, init_schema, record_event)
from super_memory.operational_slo import snapshot


def evidence(v=.8): return TrustEvidence(v,v,v,v,v,v)

def test_calibration_dimensions_version_and_metrics(tmp_path):
    model=CalibrationModel('v2',{k:1 for k in evidence().__dataclass_fields__},-3)
    assert 0 < model.predict(evidence()) < 1
    report=evaluate(model,[(evidence(.9),1),(evidence(.1),0)],bins=2)
    assert report['model_version']=='v2' and report['brier_score'] < .1
    assert brier_score([.8,.2],[1,0]) == pytest.approx(.04)
    assert expected_calibration_error([.8,.2],[1,0],2) == pytest.approx(.2)
    with pytest.raises(ValueError): TrustEvidence(2,.5,.5,.5,.5,.5)
    with pytest.raises(ValueError): CalibrationModel('bad',{'edge_count':1})
    db=sqlite3.connect(tmp_path/'x.db'); init_schema(db); event=record_event(db,evidence(),model=model,outcome=True); db.commit()
    assert event['model_version']=='v2'
    payload=json.loads(db.execute('select evidence_json from trust_calibration_events').fetchone()[0])
    assert set(payload)==set(evidence().__dataclass_fields__) and 'edge_count' not in payload


def test_slo_snapshot_is_bounded_and_rates(tmp_path):
    db=tmp_path/'slo.db'; c=sqlite3.connect(db)
    c.executescript('''CREATE TABLE memories(id TEXT,layer TEXT,created_at TEXT,pending_canonical_sync INTEGER,soft_deleted INTEGER);
    CREATE TABLE telemetry_events(kind TEXT,success INTEGER,duration_ms REAL,detail_json TEXT,created_at TEXT);
    CREATE TABLE recall_events(outcome TEXT);''')
    now=datetime.now(timezone.utc); old=(now-timedelta(minutes=10)).isoformat()
    c.executemany('INSERT INTO memories VALUES(?,?,?,?,?)',[('a','workspace_markdown',now.isoformat(),0,0),('a','mempalace',old,0,0)])
    c.executemany('INSERT INTO telemetry_events VALUES(?,?,?,?,?)',[('recall',1,100,'{"fallback":true}',now.isoformat()),('recall',1,900,'{"empty":true}',now.isoformat())])
    c.executemany('INSERT INTO recall_events VALUES(?)',[('corrected',),('success',)]); c.commit(); c.close()
    out=snapshot(db,window_hours=1,limit=10,now=now)
    assert out['bounded']=={'window_hours':1,'row_limit':10}
    assert out['metrics']['recall_p50_ms'] in (100,900)
    assert out['metrics']['recall_p95_ms']==900
    assert out['metrics']['fallback_rate']==.5 and out['metrics']['empty_success_rate']==.5
    assert out['metrics']['correction_rate']==.5
    assert 'recall_p95_ms' in out['alerts']
    with pytest.raises(ValueError): snapshot(db,limit=50001)
