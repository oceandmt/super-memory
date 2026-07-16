from pathlib import Path
from super_memory.quality_gate import apply_quality_gate
from super_memory.semantic_calibration import evaluate_corpus
from super_memory.semantic_classifier import classify_semantic_type

def test_completion_report_is_not_false_blocker():
    c=classify_semantic_type("Completed successfully; 4 tests failed earlier but all tests now pass.")
    assert c.semantic_type == "event"

def test_dimensions_and_authoritative_score():
    out=apply_quality_gate({"content":"Decision: we decided to use SQLite because it is local-first.","type":"context","scope":"project","source":"test","metadata":{"quality_score":1.0,"quality_gate":{"quality_score":0.0}}})
    m=out["metadata"]
    assert out["type"]=="decision" and m["truth_level"]=="asserted" and m["projection_type"]=="canonical_memory" and m["scope"]=="project"
    assert m["quality_score"]==m["quality"]["overall"]==m["quality_gate"]["quality_score"]
    assert set(m["quality"]["components"])=={"content_quality","completeness","source_trust","extraction_confidence","freshness"}

def test_calibration_gate():
    metrics=evaluate_corpus(Path(__file__).parent/"fixtures/semantic_quality/v1.jsonl")
    assert all(metrics["gate"].values()), metrics
