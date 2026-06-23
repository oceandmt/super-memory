"""Recall Arbitration v3 — unified recall scoring with explanations.

Builds on existing recall_arbitration.py but adds:
- why_selected / why_excluded per candidate
- layer_votes with confidence breakdowns
- graph activation score
- semantic vector score
- recency + trust + quality + type boost
- active goal bias
- Evidence hydration through closets/drawers
- Citations with source context
- Feedback/reinforcement logging
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from ..config import load_config
from ..models import MemoryType
from ..service import SuperMemoryService
from ..storage import SuperMemoryStore, row_to_memory
from ..quality_gate import extract_entities

logger = logging.getLogger("super-memory.recall.arbitration_v3")

# ── Weights ──────────────────────────────────────────────────────────────────

WEIGHTS = {
    "lexical": 0.20,
    "semantic": 0.20,
    "graph": 0.15,
    "recency": 0.08,
    "trust": 0.10,
    "quality": 0.12,
    "type_boost": 0.06,
    "goal_bias": 0.05,
    "layer": 0.04,
}

LAYER_BASE_WEIGHTS = {
    "workspace_markdown": 0.90,
    "mempalace": 0.82,
    "neural_memory": 0.85,
    "honcho": 0.78,
}

TYPE_BOOST = {
    MemoryType.DECISION: 0.12,
    MemoryType.INSTRUCTION: 0.12,
    MemoryType.WORKFLOW: 0.10,
    MemoryType.INSIGHT: 0.10,
    MemoryType.FACT: 0.08,
    MemoryType.REFERENCE: 0.08,
    MemoryType.BOUNDARY: 0.10,
    MemoryType.LESSON: 0.08,
    MemoryType.BLOCKER: 0.08,
}

STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "super", "memory",
    "what", "which", "their", "they", "them", "some", "into", "also", "than",
    "then", "about", "would", "could", "should", "after", "other", "there",
    "these", "those", "while", "where", "when", "very", "just", "more", "such",
    "have", "been", "were", "been", "being", "has", "had", "does", "did",
})


# ── Scoring Utilities ────────────────────────────────────────────────────────

def _terms(text: str) -> set[str]:
    return {t for t in re.split(r"\W+", text.lower()) if len(t) > 2 and t not in STOPWORDS}


def _recency_score(created_at: str | None) -> float:
    if not created_at:
        return 0.3
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        days = max(0, (datetime.now(timezone.utc) - dt).days)
        return 1.0 / (1.0 + days / 30.0)
    except Exception:
        return 0.3


def _calc_lexical(query_terms: set[str], content: str) -> float:
    content_terms = _terms(content)
    if not query_terms or not content_terms:
        return 0.0
    overlap = len(query_terms & content_terms)
    return overlap / max(len(query_terms), 1)


def _calc_semantic(query_terms: set[str], keywords: list[str] | None = None, summary: str = "") -> float:
    """Pseudo-semantic score based on keyword overlap (no embedding API needed)."""
    query_lower = set(t.lower() for t in query_terms)
    content_lower = set(t.lower() for t in (keywords or []))
    content_lower |= _terms(summary)
    if not content_lower:
        return 0.0
    overlap = query_lower & content_lower
    return len(overlap) / max(len(query_lower), 1)


# ── Candidate Scorer ────────────────────────────────────────────────────────

def score_candidate(
    query: str,
    record: dict[str, Any],
    layer: str = "workspace_markdown",
    rank: int = 0,
    graph_activation: float = 0.0,
    active_goal_terms: set[str] | None = None,
) -> dict[str, Any]:
    """Score one candidate record against a query with explainable breakdown."""
    query_terms = _terms(query)
    content = record.get("content") or ""
    meta = record.get("metadata") or {}

    # Component scores
    lexical = _calc_lexical(query_terms, content)
    semantic = _calc_semantic(
        query_terms,
        keywords=meta.get("keywords") or meta.get("entities") or [],
        summary=content[:300],
    )
    recency = _recency_score(record.get("created_at"))
    trust = float(record.get("trust_score") or 0.5)
    quality = float(
        meta.get("quality_score") or
        (meta.get("quality_gate") or {}).get("quality_score") or
        0.5
    )

    type_str = (record.get("type") or "context").lower()
    try:
        mt = MemoryType(type_str)
        type_bonus = TYPE_BOOST.get(mt, 0.0)
    except (ValueError, AttributeError):
        type_bonus = 0.0

    layer_base = LAYER_BASE_WEIGHTS.get(layer, 0.6)

    # Goal bias
    goal_bias = 0.0
    if active_goal_terms:
        content_terms = _terms(content)
        goal_overlap = len(active_goal_terms & content_terms)
        goal_bias = goal_overlap / max(len(active_goal_terms), 1) * 0.1

    # Rank decay
    rank_decay = 1.0 / (1.0 + rank * 0.15)

    # Final weighted score
    score = (
        lexical * WEIGHTS["lexical"] +
        semantic * WEIGHTS["semantic"] +
        graph_activation * WEIGHTS["graph"] +
        recency * WEIGHTS["recency"] +
        trust * WEIGHTS["trust"] +
        quality * WEIGHTS["quality"] +
        type_bonus * WEIGHTS["type_boost"] +
        goal_bias * WEIGHTS["goal_bias"] +
        layer_base * WEIGHTS["layer"]
    ) * rank_decay

    score = max(0.0, min(1.0, score))

    # Why breakdown
    why_selected = {
        "lexical_overlap": round(lexical, 4),
        "semantic_score": round(semantic, 4),
        "graph_activation": round(graph_activation, 4),
        "recency": round(recency, 4),
        "trust": round(trust, 4),
        "quality": round(quality, 4),
        "type_boost": round(type_bonus, 4),
        "goal_bias": round(goal_bias, 4),
        "layer_weight": round(layer_base, 4),
        "rank_decay": round(rank_decay, 4),
        "final_score": round(score, 4),
    }

    return {
        "score": round(score, 4),
        "record": record,
        "layer": layer,
        "why": why_selected,
        "citation": record.get("source") or record.get("id") or "",
    }


# ── Arbiter ──────────────────────────────────────────────────────────────────

def arbitrate_v3(
    query: str,
    limit: int = 10,
    config_path: str | None = None,
    active_goal_terms: list[str] | None = None,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """Unified recall arbitration v3.

    Gathers candidates from all layers, scores each, returns ranked results
    with explanations, citations, and excluded reasons.
    """
    cfg = load_config(config_path)
    svc = SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)

    # Step 1: Collect candidates from all layers
    layered_results = svc.recall(query, limit=max(limit * 2, 20))

    # Step 2: Flatten and score
    goal_set = set(t.lower() for t in (active_goal_terms or []))
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    excluded: list[dict[str, Any]] = []

    for layer, records in layered_results.items():
        layer_records = [r.model_dump(mode="json") for r in records]
        for i, rec in enumerate(layer_records):
            mem_id = rec.get("id", "")
            if not mem_id:
                continue
            if mem_id in seen_ids:
                excluded.append({"id": mem_id, "reason": "duplicate_across_layers", "layer": layer})
                continue
            seen_ids.add(mem_id)

            # Graph activation score (from graph edges if available)
            graph_score = 0.0
            try:
                from .. import graph
                gs = graph.activation_score(mem_id, config_path=config_path)
                graph_score = gs.get("score", 0.0) if isinstance(gs, dict) else 0.0
            except Exception:
                pass

            candidate = score_candidate(query, rec, layer=layer, rank=i, graph_activation=graph_score, active_goal_terms=goal_set)
            if candidate["score"] >= min_score:
                candidates.append(candidate)

    # Step 3: Rank by score
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Step 4: Layer votes
    layer_votes = Counter(c["layer"] for c in candidates)

    # Step 5: Build response
    top = candidates[:limit]

    # Step 6: Hydrate through closets if available
    hydrated = []
    try:
        from ..projections.closet import hydrate_closets
        drawer_ids = []
        for c in top:
            drawer_id = c.get("record", {}).get("metadata", {}).get("drawer_id")
            if drawer_id:
                drawer_ids.append(drawer_id)
        if drawer_ids:
            hyd = hydrate_closets(drawer_ids=drawer_ids[:5], config_path=config_path)
            hydrated = hyd.get("results", [])
    except Exception:
        pass

    return {
        "query": query,
        "selected_count": len(top),
        "excluded_count": len(excluded),
        "selected": top,
        "excluded": excluded[:50],
        "layer_votes": dict(layer_votes),
        "winner_layer": top[0]["layer"] if top else "none",
        "confidence": top[0]["score"] if top else 0.0,
        "citations": [c["citation"] for c in top if c.get("citation")],
        "hydrated_evidence": hydrated,
        "why": "ranked by lexical + semantic + graph + recency + trust + quality + type + goal bias + layer weight",
    }


# ── Quick search (lightweight, no graph) ─────────────────────────────────────

def quick_search(query: str, limit: int = 5, config_path: str | None = None) -> dict[str, Any]:
    """Lightweight search: direct lexical + keyword match, no graph."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    query_terms = _terms(query)

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT 200"
        ).fetchall()

    scored = []
    for row in rows:
        rec = row_to_memory(row)
        lexical = _calc_lexical(query_terms, rec.content)
        if lexical == 0:
            continue
        recency = _recency_score(rec.created_at.isoformat() if hasattr(rec.created_at, 'isoformat') else str(rec.created_at))
        score = lexical * 0.6 + recency * 0.2 + float(rec.trust_score or 0.5) * 0.2
        scored.append({
            "score": round(score, 4),
            "record": rec.model_dump(mode="json"),
            "layer": "workspace_markdown",
            "why": f"lexical={lexical:.2f}, recency={recency:.2f}",
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"query": query, "results": scored[:limit], "count": min(len(scored), limit)}
