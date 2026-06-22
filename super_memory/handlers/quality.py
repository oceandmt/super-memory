"""P0-P2 quality handlers — confidence, fidelity, retrieval, reranker, priming, etc."""
from __future__ import annotations

from .. import bridge
from .base import ToolHandler, SimpleHandler
from .core import _str, _int, _num, _bool, _array, _obj, CFG


def get_quality_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_confidence",
            "Compute unified confidence score for recall results.",
            bridge.compute_confidence,
            properties={
                "retrieval_score": _num("Retrieval score", 0.5),
                "sufficiency_confidence": _num("Sufficiency confidence", 0.5),
                "quality_score": _num("Quality score", 5.0),
                "fidelity_layer": _str("Fidelity layer", "detail"),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_fidelity",
            "Extract single-sentence essence and classify fidelity layer from content.",
            bridge.fidelity_extract,
            properties={"content": _str("Memory content")},
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_retrieval_pipeline",
            "Run full composable retrieval pipeline: parse → expand → rerank → confidence → format.",
            bridge.retrieval_pipeline,
            properties={"query": _str("Query string"), "limit": _int("Max results", 10), "config_path": CFG},
            required=["query"],
        ),
        SimpleHandler(
            "super_memory_rerank",
            "Rerank recall candidates using hybrid BM25 + semantic + CrossEncoder fusion.",
            bridge.rerank,
            properties={
                "query": _str("Query string"),
                "candidates": _array("Candidates", {"items": {"type": "object"}}),
                "config_path": CFG,
            },
            required=["query", "candidates"],
        ),
        SimpleHandler(
            "super_memory_quality_score",
            "Run quality assessment on memory content — fidelity, sufficiency, importance.",
            bridge.quality_score,
            properties={"content": _str("Content"), "memory_type": _str("Type", "context")},
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_priming_boosts",
            "Get priming boost multipliers for neurons in a session.",
            bridge.get_priming_boosts,
            properties={"session_id": _str("Session ID"), "neuron_ids": _array("Neuron IDs"), "config_path": CFG},
            required=["session_id", "neuron_ids"],
        ),
        SimpleHandler(
            "super_memory_preference_detect",
            "Analyze memory content for preference signals.",
            bridge.preference_detect,
            properties={"content": _str("Content"), "memory_type": _str("Type", ""), "config_path": CFG},
            required=["content"],
        ),
        # P1: Hippocampal Replay
        SimpleHandler(
            "super_memory_hippocampal_replay",
            "Run hippocampal replay consolidation: strengthen synapses from recent patterns.",
            bridge.run_hippocampal_replay,
            properties={"config_path": CFG, "dry_run": _bool("Preview only", True)},
        ),
        # P1: Pipeline Steps
        SimpleHandler(
            "super_memory_pipeline_steps_run",
            "Run selected pipeline steps as a composed pipeline.",
            bridge.pipeline_steps_run,
            properties={
                "query": _str("Query string"),
                "step_names": _array("Step names to run"),
                "limit": _int("Max results", 10),
                "config_path": CFG,
            },
            required=["query"],
        ),
        # P1: Storage Mixins
        SimpleHandler(
            "super_memory_storage_mixin_query",
            "Query storage using mixins: tag_frequencies, memories_by_tag, high_priority, recent, etc.",
            bridge.storage_mixin_query,
            properties={
                "action": _str("Query action", "tag_frequencies"),
                "tag": _str("Tag filter", ""),
                "tags": _array("Tags list"),
                "min_priority": _int("Min priority", 7),
                "hours": _int("Time window hours", 24),
                "limit": _int("Max results", 50),
                "config_path": CFG,
            },
        ),
        # P2: Schema Assimilation
        SimpleHandler(
            "super_memory_schema_assimilation",
            "Run schema assimilation analysis: detect patterns from recent memories.",
            bridge.run_schema_assimilation,
            properties={"config_path": CFG, "dry_run": _bool("Preview only", True)},
        ),
        SimpleHandler(
            "super_memory_schema_match",
            "Match content against registered schemas.",
            bridge.schema_match,
            properties={"content": _str("Content to match"), "config_path": CFG},
            required=["content"],
        ),
        # P5: Memory Pollution Report
        SimpleHandler(
            "super_memory_memory_pollution_report",
            "Memory pollution and quality report.",
            bridge.memory_pollution_report,
            properties={"config_path": CFG},
        ),
        # P2: Spaced Repetition
        SimpleHandler(
            "super_memory_spaced_repetition_due",
            "Get items due for review with SM-2 retention estimates.",
            bridge.spaced_repetition_get_due,
            properties={"limit": _int("Max items", 50), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_spaced_repetition_review",
            "Record a spaced repetition review grade (SM-2 0-5).",
            bridge.spaced_repetition_review,
            properties={"memory_id": _str("Memory ID"), "grade": _int("SM-2 grade 0-5"), "config_path": CFG},
            required=["memory_id", "grade"],
        ),
        SimpleHandler(
            "super_memory_spaced_repetition_stats",
            "Get spaced repetition statistics.",
            bridge.spaced_repetition_stats,
            properties={"config_path": CFG},
        ),
        # P2: Token Budget
        SimpleHandler(
            "super_memory_token_budget_estimate",
            "Estimate token count for text.",
            bridge.token_budget_estimate,
            properties={"text": _str("Text to estimate")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_token_budget_select",
            "Select value-dense memories within token budget.",
            bridge.token_budget_select,
            properties={
                "memories": _array("Memories", {"items": {"type": "object"}}),
                "budget_tokens": _int("Budget in tokens", 3000),
                "min_items": _int("Min items", 1),
                "config_path": CFG,
            },
            required=["memories"],
        ),
        # P2: Query Expander
        SimpleHandler(
            "super_memory_query_expand",
            "Expand query with synonyms, graph neighbors, and embedding terms.",
            bridge.query_expand,
            properties={"query": _str("Query to expand"), "config_path": CFG},
            required=["query"],
        ),
    ]
