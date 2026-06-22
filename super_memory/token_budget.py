"""Token Budget — manage context window allocation for memory recall.

Provides budget-aware recall that selects the most value-dense memories
to fit within a token limit. Core concepts:

1. **Value-per-token** — rank memories by (relevance / token_cost)
2. **Budget tiers** — allocate tokens across categories (high-priority, recent, related)
3. **Overflow handling** — truncate/compress when over budget
4. **Budget negotiation** — reserve space for system prompt, query, results

Uses approximate token counting (4 chars ≈ 1 token for English text).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "TokenBudgetConfig", "TokenBudgetManager",
    "estimate_tokens", "truncate_to_budget",
    "select_value_dense", "compute_budget_allocation",
    "format_within_budget",
]

logger = logging.getLogger("super-memory.token_budget")

# Approximate: 4 characters per token for English
CHARS_PER_TOKEN = 4.0

# Token costs for fixed overhead
OVERHEAD_TOKENS = {
    "system_prompt": 200,
    "query": 50,
    "format_wrapper": 30,
    "per_memory_overhead": 15,  # "- [score] " prefix
}


@dataclass
class TokenBudgetConfig:
    """Configuration for token budget management.

    Attributes:
        max_context_tokens: Total context window limit.
        reserved_system: Tokens reserved for system prompt.
        reserved_query: Tokens reserved for the query/instruction.
        max_memories_tokens: Max tokens allocated to memories.
        min_memories: Minimum memories to always include.
        value_density_threshold: Min value-per-token rank.
        compression_ratio: Truncation ratio when over budget (0.0-1.0).
    """
    max_context_tokens: int = 4000
    reserved_system: int = 200
    reserved_query: int = 50
    max_memories_tokens: int = 3000
    min_memories: int = 1
    value_density_threshold: float = 0.1
    compression_ratio: float = 0.6


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    Uses character-based approximation: 4 chars ≈ 1 token.

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def truncate_to_budget(text: str, budget_tokens: int) -> str:
    """Truncate text to fit within a token budget.

    Preserves the beginning (which usually contains the key info).
    Adds "..." truncation indicator if shortened.

    Args:
        text: Input text.
        budget_tokens: Target token limit.

    Returns:
        Truncated text.
    """
    if not text or budget_tokens <= 0:
        return ""

    max_chars = int(budget_tokens * CHARS_PER_TOKEN)
    if len(text) <= max_chars:
        return text

    # Leave room for "..."
    truncated = text[:max_chars - 3] + "..."
    return truncated


# ── Value-Dense Selection ───────────────────────────────────────────────────

@dataclass
class MemoryValue:
    """Value-per-token assessment for a memory."""
    memory_id: str
    content: str
    relevance: float  # 0.0-1.0 relevance score
    tokens: int
    value_per_token: float = 0.0

    def __post_init__(self):
        if self.tokens > 0:
            self.value_per_token = round(self.relevance / self.tokens, 6)


def select_value_dense(
    memories: list[dict[str, Any]],
    budget_tokens: int,
    min_items: int = 1,
    content_key: str = "content",
    score_key: str = "score",
    id_key: str = "neuron_id",
) -> list[dict[str, Any]]:
    """Select the most value-dense memories to fit within a token budget.

    Computes value-per-token for each memory and greedily selects
    the most efficient ones until the budget is exhausted.

    Args:
        memories: List of memory dicts with content, score.
        budget_tokens: Token budget for selected memories.
        min_items: Minimum items to always include (even if over budget).
        content_key: Dict key for content text.
        score_key: Dict key for relevance score.
        id_key: Dict key for memory ID.

    Returns:
        Subset of memories optimized for value-per-token.
    """
    if not memories:
        return []
    if budget_tokens <= 0:
        return memories[:min_items] if min_items > 0 else []

    # Assess each memory
    assessed: list[MemoryValue] = []
    for m in memories:
        content = m.get(content_key, "")
        relevance = m.get(score_key, 0.5)
        mid = m.get(id_key, m.get("id", ""))
        tokens = estimate_tokens(content)
        assessed.append(MemoryValue(memory_id=mid, content=content, relevance=relevance, tokens=tokens))

    # Sort by value-per-token descending
    assessed.sort(key=lambda x: x.value_per_token, reverse=True)

    # Greedy selection
    selected: list[dict[str, Any]] = []
    used_tokens = 0

    for av in assessed:
        if used_tokens + av.tokens <= budget_tokens or len(selected) < min_items:
            # Find and add original dict
            for m in memories:
                mid = m.get(id_key, m.get("id", ""))
                if mid == av.memory_id:
                    m["_tokens"] = av.tokens
                    m["_value_per_token"] = av.value_per_token
                    selected.append(m)
                    used_tokens += av.tokens
                    break
        else:
            break

    return selected


def compute_budget_allocation(total_tokens: int) -> dict[str, int]:
    """Compute token allocation across context categories.

    Args:
        total_tokens: Total context window size.

    Returns:
        Dict with per-category token budgets.
    """
    system = min(OVERHEAD_TOKENS["system_prompt"], int(total_tokens * 0.1))
    query = min(OVERHEAD_TOKENS["query"], int(total_tokens * 0.05))
    format_overhead = OVERHEAD_TOKENS["format_wrapper"]

    available = total_tokens - system - query - format_overhead
    memories = max(0, available)

    return {
        "total": total_tokens,
        "system_prompt": system,
        "query": query,
        "format_overhead": format_overhead,
        "memories": memories,
    }


def format_within_budget(
    memories: list[dict[str, Any]],
    total_budget: int = 4000,
    query: str = "",
) -> str:
    """Format memories into context, respecting a total token budget.

    Allocates budget across system/query/memories, selects value-dense
    memories, and formats with truncation if still over budget.

    Args:
        memories: List of memory dicts with content, score.
        total_budget: Total token budget for the context.
        query: Optional query string (uses tokens from query budget).

    Returns:
        Formatted context string within budget.
    """
    allocation = compute_budget_allocation(total_budget)

    # Account for query in the query budget
    query_tokens = estimate_tokens(query)

    # Select value-dense memories for the memory budget
    selected = select_value_dense(memories, allocation["memories"], min_items=1)

    # Format
    lines = []
    if query:
        lines.append(f"Query: {query}")

    if selected:
        lines.append("Relevant memories:")
        for m in selected:
            content = m.get("content", "")
            score = m.get("score", 0.5)
            # Truncate if needed
            tokens_left = allocation["memories"]
            content_tokens = estimate_tokens(content)
            if content_tokens > tokens_left:
                content = truncate_to_budget(content, max(1, tokens_left - OVERHEAD_TOKENS["per_memory_overhead"]))
            lines.append(f"- [{score:.2f}] {content}")

    result = "\n".join(lines)

    # Final budget check
    result_tokens = estimate_tokens(result)
    if result_tokens > total_budget:
        result = truncate_to_budget(result, total_budget - 10)

    return result


# ── Token Budget Manager ─────────────────────────────────────────────────────

class TokenBudgetManager:
    """Manages token budgets across recall cycles.

    Tracks actual usage and adjusts future budgets based on observed
    compression ratios.
    """

    def __init__(self, config: TokenBudgetConfig | None = None):
        self.config = config or TokenBudgetConfig()
        self._usage_history: list[dict[str, Any]] = []

    def get_allocation(self) -> dict[str, int]:
        """Get current token budget allocation."""
        return compute_budget_allocation(self.config.max_context_tokens)

    def select_best(
        self,
        memories: list[dict[str, Any]],
        content_key: str = "content",
        score_key: str = "score",
    ) -> list[dict[str, Any]]:
        """Select best memories within the memory token budget."""
        allocation = self.get_allocation()
        selected = select_value_dense(
            memories,
            allocation["memories"],
            min_items=self.config.min_memories,
            content_key=content_key,
            score_key=score_key,
        )

        # Record usage
        total_tokens = sum(m.get("_tokens", estimate_tokens(m.get(content_key, ""))) for m in selected)
        self._usage_history.append({
            "candidates": len(memories),
            "selected": len(selected),
            "budget": allocation["memories"],
            "used": total_tokens,
            "utilization": round(total_tokens / max(allocation["memories"], 1), 2),
        })

        return selected

    def get_usage_history(self, last_n: int = 10) -> list[dict[str, Any]]:
        """Get recent budget usage history."""
        return self._usage_history[-last_n:]

    def estimated_savings(self) -> float:
        """Estimate tokens saved by budget management."""
        if not self._usage_history:
            return 0.0
        total_candidate_tokens = sum(
            h["candidates"] * 100  # Rough estimate
            for h in self._usage_history
        )
        total_used = sum(h["used"] for h in self._usage_history)
        return max(0, total_candidate_tokens - total_used)
