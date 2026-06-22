from __future__ import annotations
"""Super Memory: local multi-layer memory app for OpenClaw multi-agents."""

__version__ = "1.6.0"

from .models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService

# P0-P5 module exports (lazy — imported on access)
from . import (
    safety,
    dedup,
    extraction,
    embeddings,
    cache,
    sync,
    spreading_activation as spreading,
    trigger_engine as triggers,
    eternal_context,
    brain_mode,
    pipeline_integration,
    auto_deep,
    reranker,
    quality_scorer,
    priming,
    reflex_arc,
    preference_detector,
    diagnostics,
)

__all__ = [
    "MemoryRecord", "MemoryLayer", "MemoryScope", "MemoryType",
    "SuperMemoryService",
    "safety", "dedup", "extraction", "embeddings", "cache", "sync",
    "spreading", "triggers", "eternal_context", "brain_mode",
    "pipeline_integration", "auto_deep",
    "reranker", "quality_scorer", "priming", "reflex_arc",
    "preference_detector", "diagnostics",
]
