"""Cross-layer recall ablation and safety-preserving admission gate."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .recall_benchmark import evaluate_ranked_cases

LAYER_STAGES = (("l1",), ("l1", "honcho"), ("l1", "honcho", "mempalace"),
                ("l1", "honcho", "mempalace", "neural"),
                ("l1", "honcho", "mempalace", "neural", "vector"))
SAFETY_KEYS = ("unauthorized_hit_rate", "deleted_hit_rate", "stale_hit_rate")


def run_cross_layer_ablation(cases: list[dict[str, Any]], backend_factory: Callable[[tuple[str, ...]], Callable[..., dict[str, Any]]], *, output_path: str | Path | None = None) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for layers in LAYER_STAGES:
        metrics = evaluate_ranked_cases(cases, backend_factory(layers))
        if previous is None:
            admitted, reason = True, "baseline"
        else:
            ndcg_gain = metrics["ndcg_at_10"] - previous["metrics"]["ndcg_at_10"]
            recall_gain = metrics["recall_at_5"] - previous["metrics"]["recall_at_5"]
            safe = all(metrics[key] <= previous["metrics"][key] for key in SAFETY_KEYS)
            admitted = safe and (ndcg_gain >= .03 or recall_gain >= .05)
            reason = "quality_gain" if admitted else ("safety_regression" if not safe else "insufficient_gain")
        stage = {"name": "full_fusion" if layers == LAYER_STAGES[-1] else "+".join(layers),
                 "layers": list(layers), "admitted": admitted, "reason": reason, "metrics": metrics}
        stages.append(stage)
        if admitted:
            previous = stage
    report = {"policy": {"min_ndcg_gain": .03, "min_recall_at_5_gain": .05, "safety_regression_allowed": False},
              "provider_status": "fixture" if getattr(backend_factory, "deterministic_fixture", False) else "runtime_backend_unverified",
              "stages": stages, "admitted_layers": stages[-1]["layers"] if stages[-1]["admitted"] else previous["layers"]}
    if output_path:
        path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
