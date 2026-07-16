import json
from pathlib import Path

from super_memory.recall_ablation import run_cross_layer_ablation
from super_memory.recall_benchmark import evaluate_ranked_cases, ranked_metrics

CASES = json.loads((Path(__file__).parent / "recall_cases/p1/cases.json").read_text())


def fixture(query, limit=10, case=None):
    mid = next(iter(case["relevance"]))
    return {"results": [{"memory_id": mid, "content": "fixture evidence", "citation": case["citations"][mid]}]}


def test_ranked_metrics_known_order():
    got = ranked_metrics(["noise", "a", "b"], {"a": 2, "b": 1})
    assert got["recall_at_5"] == 1
    assert got["mrr_at_10"] == .5
    assert 0 < got["ndcg_at_10"] < 1


def test_p1_oracle_categories_and_safety_metrics():
    report = evaluate_ranked_cases(CASES, fixture)
    assert {c["category"] for c in report["cases"]} == {"exact", "paraphrase", "vietnamese", "cjk", "temporal", "contradiction", "deleted", "scope_isolation", "source_revision"}
    assert report["recall_at_5"] == report["mrr_at_10"] == report["ndcg_at_10"] == 1
    assert report["citation_correctness"] == 1
    assert report["unauthorized_hit_rate"] == report["deleted_hit_rate"] == report["stale_hit_rate"] == 0
    assert report["latency_ms"]["p95"] >= 0


def test_p2_gate_rejects_small_gain_and_safety_regression(tmp_path):
    class Factory:
        deterministic_fixture = True
        def __call__(self, layers):
            def backend(query, limit=10, case=None):
                mid = next(iter(case["relevance"]))
                rows = [{"memory_id": mid, "content": "ok", "citation": case["citations"][mid]}]
                if "neural" in layers and case.get("unauthorized_ids"):
                    rows.insert(0, {"memory_id": case["unauthorized_ids"][0], "content": "leak"})
                return {"results": rows}
            return backend
    report = run_cross_layer_ablation(CASES, Factory(), output_path=tmp_path / "ablation.json")
    assert report["provider_status"] == "fixture"
    assert report["stages"][0]["admitted"]
    assert report["stages"][1]["reason"] == "insufficient_gain"
    assert any(s["reason"] == "safety_regression" for s in report["stages"])
    assert (tmp_path / "ablation.json").exists()
