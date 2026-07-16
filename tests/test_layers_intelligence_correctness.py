import math, sqlite3
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import pytest
from super_memory.temporal_decay import apply_temporal_decay
from super_memory.hypothesis_engine import HypothesisEngine
from super_memory.spreading_activation import SpreadingActivation
from super_memory.self_improve import should_capture_lesson, _lesson_observation

def test_half_life_exact_and_invalid():
    now=datetime.now(timezone.utc); items=[{"timestamp":now-timedelta(days=10),"score":1.0}]
    assert apply_temporal_decay(items,half_life=10,now=now)[0]["score"] == pytest.approx(.5)
    for value in (0,-1,float("inf"),float("nan")):
        with pytest.raises(ValueError): apply_temporal_decay([{"timestamp":now,"score":1}],half_life=value,now=now)

def test_hypothesis_requires_grounding_dedups_and_challenges():
    e=HypothesisEngine(); h=e.create_hypothesis("x")
    with pytest.raises(ValueError): e.add_evidence(h.id,"claim",source_id="s",direction="banana")
    assert e.add_evidence(h.id,"claim",source_id="s")
    assert e.add_evidence(h.id,"claim",source_id="s") is None
    assert h.evidence_ids == [e.get_evidence(h.id)[0].id]
    state=e.to_save_dict(); restored=HypothesisEngine(state)
    assert restored.get_evidence(h.id)[0].source_id == "s"

def test_activation_uses_relation_schema_and_surfaces_schema_errors():
    db=sqlite3.connect(":memory:"); db.row_factory=sqlite3.Row
    db.executescript("CREATE TABLE cognitive_neurons(id TEXT,content TEXT,kind TEXT); CREATE TABLE cognitive_synapses(source_neuron_id TEXT,target_neuron_id TEXT,relation TEXT,weight REAL); INSERT INTO cognitive_neurons VALUES('a','A','memory'),('b','B','entity'); INSERT INTO cognitive_synapses VALUES('a','b','mentions',.8);")
    config=SimpleNamespace(max_spread_hops=4, min_activation_threshold=.01)
    results,_=SpreadingActivation(db,config).activate(["a"]); assert "b" in results
    db.execute("DROP TABLE cognitive_synapses")
    with pytest.raises(RuntimeError): SpreadingActivation(db,config).activate(["a"])

def test_lesson_extraction_requires_grounded_outcome_and_word_boundaries():
    assert not should_capture_lesson("prefixedly")
    assert _lesson_observation("Failure occurred. We fixed the parser. Tests passed.") == {"problem":"Failure occurred.","action":"We fixed the parser.","outcome":"Tests passed."}
    assert _lesson_observation("A failure was quoted but no action happened.") is None
