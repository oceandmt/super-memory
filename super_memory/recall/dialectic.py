"""Agentic Dialectic Mode — optional LLM-based synthesis after deterministic recall.

P2 — borrows from Honcho DialecticAgent:
1. Deterministic recall first (Recall Arbitration v3)
2. If query needs synthesis/reasoning, optionally invoke an LLM agent
3. Agent receives: query + recall results + structured tool context
4. Returns: synthesized answer with citations

This is OPTIONAL — the default recall path remains fully deterministic.
Dialectic mode is triggered by explicit query parameter or tool call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from ..config import load_config

logger = logging.getLogger("super-memory.recall.dialectic")

# ── Config ───────────────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are a memory dialectic agent for Super Memory.

You receive a user query and a set of recalled memories. Your task:
1. Synthesize the recalled evidence into a coherent answer
2. Reference specific sources (memory IDs, line numbers, file paths)
3. Note gaps, conflicts, or uncertainties in the evidence
4. Suggest what additional information would help

Rules:
- Always cite sources when making factual claims
- Distinguish between explicit evidence and inferred conclusions
- If recalled results are insufficient, say so clearly
- Keep answers concise and actionable"""


# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class DialecticTurn:
    """A single turn in the dialectic reasoning loop."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class DialecticResult:
    """Result from a dialectic reasoning session."""
    query: str
    answer: str
    sources_cited: list[dict[str, Any]]
    confidence: float
    gaps: list[str]
    turns: list[DialecticTurn]
    duration_ms: float = 0.0


# ── Dialectic Agent ─────────────────────────────────────────────────────────

class DialecticAgent:
    """Optional agent that synthesizes recall results into answers.

    Two modes:
    1. **format**: pure string formatting (no LLM needed) — suitable for simple queries
    2. **synthesize**: LLM-based reasoning — requires an available LLM API

    Usage:
        agent = DialecticAgent(config_path=...)
        result = agent.answer(query=..., recall_result=..., mode="format")
    """

    def __init__(self, config_path: str | None = None):
        self.cfg = load_config(config_path)
        self._mode_available = self._check_llm()

    def _check_llm(self) -> bool:
        """Check if LLM-based synthesis is available."""
        # Check for common env vars or config settings
        import os
        return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or self.cfg.get("llm", {}).get("api_key"))

    def answer(
        self,
        query: str,
        recall_result: dict[str, Any] | None = None,
        mode: str = "format",
        **kwargs,
    ) -> dict[str, Any]:
        """Answer a query using optional dialectic reasoning.

        Args:
            query: User query
            recall_result: Result from recall_arbitrate_v3() or similar
            mode: "format" (deterministic/rule-based) or "synthesize" (LLM-based)

        Returns:
            Answer with citations, confidence, gaps, sources
        """
        start_time = datetime.now(timezone.utc)

        if mode == "format" or not self._mode_available:
            result = self._format_answer(query, recall_result)
        elif mode == "synthesize":
            result = self._synthesize_answer(query, recall_result, **kwargs)
        else:
            result = self._format_answer(query, recall_result)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        result.duration_ms = round(duration, 1)

        return {
            "ok": True,
            "query": query,
            "answer": result.answer,
            "sources": result.sources_cited,
            "confidence": result.confidence,
            "gaps": result.gaps,
            "duration_ms": result.duration_ms,
            "mode": mode,
            "llm_available": self._mode_available,
        }

    def _format_answer(self, query: str, recall_result: dict[str, Any] | None) -> DialecticResult:
        """Deterministic format-only answer (no LLM)."""
        if not recall_result:
            return DialecticResult(
                query=query,
                answer="No recall results available to synthesize.",
                sources_cited=[],
                confidence=0.0,
                gaps=["No recall data"],
                turns=[],
            )

        selected = recall_result.get("selected", [])
        citations = recall_result.get("citations", [])
        layer_votes = recall_result.get("layer_votes", {})

        if not selected:
            return DialecticResult(
                query=query,
                answer=f"No matching memories found for: '{query}'.",
                sources_cited=[],
                confidence=0.0,
                gaps=[f"No matches for query"],
                turns=[],
            )

        # Build answer from top results
        top = selected[:3]
        lines = [f"## Results for: {query}"]
        lines.append(f"Found {len(selected)} matches across {len(layer_votes)} layers.\n")

        for i, sel in enumerate(top):
            record = sel.get("record", {})
            score = sel.get("score", 0)
            why = sel.get("why", {})
            content = (record.get("content") or "")[:300]
            mem_type = record.get("type", "context")
            source = record.get("source", "")
            mem_id = record.get("id", "")[:8] if record.get("id") else ""

            lines.append(f"### {i+1}. [{mem_type}] (score={score:.2f}) [{mem_id}]")
            lines.append(f"   Source: {source or 'unknown'}")
            if content:
                lines.append(f"   ```\n   {content}\n   ```")
            if why:
                lines.append(f"   Why: lexical={why.get('lexical_overlap',0):.2f}, semantic={why.get('semantic_score',0):.2f}, graph={why.get('graph_activation',0):.2f}, recency={why.get('recency',0):.2f}, trust={why.get('trust',0):.2f}, quality={why.get('quality',0):.2f}")
            lines.append("")

        # Citations
        if citations:
            lines.append(f"### Citations ({len(citations)})")
            for c in citations[:5]:
                lines.append(f"- {c}")

        # Layer distribution
        if layer_votes:
            lines.append(f"\n### Layer distribution")
            for layer, count in sorted(layer_votes.items(), key=lambda x: -x[1]):
                lines.append(f"- {layer}: {count}")

        # Confidence
        top_score = top[0].get("score", 0) if top else 0
        confidence = min(1.0, top_score * 1.5)

        # Gaps
        gaps = []
        if len(selected) < 3:
            gaps.append(f"Only {len(selected)} matches found")
        if not citations:
            gaps.append("No source citations available")
        if top_score < 0.5:
            gaps.append(f"Low top score ({top_score:.2f})")

        answer = "\n".join(lines)
        sources = [{"memory_id": s.get("record", {}).get("id", ""), "score": s.get("score", 0), "citation": s.get("citation", "")} for s in top]

        return DialecticResult(
            query=query,
            answer=answer,
            sources_cited=sources,
            confidence=round(confidence, 4),
            gaps=gaps,
            turns=[],
        )

    def _synthesize_answer(self, query: str, recall_result: dict[str, Any] | None, **kwargs) -> DialecticResult:
        """LLM-based synthesis (placeholder — requires external LLM API)."""
        # For now, fall back to format mode
        result = self._format_answer(query, recall_result)

        # If LLM API is available, attempt synthesis
        if self._mode_available:
            result.answer += "\n\n*[LLM synthesis mode not fully implemented — falling back to format mode]*"
            result.gaps.append("LLM synthesis not yet connected to provider")

        return result


# ── Convenience ──────────────────────────────────────────────────────────────

def dialectic_answer(
    query: str,
    recall_result: dict[str, Any] | None = None,
    mode: str = "format",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Convenience: create agent + answer in one call."""
    agent = DialecticAgent(config_path=config_path)
    return agent.answer(query=query, recall_result=recall_result, mode=mode)
