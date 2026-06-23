"""Retrieval pipeline — composable recall orchestration.

Orchestrates the full recall flow:
1. **Parse** — understand query intent and depth
2. **Expand** — enrich query via graph relationships
3. **Activate** — run spreading activation through the cognitive graph
4. **Fuse** — combine multiple retrieval strategies with score fusion
5. **Score** — compute unified confidence for each result
6. **Format** — prepare context for LLM injection

Each step is optional and independently replaceable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable

from .confidence import (
    ConfidenceScore,
    ConfidenceWeights,
    compute_confidence,
)
from .reranker import (
    RerankerConfig,
    FusedResult,
    fusion_rerank,
)

__all__ = [
    "RetrievalConfig",
    "RetrievalStep",
    "QueryIntent",
    "PipelineResult",
    "RetrievalPipeline",
    "query_expand",
    "format_context",
    "compute_result_confidence",
    # Micro-gap 1: Preflight
    "SearchPreflightResult",
    "resolve_search_preflight",
]

logger = logging.getLogger("super-memory.retrieval_pipeline")


# ── Depth Level ──────────────────────────────────────────────────────────────

# ── Search Preflight (Micro-gap 1: Async Search Preflight) ────────────


@dataclass
class SearchPreflightResult:
    """Result of search preflight validation.

    Mirrors memory-core manager-search-preflight.ts:
    - normalizedQuery: trimmed query
    - shouldInitializeProvider: whether embedding provider should init
    - shouldSearch: whether search should proceed
    """
    normalized_query: str = ""
    should_initialize_provider: bool = False
    should_search: bool = False
    reason: str = ""


def resolve_search_preflight(
    query: str,
    has_indexed_content: bool = True,
    has_embeddings: bool = True,
) -> SearchPreflightResult:
    """Validate search parameters before execution.

    Mirrors memory-core `resolveMemorySearchPreflight()`.
    Prevents empty queries and searches against empty indexes.

    Args:
        query: Raw query string.
        has_indexed_content: Whether any content has been indexed (FTS5).
        has_embeddings: Whether embedding vectors exist.

    Returns:
        SearchPreflightResult with validation decision.
    """
    normalized_query = query.strip() if query else ""

    if not normalized_query:
        return SearchPreflightResult(
            normalized_query="",
            should_initialize_provider=False,
            should_search=False,
            reason="empty query after trimming",
        )

    if len(normalized_query) < 2:
        return SearchPreflightResult(
            normalized_query=normalized_query,
            should_initialize_provider=False,
            should_search=False,
            reason=f"query too short ({len(normalized_query)} chars, min 2)",
        )

    if not has_indexed_content:
        return SearchPreflightResult(
            normalized_query=normalized_query,
            should_initialize_provider=False,
            should_search=False,
            reason="no indexed content available",
        )

    return SearchPreflightResult(
        normalized_query=normalized_query,
        should_initialize_provider=has_embeddings,
        should_search=True,
        reason="pass",
    )


# ── Depth Level ──────────────────────────────────────────────────────────────


class DepthLevel(IntEnum):
    """Retrieval depth, matching neural-memory semantics."""
    INSTANT = 0   # Direct lookup, 1 hop
    CONTEXT = 1   # Spreading activation, 3 hops (default)
    HABIT = 2     # Cross-time patterns, 4 hops
    DEEP = 3      # Full graph traversal


# ── Query Intent ─────────────────────────────────────────────────────────────

@dataclass
class QueryIntent:
    """Parsed query metadata for pipeline routing."""
    raw: str
    depth: DepthLevel = DepthLevel.CONTEXT
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    is_question: bool = False
    is_temporal: bool = False
    is_causal: bool = False


def parse_query(query: str, suggested_depth: DepthLevel | None = None) -> QueryIntent:
    """Parse query to extract intent signals.

    Detects:
    - Question patterns (what/how/why/when)
    - Temporal references (yesterday, last week, dates)
    - Causal queries (why, because, caused by)
    - Named entities (capitalized words)
    - Topics (non-stop-word content words)

    Args:
        query: Raw query string.
        suggested_depth: If provided, used as depth override.

    Returns:
        Parsed QueryIntent.
    """
    depth = suggested_depth if suggested_depth is not None else DepthLevel.CONTEXT
    query_lower = query.lower()

    # Question detection
    is_question = bool(re.match(r'^(what|how|why|when|where|who|which|did|does|is|are|was|were)\b', query_lower))
    is_question = is_question or query_lower.endswith("?")

    # Temporal detection
    is_temporal = bool(re.search(
        r'\b(yesterday|today|last\s+(week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|'
        r'this\s+(week|month|year)|ago|since|before|after|during|between|'
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|'
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b)',
        query_lower
    ))

    # Causal detection
    is_causal = bool(re.search(r'\b(why|because|caused\s+by|lead\s+to|result\s+in|due\s+to|triggered|root\s+cause)\b', query_lower))

    # Depth override based on intent
    if is_causal and depth < DepthLevel.CONTEXT:
        depth = DepthLevel.CONTEXT
    if is_temporal and depth < DepthLevel.CONTEXT:
        depth = DepthLevel.CONTEXT

    # Entity extraction (capitalized words)
    entities = re.findall(r'\b[A-Z][a-z]+[A-Z]\w*\b|\b[A-Z][a-z]{2,}\b|\b[A-Z]{2,}\b', query)

    # Topic extraction (words >= 3 chars, not stop words, not entities)
    stop_words = {
        "the", "and", "for", "that", "this", "with", "what", "how", "why",
        "when", "where", "who", "which", "was", "were", "have", "has", "had",
        "are", "is", "its", "not", "but", "from", "they", "you", "all", "can",
        "just", "about", "been", "very", "some", "would", "could", "should",
        "does", "did", "doing", "having", "going", "getting", "being",
    }
    words = re.findall(r"\w{3,}", query_lower)
    topics = list(set(w for w in words if w not in stop_words and w not in {e.lower() for e in entities}))

    return QueryIntent(
        raw=query,
        depth=DepthLevel(depth),
        topics=topics,
        entities=entities,
        is_question=is_question,
        is_temporal=is_temporal,
        is_causal=is_causal,
    )


# ── Query Expansion ──────────────────────────────────────────────────────────

def query_expand(
    query: str,
    intent: QueryIntent | None = None,
    graph_context: dict[str, list[str]] | None = None,
) -> tuple[str, list[str]]:
    """Expand query with graph-derived synonyms and related terms.

    For "python deployment", may expand to "python django fastapi deployment".
    Uses graph_context if provided (e.g. co-occurring terms from graph edges).

    Args:
        query: Original query.
        intent: Parsed QueryIntent (used for entity boost).
        graph_context: Dict of {term: [related_terms]} from graph relationships.

    Returns:
        Tuple of (expanded_query, expansion_terms_list).
    """
    if not graph_context:
        return query, []

    expansion_terms: set[str] = set()
    query_lower = query.lower()
    query_words = set(re.findall(r"\w{3,}", query_lower))

    for term, related in graph_context.items():
        term_lower = term.lower()
        if term_lower in query_words:
            # Add related terms that aren't already in the query
            for rel in related:
                if rel.lower() not in query_words:
                    expansion_terms.add(rel)

    # Boost entities in original query
    if intent and intent.entities:
        for ent in intent.entities:
            if ent.lower() not in query_lower:
                expansion_terms.add(ent)

    if not expansion_terms:
        return query, []

    expanded = f"{query} {' '.join(sorted(expansion_terms)[:10])}"
    return expanded, sorted(expansion_terms)[:10]


# ── Context Formatting ───────────────────────────────────────────────────────

_CONTEXT_FORMAT = """{query}

Relevant memories:
{memories}"""

_MEMORY_FORMAT = "- [{score:.2f}] {content}"

_MEMORY_WITH_CONFIDENCE = "- [{score:.2f} (confidence: {confidence:.2f})] {content}"


def format_context(
    results: list[dict[str, Any]],
    query: str = "",
    include_confidence: bool = True,
    max_memories: int = 10,
    max_chars_per_memory: int = 500,
) -> str:
    """Format pipeline results into LLM-ready context string.

    Args:
        results: List of result dicts with 'score', 'content', optional 'confidence'.
        query: Original query (prepended as header).
        include_confidence: Include confidence score in each entry.
        max_memories: Max number of memories to include.
        max_chars_per_memory: Max chars per memory content.

    Returns:
        Formatted context string ready for prompt injection.
    """
    if not results:
        return ""

    memories = []
    for r in results[:max_memories]:
        content = r.get("content", "")
        if len(content) > max_chars_per_memory:
            content = content[:max_chars_per_memory] + "..."

        score = r.get("score", 0.5)
        if include_confidence and "confidence" in r:
            conf = r["confidence"]["overall"] if isinstance(r["confidence"], dict) else r["confidence"]
            memories.append(_MEMORY_WITH_CONFIDENCE.format(
                score=score, confidence=conf, content=content
            ))
        else:
            memories.append(_MEMORY_FORMAT.format(score=score, content=content))

    if not memories:
        return ""

    return _CONTEXT_FORMAT.format(query=query, memories="\n".join(memories))


# ── Result Confidence ────────────────────────────────────────────────────────

def compute_result_confidence(
    result: dict[str, Any],
    retrieval_score: float | None = None,
    quality_score_val: float | None = None,
    fidelity_layer: str = "detail",
    created_at: datetime | None = None,
    weights: ConfidenceWeights | None = None,
) -> ConfidenceScore:
    """Compute ConfidenceScore for a single pipeline result.

    Args:
        result: Pipeline result dict.
        retrieval_score: Override for retrieval score (defaults to result.get('score', 0.5)).
        quality_score_val: Quality score 0-10 (default 5.0).
        fidelity_layer: Fidelity layer classification.
        created_at: Memory creation timestamp.
        weights: Optional custom weights.

    Returns:
        ConfidenceScore for this result.
    """
    rs = retrieval_score if retrieval_score is not None else result.get("score", 0.5)
    qs = quality_score_val if quality_score_val is not None else result.get("quality_score", 5.0)
    sufficiency = result.get("sufficiency", 0.5)

    return compute_confidence(
        retrieval_score=rs,
        sufficiency_confidence=sufficiency,
        quality_score=qs,
        fidelity_layer=fidelity_layer,
        created_at=created_at,
        weights=weights,
    )


# ── Pipeline Result ──────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """Full output of the retrieval pipeline for a single query."""
    query: str
    intent: QueryIntent
    expanded_query: str
    expansion_terms: list[str]
    raw_candidates: list[dict[str, Any]]
    reranked: list[FusedResult]
    confidences: list[ConfidenceScore]
    formatted_context: str


# ── Pipeline Config ──────────────────────────────────────────────────────────

@dataclass
class RetrievalConfig:
    """Configuration for the retrieval pipeline.

    Each step can be individually enabled/disabled.
    """
    # Step flags
    enable_parse: bool = True
    enable_expand: bool = True
    enable_rerank: bool = True
    enable_confidence: bool = True
    enable_format: bool = True

    # Limits
    max_raw_candidates: int = 50
    max_formatted_memories: int = 10
    max_chars_per_memory: int = 500

    # Sub-configs
    reranker_config: RerankerConfig | None = None
    confidence_weights: ConfidenceWeights | None = None

    # Query expansion
    graph_context: dict[str, list[str]] | None = None


# ── Step Enum ────────────────────────────────────────────────────────────────

class RetrievalStep:
    """Named pipeline step constants for selective execution."""
    PARSE = "parse"
    EXPAND = "expand"
    ACTIVATE = "activate"
    FUSE = "fuse"
    SCORE = "score"
    FORMAT = "format"


# ── Pipeline ─────────────────────────────────────────────────────────────────

class RetrievalPipeline:
    """Composable retrieval pipeline with step-by-step orchestration.

    Usage::
        pipeline = RetrievalPipeline(config)
        result = pipeline.run(
            query="python deployment kubernetes",
            retrieve_fn=my_recall_function,  # Callable that returns candidates
        )
        print(result.formatted_context)
    """

    def __init__(self, config: RetrievalConfig | None = None):
        self.config = config or RetrievalConfig()

    def run(
        self,
        query: str,
        retrieve_fn: Callable[[str, int], list[dict[str, Any]]],
        suggested_depth: DepthLevel | None = None,
        limit: int = 10,
    ) -> PipelineResult:
        """Execute the full retrieval pipeline.

        Args:
            query: User query string.
            retrieve_fn: Function that performs actual retrieval.
                Signature: (query, limit) -> list[dict] with 'neuron_id', 'content' keys.
            suggested_depth: Optional depth override.
            limit: Max results requested.

        Returns:
            PipelineResult with all intermediate and final outputs.
        """
        cfg = self.config

        # Step 1: Parse
        if cfg.enable_parse:
            intent = parse_query(query, suggested_depth)
        else:
            intent = QueryIntent(raw=query)

        # Step 2: Expand
        expanded_query, expansion_terms = query, []
        if cfg.enable_expand:
            expanded_query, expansion_terms = query_expand(
                query, intent, cfg.graph_context
            )

        # Step 3: Activate (retrieve)
        raw_candidates = retrieve_fn(expanded_query, cfg.max_raw_candidates) or []

        # Step 4: Fuse (rerank)
        if cfg.enable_rerank:
            reranked = fusion_rerank(query, raw_candidates, cfg.reranker_config)
        else:
            # Simple deduplicated pass-through
            seen = set()
            reranked = []
            for c in raw_candidates[:limit]:
                nid = c.get("neuron_id", c.get("id", ""))
                if nid not in seen:
                    seen.add(nid)
                    reranked.append(FusedResult(
                        neuron_id=nid,
                        content=c.get("content", ""),
                        score=c.get("score", 0.5),
                        bm25_score=0.0,
                        semantic_score=0.0,
                        crossencoder_score=0.0,
                    ))

        # Step 5: Score (confidence)
        confidences: list[ConfidenceScore] = []
        if cfg.enable_confidence:
            for r in reranked[:limit]:
                cs = compute_result_confidence(
                    result={"score": r.score, "neuron_id": r.neuron_id},
                    retrieval_score=r.score,
                    fidelity_layer="detail",
                    weights=cfg.confidence_weights,
                )
                confidences.append(cs)

        # Step 6: Format
        formatted = ""
        if cfg.enable_format:
            combined = []
            for i, r in enumerate(reranked[:limit]):
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
                max_memories=cfg.max_formatted_memories,
                max_chars_per_memory=cfg.max_chars_per_memory,
            )

        return PipelineResult(
            query=query,
            intent=intent,
            expanded_query=expanded_query,
            expansion_terms=expansion_terms,
            raw_candidates=raw_candidates,
            reranked=reranked,
            confidences=confidences,
            formatted_context=formatted,
        )

# ── Safe wrapper ─────────────────────────────────────────────────────────────

def run_pipeline_safe(query: str, limit: int = 10, config_path: str | None = None) -> dict:
    """Safe wrapper for run_pipeline with error handling."""
    try:
        result = run_pipeline(query, limit=limit, config_path=config_path)
        return result
    except Exception as e:
        logger.error("retrieval_pipeline failed: %s", e, exc_info=True)
        return {"results": [], "error": str(e), "query": query}
