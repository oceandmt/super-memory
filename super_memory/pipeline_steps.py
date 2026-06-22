"""Pipeline Steps — extractable step handlers for the retrieval pipeline.

Provides standalone, independently callable step functions that can be
composed into custom pipelines, tested individually, or called from
external code without running the full RetrievalPipeline class.

Each step is a pure function or lightweight handler class.

Step index:
0.  Safety           — run_safety_step
1.  Parse            — parse_query (from retrieval_pipeline)
2.  Expand           — query expansion
3.  Retrieve         — raw candidate retrieval
4.  Fuse/Rerank      — hybrid score fusion
5.  Score/Confidence — confidence scoring
6.  Format           — context formatting
7.  Annotate         — freshness, priming, goal boost
8.  Filter           — tier, tag, priority filters
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .confidence import ConfidenceScore, compute_confidence, ConfidenceWeights
from .reranker import FusedResult, RerankerConfig, fusion_rerank, bm25_lexical_score
from .retrieval_pipeline import (
    DepthLevel, QueryIntent, parse_query,
    query_expand, format_context, compute_result_confidence,
)

__all__ = [
    "PipelineStep", "StepRegistry",
    "safety_step", "parse_step", "expand_step",
    "retrieve_step", "fuse_step", "score_step",
    "format_step", "annotate_step", "filter_step",
    "create_default_pipeline",
]

logger = logging.getLogger("super-memory.pipeline_steps")


# ── Step Handler Type ─────────────────────────────────────────────────────────

StepHandler = Callable[..., Any]

@dataclass
class PipelineStep:
    """Descriptor for a single pipeline step."""
    name: str
    handler: StepHandler
    description: str = ""
    enabled: bool = True
    order: int = 0


@dataclass
class StepContext:
    """Mutable context passed through pipeline steps."""
    query: str = ""
    intent: QueryIntent | None = None
    expanded_query: str = ""
    expansion_terms: list[str] = field(default_factory=list)
    raw_candidates: list[dict[str, Any]] = field(default_factory=list)
    reranked: list[FusedResult] = field(default_factory=list)
    confidences: list[ConfidenceScore] = field(default_factory=list)
    formatted_context: str = ""
    safety_result: dict[str, Any] = field(default_factory=dict)
    annotations: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_pipeline_result_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": {
                "raw": self.intent.raw if self.intent else self.query,
                "depth": int(self.intent.depth) if self.intent else 1,
                "entities": self.intent.entities if self.intent else [],
                "topics": self.intent.topics if self.intent else [],
                "is_question": self.intent.is_question if self.intent else False,
                "is_temporal": self.intent.is_temporal if self.intent else False,
                "is_causal": self.intent.is_causal if self.intent else False,
            } if self.intent else {},
            "expanded_query": self.expanded_query,
            "expansion_terms": self.expansion_terms,
            "raw_count": len(self.raw_candidates),
            "reranked_count": len(self.reranked),
            "confidences": [
                {"overall": c.overall, "retrieval": c.retrieval,
                 "content_quality": c.content_quality, "fidelity": c.fidelity,
                 "freshness": c.freshness}
                for c in self.confidences
            ] if self.confidences else [],
            "formatted_context": self.formatted_context,
            "annotations": self.annotations,
            "safety_passed": not self.safety_result.get("blocked", False),
        }


# ── Safety Step ───────────────────────────────────────────────────────────────

def safety_step(content: str, context: StepContext | None = None) -> dict[str, Any]:
    """Step 0: Run safety firewall on query content."""
    try:
        from .pipeline_integration import run_safety_firewall
        result = run_safety_firewall(content)
        if context:
            context.safety_result = result
        return result
    except Exception as e:
        logger.debug("safety step failed: %s", e)
        return {"blocked": False, "error": str(e)}


# ── Parse Step ────────────────────────────────────────────────────────────────

def parse_step(
    query: str,
    suggested_depth: DepthLevel | None = None,
    context: StepContext | None = None,
) -> QueryIntent:
    """Step 1: Parse query into structured intent."""
    intent = parse_query(query, suggested_depth)
    if context:
        context.query = query
        context.intent = intent
    return intent


# ── Expand Step ──────────────────────────────────────────────────────────────

def expand_step(
    query: str,
    intent: QueryIntent | None = None,
    graph_context: dict[str, list[str]] | None = None,
    context: StepContext | None = None,
) -> tuple[str, list[str]]:
    """Step 2: Expand query with graph-derived terms."""
    expanded, terms = query_expand(query, intent, graph_context)
    if context:
        context.expanded_query = expanded
        context.expansion_terms = terms
    return expanded, terms


# ── Retrieve Step ────────────────────────────────────────────────────────────

def retrieve_step(
    query: str,
    retrieve_fn: Callable[[str, int], list[dict[str, Any]]],
    limit: int = 50,
    context: StepContext | None = None,
) -> list[dict[str, Any]]:
    """Step 3: Retrieve raw candidates using the provided function."""
    candidates = retrieve_fn(query, limit) or []
    if context:
        context.raw_candidates = candidates
    return candidates


# ── Fuse / Rerank Step ──────────────────────────────────────────────────────

def fuse_step(
    query: str,
    candidates: list[dict[str, Any]],
    config: RerankerConfig | None = None,
    limit: int = 10,
    context: StepContext | None = None,
) -> list[FusedResult]:
    """Step 4: Rerank and fuse candidate scores."""
    reranked = fusion_rerank(query, candidates, config)[:limit]
    if context:
        context.reranked = reranked
    return reranked


# ── Score / Confidence Step ─────────────────────────────────────────────────

def score_step(
    reranked: list[FusedResult],
    weights: ConfidenceWeights | None = None,
    limit: int = 10,
    context: StepContext | None = None,
) -> list[ConfidenceScore]:
    """Step 5: Compute confidence scores for reranked results."""
    confidences = []
    for r in reranked[:limit]:
        cs = compute_confidence(
            retrieval_score=r.score,
            quality_score=5.0,
            fidelity_layer="detail",
            weights=weights,
        )
        confidences.append(cs)
    if context:
        context.confidences = confidences
    return confidences


# ── Format Step ──────────────────────────────────────────────────────────────

def format_step(
    reranked: list[FusedResult],
    confidences: list[ConfidenceScore],
    query: str = "",
    max_memories: int = 10,
    max_chars_per_memory: int = 500,
    context: StepContext | None = None,
) -> str:
    """Step 6: Format results into LLM-ready context."""
    combined = []
    for i, r in enumerate(reranked[:max_memories]):
        entry: dict[str, Any] = {
            "neuron_id": r.neuron_id,
            "content": r.content,
            "score": r.score,
        }
        if i < len(confidences):
            entry["confidence"] = {
                "overall": confidences[i].overall,
                "retrieval": confidences[i].retrieval,
                "content_quality": confidences[i].content_quality,
                "fidelity": confidences[i].fidelity,
                "freshness": confidences[i].freshness,
            }
        combined.append(entry)

    formatted = format_context(
        combined,
        query=query,
        max_memories=max_memories,
        max_chars_per_memory=max_chars_per_memory,
    )
    if context:
        context.formatted_context = formatted
    return formatted


# ── Annotate Step ────────────────────────────────────────────────────────────

def annotate_step(
    results: list[dict[str, Any]],
    session_id: str = "",
    context: StepContext | None = None,
) -> list[dict[str, Any]]:
    """Step 7: Annotate results with freshness, priming, and goal boosts."""
    try:
        # Freshness
        from .pipeline_integration import annotate_freshness
        results = annotate_freshness(results)

        # Priming boost
        if session_id:
            from .priming import apply_priming_to_recall
            results = apply_priming_to_recall(session_id, results)

        # Goal boost
        try:
            from .goals import compute_goal_boost
            for r in results:
                tags = r.get("tags", r.get("_tags", []))
                content = r.get("content", "")
                goal_boost = compute_goal_boost(tags, content)
                r["_goal_boost"] = goal_boost
        except Exception:
            pass
    except Exception as e:
        logger.debug("annotate step failed: %s", e)

    if context:
        context.annotations = [
            {k: v for k, v in r.items() if k.startswith("_")}
            for r in results
        ]
    return results


# ── Filter Step ──────────────────────────────────────────────────────────────

def filter_step(
    results: list[dict[str, Any]],
    min_score: float = 0.0,
    tier: str | None = None,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Step 8: Filter results by score threshold, tier, or tags."""
    filtered = results

    # Score filter
    if min_score > 0:
        filtered = [r for r in filtered if r.get("score", 0) >= min_score]

    # Tier filter
    if tier:
        filtered = [r for r in filtered if r.get("tier", r.get("_tier")) == tier]

    # Tag include filter
    if include_tags:
        include_lower = {t.lower() for t in include_tags}
        filtered = [
            r for r in filtered
            if include_lower & {t.lower() for t in (r.get("tags", r.get("_tags", [])))}
        ]

    # Tag exclude filter
    if exclude_tags:
        exclude_lower = {t.lower() for t in exclude_tags}
        filtered = [
            r for r in filtered
            if not (exclude_lower & {t.lower() for t in (r.get("tags", r.get("_tags", [])))})
        ]

    return filtered[:max_results]


# ── Step Registry ────────────────────────────────────────────────────────────

class StepRegistry:
    """Registry of available pipeline steps for dynamic composition."""

    def __init__(self):
        self._steps: dict[str, PipelineStep] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(PipelineStep("safety", safety_step, "Safety firewall", order=0))
        self.register(PipelineStep("parse", parse_step, "Query parsing", order=1))
        self.register(PipelineStep("expand", expand_step, "Query expansion", order=2))
        self.register(PipelineStep("retrieve", retrieve_step, "Raw retrieval", order=3))
        self.register(PipelineStep("fuse", fuse_step, "Score fusion rerank", order=4))
        self.register(PipelineStep("score", score_step, "Confidence scoring", order=5))
        self.register(PipelineStep("format", format_step, "Context formatting", order=6))
        self.register(PipelineStep("annotate", annotate_step, "Annotation", order=7))
        self.register(PipelineStep("filter", filter_step, "Result filtering", order=8))

    def register(self, step: PipelineStep) -> None:
        self._steps[step.name] = step

    def get(self, name: str) -> PipelineStep | None:
        return self._steps.get(name)

    def list(self) -> list[PipelineStep]:
        return sorted(self._steps.values(), key=lambda s: s.order)

    def names(self) -> list[str]:
        return [s.name for s in self.list()]

    def enable(self, name: str) -> bool:
        step = self._steps.get(name)
        if step:
            step.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        step = self._steps.get(name)
        if step:
            step.enabled = False
            return True
        return False


# ── Factory ──────────────────────────────────────────────────────────────────

def create_default_pipeline(
    step_names: list[str] | None = None,
) -> tuple[StepRegistry, list[str]]:
    """Create a default pipeline configuration.

    Args:
        step_names: List of step names to include (None for all default).

    Returns:
        Tuple of (StepRegistry, list of enabled step names in order).
    """
    registry = StepRegistry()
    if step_names is None:
        step_names = ["parse", "expand", "retrieve", "fuse", "score", "format"]
    return registry, step_names
