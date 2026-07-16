"""Release/readiness gate for the meaningful-write benchmark."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .semantic_quality_benchmark import benchmark

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "tests/fixtures/meaningfulness/corpus.jsonl"
DEFAULT_ARTIFACT = ROOT / "audit-artifacts/semantic-enhancement/metrics.json"


def semantic_release_gate(corpus_path: str | Path = DEFAULT_CORPUS,
                          artifact_path: str | Path = DEFAULT_ARTIFACT) -> dict[str, Any]:
    report = benchmark(corpus_path, artifact_path)
    primary = report["primary"]
    return {"name": "semantic_meaningfulness", "ready": report["passed"],
            "artifact": str(artifact_path), "metrics": {
                "precision": primary["useful_write_precision"],
                "recall": primary["useful_write_recall"],
                "noise_promotion_rate": primary["noise_promotion_rate"],
                "unapproved_generated_promotions": primary["unapproved_generated_promotions"]},
            "failures": report["actionable_false_cases"]}
