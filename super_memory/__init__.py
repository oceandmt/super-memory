from __future__ import annotations
"""Super Memory: local multi-layer memory app for OpenClaw multi-agents."""

__version__ = "2.1.1"

from .models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService

# P0-P5 module exports (lazy — imported on access)
from . import (
    # P0 — Critical (Safety & Recall Quality)
    safety,
    dedup,
    confidence,
    fidelity,
    retrieval_pipeline,
    reranker,
    spreading_activation as spreading,
    dream_engine,

    # P1 — Core Infrastructure
    extraction,
    embeddings,
    cache,
    trigger_engine as triggers,
    eternal_context,
    brain_mode,
    pipeline_integration,
    hippocampal_replay,
    pipeline_steps,
    storage_mixins,
    quality_scorer,
    priming,
    reflex_arc,

    # P0 — Quality & Arbitration
    quality_gate,
    recall_arbitration,
    self_training,

    # P1 — Semantic
    semantic_taxonomy,

    # P2 — Workflows & Integration
    preference_detector,
    schema_assimilation,
    spaced_repetition,
    token_budget,
    query_expander,
    workflows,

    # P3 — Sync Foundation & Observability
    sync,
    telemetry,
    agent_isolation,

    # P0 — Memory-Slot Contract
    cooldown,
    session_index,

    # P1 — Search Quality
    mmr,
    temporal_decay,
    hybrid_search,
    session_visibility,

    # P2 — Embedding Providers
    embeddings_registry,

    # P3 — Infrastructure
    rem,
    watcher,
    flush_plan,
    reindex,

    # Remaining Gaps
    index_identity,
    self_heal,
    prompt_section,
    narrative,
    rem_evidence,
    qmd,

    # Dev Tools
    auto_deep,
    diagnostics,
)

__all__ = [
    "MemoryRecord", "MemoryLayer", "MemoryScope", "MemoryType",
    "SuperMemoryService",
    # P0
    "safety", "dedup", "confidence", "fidelity", "retrieval_pipeline",
    "reranker", "spreading", "dream_engine",
    # P1
    "extraction", "embeddings", "cache", "triggers", "eternal_context",
    "brain_mode", "pipeline_integration", "hippocampal_replay",
    "pipeline_steps", "storage_mixins", "quality_scorer", "priming", "reflex_arc",
    # P0-P2
    "quality_gate", "recall_arbitration", "self_training",
    "semantic_taxonomy", "workflows",
    # P2
    "preference_detector", "schema_assimilation", "spaced_repetition",
    "token_budget", "query_expander",
    # P3
    "sync", "telemetry", "agent_isolation",
    # P0
    "cooldown", "session_index",
    # P1
    "mmr", "temporal_decay", "hybrid_search", "session_visibility",
    # P2
    "embeddings_registry",
    # P3
    "rem", "watcher", "flush_plan", "reindex",
    # Remaining Gaps
    "index_identity", "self_heal", "prompt_section", "narrative", "rem_evidence", "qmd",
    # Dev
    "auto_deep", "diagnostics",
]
