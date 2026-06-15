from __future__ import annotations

import argparse
import json
import random
import statistics
import tempfile
import time
from pathlib import Path

import yaml

from super_memory.graph import _hash, _now, _store, _upsert_neuron, _upsert_synapse, spreading_activation

TOPICS = [
    "auth", "database", "telegram", "discord", "openclaw", "memory",
    "trading", "gold", "facebook", "content", "scheduler", "security",
]


def make_config(root: Path) -> Path:
    cfg_path = root / "super-memory.yaml"
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    cfg = {
        "workspace_root": str(workspace),
        "sqlite_path": str(root / "super-memory.sqlite3"),
        "require_canonical_first": True,
    }
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return cfg_path


def seed_graph(size: int, config_path: str) -> dict[str, float]:
    store = _store(config_path)
    t0 = time.perf_counter()
    with store.connect() as conn:
        now = _now()
        for i in range(size):
            topic = TOPICS[i % len(TOPICS)]
            neighbor = TOPICS[(i + 3) % len(TOPICS)]
            content = (
                f"Synthetic memory {i}: {topic} workflow decision caused by {neighbor} incident. "
                f"Project super-memory preserves provenance recall path benchmark latency."
            )
            memory_id = f"bench-{i}"
            anchor = _upsert_neuron(conn, kind="memory", content=content[:500], source_memory_id=memory_id, confidence=0.8)
            topic_n = _upsert_neuron(conn, kind="entity", content=topic, confidence=0.9)
            neighbor_n = _upsert_neuron(conn, kind="entity", content=neighbor, confidence=0.8)
            project_n = _upsert_neuron(conn, kind="project", content="super-memory-benchmark", confidence=0.9)
            synapses = [
                _upsert_synapse(conn, source=anchor, target=topic_n, relation="mentions", weight=0.9, confidence=0.9),
                _upsert_synapse(conn, source=anchor, target=neighbor_n, relation="caused_by", weight=0.75, confidence=0.8),
                _upsert_synapse(conn, source=anchor, target=project_n, relation="in_project", weight=0.8, confidence=0.9),
                _upsert_synapse(conn, source=topic_n, target=neighbor_n, relation="related_to", weight=0.55, confidence=0.7),
            ]
            fiber_id = f"f:{memory_id}"
            neuron_ids = [anchor, topic_n, neighbor_n, project_n]
            conn.execute(
                """
                INSERT OR REPLACE INTO cognitive_fibers
                (id, anchor_neuron_id, neuron_ids_json, synapse_ids_json, pathway_json, salience, coherence, conductivity, frequency, summary, tags_json, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fiber_id,
                    anchor,
                    json.dumps(neuron_ids),
                    json.dumps(synapses),
                    json.dumps(neuron_ids),
                    0.8,
                    0.7,
                    1.0,
                    0,
                    content[:280],
                    json.dumps([topic, "benchmark"]),
                    json.dumps({"memory_id": memory_id, "benchmark": True}),
                    now,
                    now,
                ),
            )
    return {"seed_ms": round((time.perf_counter() - t0) * 1000, 2)}


def run_benchmark(size: int, queries: int) -> dict[str, object]:
    random.seed(42)
    with tempfile.TemporaryDirectory(prefix=f"super-memory-bench-{size}-") as td:
        root = Path(td)
        cfg_path = str(make_config(root))
        seed_stats = seed_graph(size, cfg_path)

        recall_latencies: list[float] = []
        activated_counts: list[int] = []
        hit_count = 0
        for _ in range(queries):
            q = random.choice(TOPICS)
            rt0 = time.perf_counter()
            result = spreading_activation(q, depth=2, top_k=10, seed_limit=30, config_path=cfg_path)
            recall_latencies.append((time.perf_counter() - rt0) * 1000)
            activated_counts.append(int(result.get("total_activated", 0)))
            if result.get("results"):
                hit_count += 1

        recall_latencies_sorted = sorted(recall_latencies)
        p95_index = min(len(recall_latencies_sorted) - 1, int(len(recall_latencies_sorted) * 0.95))
        return {
            "size": size,
            "queries": queries,
            "seed_total_ms": seed_stats["seed_ms"],
            "seed_per_memory_ms": round(seed_stats["seed_ms"] / size, 4),
            "recall_p50_ms": round(statistics.median(recall_latencies), 4),
            "recall_p95_ms": round(recall_latencies_sorted[p95_index], 4),
            "recall_avg_ms": round(statistics.mean(recall_latencies), 4),
            "hit_rate": round(hit_count / queries, 4),
            "avg_activated": round(statistics.mean(activated_counts), 2),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Super-Memory spreading activation recall")
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000])
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--output", default="docs/SPREADING_ACTIVATION_BENCHMARK.json")
    args = parser.parse_args()

    results = [run_benchmark(size, args.queries) for size in args.sizes]
    out = {"benchmark": "spreading_activation", "mode": "synthetic_layer4_graph", "results": results}
    Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
