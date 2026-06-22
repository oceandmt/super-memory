"""Goal-directed recall — bias memory retrieval toward active goals.

Ported concept from neural-memory v4.58.0 `engine/activation.py`.
Active goals boost relevance scores for memories related to current
objectives, making recall context-aware.

Architecture:
- Goals are stored in-memory (session-scoped) with optional persistence
  to SQLite via metadata records
- Active goals apply a boost multiplier to memory scores during recall
- Goals auto-expire after TTL or when marked complete
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("super-memory.goals")

# Default: boost matching memories by 2x
GOAL_BOOST_MULTIPLIER = 2.0

# Default: goal expires after 1 hour of inactivity
GOAL_DEFAULT_TTL_SECONDS = 3600

# Max active goals
MAX_ACTIVE_GOALS = 5


@dataclass
class Goal:
    """A memory retrieval goal."""
    id: str
    description: str
    keywords: list[str] = field(default_factory=list)
    priority: int = 5  # 1-10, higher = stronger boost
    created_at: float = 0.0
    expires_at: float = 0.0
    state: str = "active"  # active | paused | completed

    def is_expired(self, now: float | None = None) -> bool:
        now = now or time.time()
        return now > self.expires_at

    def is_active(self) -> bool:
        return self.state == "active" and not self.is_expired()


class GoalManager:
    """In-memory goal manager for session-scoped retrieval biasing."""

    def __init__(self) -> None:
        self._goals: dict[str, Goal] = {}

    def create_goal(
        self,
        description: str,
        keywords: list[str] | None = None,
        priority: int = 5,
        ttl_seconds: int = GOAL_DEFAULT_TTL_SECONDS,
    ) -> Goal:
        """Create a new active goal."""
        import uuid
        now = time.time()
        goal_id = str(uuid.uuid4())

        # Auto-extract keywords from description if not provided
        if not keywords:
            keywords = self._extract_keywords(description)

        goal = Goal(
            id=goal_id,
            description=description,
            keywords=keywords,
            priority=priority,
            created_at=now,
            expires_at=now + ttl_seconds,
        )

        self._goals[goal_id] = goal

        # Enforce max active goals
        self._trim_excess()

        logger.debug("goal created", goal_id=goal_id, description=description[:60])
        return goal

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from goal description."""
        import re
        # Simple extraction: take capitalized words, tech terms, and multi-word phrases
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_.\-/]{2,}", text)
        # Lowercase filter for common noise words
        stop_words = {
            "the", "a", "an", "to", "for", "of", "in", "on", "at", "by",
            "with", "from", "and", "or", "but", "not", "is", "are", "was",
            "were", "been", "have", "has", "had", "do", "does", "did",
            "will", "would", "can", "could", "should", "may", "might",
            "that", "this", "these", "those", "it", "its", "all", "each",
            "every", "some", "any", "no", "none", "both", "few", "more",
            "most", "other", "into", "about", "than", "as", "if", "what",
            "how", "when", "where", "why", "who", "whom", "which",
        }
        return [w.lower() for w in words if w.lower() not in stop_words and len(w) > 2]

    def get_goal(self, goal_id: str) -> Goal | None:
        """Get a goal by ID."""
        goal = self._goals.get(goal_id)
        if goal and goal.is_expired():
            goal.state = "expired"
        return goal

    def list_goals(self, state: str | None = None) -> list[Goal]:
        """List goals, optionally filtered by state."""
        now = time.time()
        goals = []
        for g in self._goals.values():
            if g.is_expired():
                g.state = "expired"
            if state is None or g.state == state:
                goals.append(g)
        return sorted(goals, key=lambda g: g.priority, reverse=True)

    def get_active_goals(self) -> list[Goal]:
        """Get all currently active goals."""
        return [g for g in self._goals.values() if g.is_active()]

    def pause_goal(self, goal_id: str) -> bool:
        """Pause an active goal."""
        goal = self._goals.get(goal_id)
        if goal and goal.state == "active":
            goal.state = "paused"
            return True
        return False

    def complete_goal(self, goal_id: str) -> bool:
        """Mark a goal as completed."""
        goal = self._goals.get(goal_id)
        if goal:
            goal.state = "completed"
            return True
        return False

    def remove_goal(self, goal_id: str) -> bool:
        """Remove a goal entirely."""
        return self._goals.pop(goal_id, None) is not None

    def clear_expired(self) -> int:
        """Remove expired goals. Returns count removed."""
        now = time.time()
        expired = [gid for gid, g in self._goals.items() if g.is_expired(now)]
        for gid in expired:
            del self._goals[gid]
        return len(expired)

    def _trim_excess(self) -> None:
        """If more than MAX_ACTIVE_GOALS active, remove lowest priority."""
        active = self.get_active_goals()
        if len(active) > MAX_ACTIVE_GOALS:
            # Remove lowest priority (excluding the newest)
            sorted_active = sorted(active, key=lambda g: (g.priority, -g.created_at))
            for goal in sorted_active[:len(sorted_active) - MAX_ACTIVE_GOALS]:
                self._goals.pop(goal.id, None)

    def compute_goal_boost(self, memory_tags: list[str], memory_content: str = "") -> float:
        """Compute boost multiplier for a memory based on active goals.

        Returns a multiplier >= 1.0 (no boost) up to ~3.0 (strong match).
        """
        active = self.get_active_goals()
        if not active:
            return 1.0

        max_boost = 1.0
        content_lower = memory_content.lower()

        for goal in active:
            boost = 1.0
            keyword_matches = 0

            # Check keywords against tags
            tag_set = {t.lower() for t in memory_tags}
            for kw in goal.keywords:
                if kw in tag_set:
                    keyword_matches += 2  # Tag match = strong signal

                # Check against content
                if kw in content_lower:
                    keyword_matches += 1

            if keyword_matches > 0:
                # Boost = 1 + (priority/10) * matches * decay factor
                priority_factor = goal.priority / 10.0
                boost = 1.0 + (priority_factor * keyword_matches * 0.5)
                boost = min(boost, 3.0)  # Cap at 3x

            if boost > max_boost:
                max_boost = boost

        return max_boost


# ── Singleton ─────────────────────────────────────────────────────────────────

_goal_manager: GoalManager | None = None


def get_goal_manager() -> GoalManager:
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = GoalManager()
    return _goal_manager


def create_goal(
    description: str,
    keywords: list[str] | None = None,
    priority: int = 5,
    ttl_seconds: int = GOAL_DEFAULT_TTL_SECONDS,
) -> Goal:
    """Convenience: create a new goal."""
    return get_goal_manager().create_goal(description, keywords, priority, ttl_seconds)


def compute_goal_boost(tags: list[str], content: str = "") -> float:
    """Convenience: compute goal boost for a memory."""
    return get_goal_manager().compute_goal_boost(tags, content)
