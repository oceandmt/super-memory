from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import bridge
from .config import load_config
from .cross_agent import CrossAgentTools
from .hybrid_recall import HybridRecall


def benchmark_cross_agent(config_path: str | Path | None = None, limit: int = 5) -> dict[str, Any]:
    """Small deterministic benchmark for cross-agent/session recall latency."""
    cfg = load_config(config_path)
    cases = [
        {"query": "canonical markdown", "agent_id": "lucas"},
        {"query": "admin MCP profile", "agent_id": "alex"},
    ]
    ca = CrossAgentTools(cfg)
    hr = HybridRecall(cfg)
    results: list[dict[str, Any]] = []
    for case in cases:
        start = time.perf_counter()
        recall = ca.cross_agent_recall(case["query"], case["agent_id"], limit)
        elapsed_ms = (time.perf_counter() - start) * 1000
        results.append(
            {
                "kind": "cross_agent_recall",
                "query": case["query"],
                "agent_id": case["agent_id"],
                "count": recall.get("count", 0),
                "latency_ms": round(elapsed_ms, 3),
            }
        )
    start = time.perf_counter()
    hybrid = hr.cross_scope_recall("canonical markdown", agent_scope="all", session_scope="all", source_layers=["markdown", "honcho", "mempalace", "graph"], limit=limit)
    results.append(
        {
            "kind": "cross_scope_recall",
            "query": "canonical markdown",
            "count": hybrid.get("count", 0),
            "latency_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    )
    avg_latency = sum(r["latency_ms"] for r in results) / len(results) if results else 0.0
    health = bridge.cross_layer_health(config_path=str(config_path) if config_path else None)
    return {
        "ok": all(r["count"] >= 0 for r in results) and health.get("verdict") != "fail",
        "results": results,
        "avg_latency_ms": round(avg_latency, 3),
        "cross_layer_verdict": health.get("verdict"),
    }
