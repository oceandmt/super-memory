from __future__ import annotations
"""Super Memory: local multi-layer memory app for OpenClaw multi-agents."""

__version__ = "1.7.0"

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

    # P2 — Workflows & Integration
    preference_detector,
    schema_assimilation,
    spaced_repetition,
    token_budget,
    query_expander,

    # P3 — Sync Foundation
    sync,

    # Dev Tools
    auto_deep,
    diagnostics,
)

__all__ = [
    "MemoryRecord", "MemoryLayer", "MemoryScope", "MemoryType",
    "SuperMemoryService",
    # P0
    "safety", "dedup", "confidence", "fidelity", "retrieval_pipeline",
    "reranker", "spreading",
    # P1
    "extraction", "embeddings", "cache", "triggers", "eternal_context",
    "brain_mode", "pipeline_integration", "hippocampal_replay",
    "pipeline_steps", "storage_mixins", "quality_scorer", "priming", "reflex_arc",
    # P2
    "preference_detector", "schema_assimilation", "spaced_repetition",
    "token_budget", "query_expander",
    # P3
    "sync",
    # Dev
    "auto_deep", "diagnostics",
]
