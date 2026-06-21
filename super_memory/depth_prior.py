"""Adaptive Depth Prior for Super Memory recall.

Tracks recall success rates per query type and auto-adjusts
search depth to optimize the balance between recall quality
and token cost.

Depth levels:
  0 = instant (direct lookup, 1 hop)
  1 = context (default, 3 hops)
  2 = habit (cross-time patterns, 4 hops)
  3 = deep (full graph traversal)

The depth prior starts with conservative defaults and adapts
per query type based on observed success/failure rates.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_KEY_PREFIX = "_depth_prior_v1"


def _now() -> float:
    return time.monotonic()


# ── Query type classification ──────────────────────────────────────────────

# Keywords that signal different query intents
_PROJECT_KEYWORDS = {
    "project", "repo", "workspace", "code", "branch", "commit",
    "config", "deploy", "ci", "test", "build",
}
_CURRENT_KEYWORDS = {
    "current", "now", "today", "latest", "recent", "active",
    "state", "status", "running",
}
_HISTORY_KEYWORDS = {
    "history", "past", "previous", "old", "archive", "earlier",
    "timeline", "evolution", "changelog",
}
_DEEP_KEYWORDS = {
    "architecture", "design", "reason", "why", "how",
    "relationship", "compare", "impact", "root cause",
}


def classify_query(query: str) -> str:
    """Classify a query into a recall type for depth adjustment.

    Returns one of: 'current', 'history', 'deep', 'project', 'general'.
    """
    words = set(query.lower().split())
    if words & _CURRENT_KEYWORDS:
        return "current"
    if words & _HISTORY_KEYWORDS:
        return "history"
    if words & _DEEP_KEYWORDS:
        return "deep"
    if words & _PROJECT_KEYWORDS:
        return "project"
    return "general"


# ── Default depth map ──────────────────────────────────────────────────────

_DEFAULT_DEPTHS: dict[str, int] = {
    "current": 0,     # Quick lookups
    "history": 1,     # Context depth
    "deep": 2,        # Habit depth
    "project": 1,     # Context depth
    "general": 1,     # Context depth (default)
}


@dataclass
class DepthPrior:
    """Tracks recall success history per query type.

    Attributes:
        successes: Count of successful recalls per type.
        failures: Count of failed recalls per type.
        depths: Current depth per type.
        total_queries: Total queries tracked.
        last_decay: Timestamp of last decay event.
    """
    successes: dict[str, int] = field(default_factory=lambda: {"general": 0})
    failures: dict[str, int] = field(default_factory=lambda: {"general": 0})
    depths: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_DEPTHS))
    total_queries: int = 0
    last_decay: float = field(default_factory=_now)

    def expected_depth(self, query_type: str) -> int:
        """Return the recommended depth for a query type."""
        return self.depths.get(query_type, _DEFAULT_DEPTHS.get(query_type, 1))

    def update(self, query_type: str, success: bool, hit_count: int) -> None:
        """Update statistics after a recall run.

        Args:
            query_type: Classified query type.
            success: Whether recall returned useful results.
            hit_count: Number of results returned.
        """
        self.total_queries += 1
        if success and hit_count >= 2:
            self.successes[query_type] = self.successes.get(query_type, 0) + 1
        else:
            self.failures[query_type] = self.failures.get(query_type, 0) + 1

        # Recalculate depth every 10 queries for this type
        total = self.successes.get(query_type, 0) + self.failures.get(query_type, 0)
        if total > 0 and total % 10 == 0:
            rate = self.successes.get(query_type, 0) / total
            if rate < 0.3:
                # Low success rate — try deeper search
                current = self.depths.get(query_type, 1)
                self.depths[query_type] = min(current + 1, 3)
            elif rate > 0.8 and self.depths.get(query_type, 1) > 0:
                # High success rate — try shallower (saves tokens)
                current = self.depths.get(query_type, 1)
                self.depths[query_type] = max(current - 1, 0)

    def decay(self, factor: float = 0.95) -> None:
        """Apply exponential decay to old successes.
        
        Prevents stale patterns from dominating.
        """
        now = _now()
        if now - self.last_decay < 3600:  # Once per hour max
            return
        self.last_decay = now
        for key in list(self.successes.keys()):
            self.successes[key] = max(1, int(self.successes[key] * factor))
        for key in list(self.failures.keys()):
            self.failures[key] = max(1, int(self.failures[key] * factor))

    def to_dict(self) -> dict[str, Any]:
        return {
            "depths": dict(self.depths),
            "successes": dict(self.successes),
            "failures": dict(self.failures),
            "total_queries": self.total_queries,
        }


# ── Global cache (in-memory, backed by metadata table) ─────────────────────

_depth_cache: dict[str, DepthPrior] = {}
_depth_lock = threading.Lock()


def _get_prior(store: Any, key: str = "default") -> DepthPrior:
    """Get or create a DepthPrior from cache + persistent store."""
    with _depth_lock:
        if key in _depth_cache:
            return _depth_cache[key]
        # Try to load from store
        prior = DepthPrior()
        try:
            row = store._get_meta(f"{_KEY_PREFIX}:{key}")
            if row:
                data = json.loads(row) if isinstance(row, str) else row
                prior.successes = data.get("successes", {"general": 0})
                prior.failures = data.get("failures", {"general": 0})
                prior.depths = data.get("depths", dict(_DEFAULT_DEPTHS))
                prior.total_queries = data.get("total_queries", 0)
        except Exception:
            pass  # Start fresh on error
        _depth_cache[key] = prior
        return prior


def _save_prior(store: Any, prior: DepthPrior, key: str = "default") -> None:
    """Persist depth prior state."""
    try:
        store._set_meta(f"{_KEY_PREFIX}:{key}", prior.to_dict())
    except Exception:
        pass  # Non-fatal


def expected_depth(query: str, store: Any = None) -> int:
    """Get expected recall depth for a query.

    Args:
        query: The search query string.
        store: Optional SuperMemoryStore with _get_meta support.

    Returns:
        Recommended depth (0-3).
    """
    query_type = classify_query(query)
    if store is None:
        return _DEFAULT_DEPTHS.get(query_type, 1)
    prior = _get_prior(store)
    return prior.expected_depth(query_type)


def record_outcome(
    query: str,
    hit_count: int,
    store: Any = None,
    threshold: int = 2,
) -> None:
    """Record a recall outcome and update depth prior.

    Args:
        query: The search query string.
        hit_count: Number of results returned.
        store: Optional SuperMemoryStore.
        threshold: Minimum hits to consider successful (default 2).
    """
    if store is None:
        return
    query_type = classify_query(query)
    prior = _get_prior(store)
    prior.update(query_type, success=hit_count >= threshold, hit_count=hit_count)
    prior.decay()
    _save_prior(store, prior)
