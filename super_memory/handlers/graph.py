"""Graph handlers — causal chains, temporal, neighbors, spreading activation."""
from __future__ import annotations

from .. import bridge
from .base import ToolHandler, SimpleHandler
from .core import _str, _int, _num, _bool, _array, _obj, CFG


def get_graph_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_graph_health",
            "Run full graph health check: neurons, synapses, orphans, duplicates.",
            bridge.graph_health,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_graph_stats",
            "Show Layer 4 neuron/synapse/fiber counts.",
            bridge.graph_stats,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_graph_neighbors",
            "List graph neighbors for a neuron or memory id.",
            bridge.graph_neighbors,
            properties={"id": _str("Neuron ID"), "direction": _str("out/in", "out"), "limit": _int("Max results", 20), "config_path": CFG},
            required=["id"],
        ),
        SimpleHandler(
            "super_memory_graph_recall",
            "Recall cognitive fibers from Layer 4 graph.",
            bridge.graph_recall,
            properties={"query": _str("Search query"), "limit": _int("Max results", 10), "config_path": CFG},
            required=["query"],
        ),
        SimpleHandler(
            "super_memory_graph_rebuild",
            "Rebuild derived Layer 4 graph from SQLite memories.",
            bridge.graph_rebuild,
            properties={"limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_stabilize",
            "Run full graph stabilization: health check, repair orphans, dedup, prune stale.",
            bridge.stabilize,
            properties={
                "dry_run": _bool("Preview only", True),
                "prune_stale_synapses": _bool("Prune stale", True),
                "weight_threshold": _num("Prune weight threshold", 0.05),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_spreading_activation",
            "Run spreading activation for associative graph recall.",
            bridge.run_spreading_activation,
            properties={
                "query": _str("Query"),
                "anchor_neurons": _array("Anchor neuron IDs"),
                "max_hops": _int("Max hops", 3),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_spreading_activation_recall",
            "Neural-memory-style spreading activation recall through the cognitive graph.",
            bridge.spreading_activation_recall,
            properties={
                "query": _str("Query"),
                "depth": _int("Depth 0-3", 2),
                "top_k": _int("Top K", 20),
                "seed_limit": _int("Seed limit", 30),
                "config_path": CFG,
            },
            required=["query"],
        ),
        SimpleHandler(
            "nmem_recall",
            "Compatibility alias: neural-memory-style spreading activation recall.",
            bridge._nmem_recall_compat,
            properties={
                "query": _str("Query"),
                "depth": _int("Depth 0-3", 2),
                "top_k": _int("Top K", 20),
                "seed_limit": _int("Seed limit", 30),
                "config_path": CFG,
            },
            required=["query"],
        ),
        SimpleHandler(
            "super_memory_causal_chain",
            "Trace causal chain through LEADS_TO/CAUSED_BY synapses.",
            bridge.causal_chain,
            properties={
                "memory_id": _str("Memory ID"),
                "direction": _str("forward/backward", "forward"),
                "max_depth": _int("Max depth", 6),
                "config_path": CFG,
            },
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_event_sequence",
            "Get chronological event sequence within optional time window.",
            bridge.event_sequence,
            properties={
                "start": _str("Start ISO time"),
                "end": _str("End ISO time"),
                "types": _array("Event types"),
                "limit": _int("Max results", 20),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_temporal_range",
            "Get memories within a time window.",
            bridge.temporal_range,
            properties={
                "start": _str("Start ISO time"),
                "end": _str("End ISO time"),
                "limit": _int("Max results", 20),
                "config_path": CFG,
            },
            required=["start", "end"],
        ),
        SimpleHandler(
            "super_memory_topic_narrative",
            "Build coherent narrative from memories related to a topic.",
            bridge.topic_narrative,
            properties={"topic": _str("Topic"), "limit": _int("Max results", 10), "config_path": CFG},
            required=["topic"],
        ),
    ]
