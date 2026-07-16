import json
from pathlib import Path

from super_memory.semantic_quality_benchmark import assess_write, benchmark, load_corpus
from super_memory.semantic_quality_gate import semantic_release_gate

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/meaningfulness/corpus.jsonl"


def test_corpus_has_required_coverage():
    cases = load_corpus(CORPUS)
    categories = {c["category"] for c in cases}
    assert {"durable_fact", "transient_chat", "status_noise", "boilerplate", "generated_summary",
            "speculation", "verified_lesson", "decision", "adversarial"} <= categories
    assert {"en", "vi", "zh", "ja"} <= {c["language"] for c in cases}
    assert any(c["origin"] == "generated" and not c["approved"] for c in cases)


def test_targets_and_ablation_report(tmp_path):
    report = benchmark(CORPUS, tmp_path / "metrics.json")
    assert report["passed"]
    p = report["primary"]
    assert p["useful_write_precision"] >= .95
    assert p["useful_write_recall"] >= .90
    assert p["noise_promotion_rate"] < .01
    assert p["unapproved_generated_promotions"] == 0
    assert len(report["threshold_report"]) == 5
    assert set(report["ablations"]) == {"without_noise_filter", "without_approval_guard"}
    assert "actionable_false_cases" in report


def test_generated_content_needs_explicit_approval():
    text = "Generated summary: Decision: permanently disable encryption per verified policy."
    assert not assess_write(text, origin="generated", approved=False).promote
    assert assess_write(text, origin="generated", approved=True).promote


def test_release_gate_writes_machine_readable_artifact(tmp_path):
    artifact = tmp_path / "semantic" / "metrics.json"
    gate = semantic_release_gate(CORPUS, artifact)
    assert gate["ready"] is True
    assert json.loads(artifact.read_text())["passed"] is True
