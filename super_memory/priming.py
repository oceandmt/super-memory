"""Priming — session-aware recall weight modulation.

Tracks which neurons/concepts have been accessed in the current session
and boosts their activation weights on subsequent recalls. This makes
related follow-up queries return more relevant results (context continuity).

Based on neural-memory v4.58.0 engine/priming.py but simplified for
super-memory's non-async, session-scoped architecture.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "PrimingConfig", "PrimingTracker", "SessionPriming",
]

logger = logging.getLogger("super-memory.priming")


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class PrimingConfig:
    """Configuration for session priming.

    Attributes:
        enabled: Set False to disable priming.
        boost_max: Maximum multiplication factor for primed neurons.
        boost_decay: Exponential decay per subsequent neuron hit.
        decay_half_life: Number of accesses before boost halves.
        track_concepts: Also boost semantically similar terms.
        max_tracked_neurons: Cap on tracked neuron IDs.
        session_timeout_min: Reset if session gap > this many minutes.
    """
    enabled: bool = True
    boost_max: float = 2.0
    boost_decay: float = 0.85
    decay_half_life: int = 3
    track_concepts: bool = True
    max_tracked_neurons: int = 500
    session_timeout_min: int = 30


# ── Session Priming ──────────────────────────────────────────────────────────

@dataclass
class SessionPriming:
    """Tracks priming state for one session."""
    session_id: str = ""
    accessed_neurons: dict[str, int] = field(default_factory=dict)  # neuron_id -> access_count
    query_history: list[str] = field(default_factory=list)
    last_access: float = 0.0  # Unix timestamp
    concept_tags: dict[str, float] = field(default_factory=dict)  # tag -> cumulative boost
    neuron_contents: dict[str, str] = field(default_factory=dict)  # neuron_id -> content snippet

    def is_stale(self, timeout_min: int = 30) -> bool:
        """Check if this session is stale (gap > timeout)."""
        if self.last_access == 0:
            return True
        elapsed = (datetime.now(timezone.utc).timestamp() - self.last_access) / 60
        return elapsed > timeout_min


class PrimingTracker:
    """Manages priming state across sessions.

    Stores priming session data in memory (not persisted across restarts).
    For production, call .save_state() / .load_state() to persist.
    """

    def __init__(self, config: PrimingConfig | None = None):
        self.config = config or PrimingConfig()
        self._sessions: dict[str, SessionPriming] = {}

    def get_or_create_session(self, session_id: str) -> SessionPriming:
        """Get or create a priming session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionPriming(session_id=session_id)
        sp = self._sessions[session_id]
        if sp.is_stale(self.config.session_timeout_min):
            # Stale session — reset
            self._sessions[session_id] = SessionPriming(session_id=session_id)
            sp = self._sessions[session_id]
        return sp

    def record_access(self, session_id: str, neuron_id: str, content: str = "", query: str = "") -> None:
        """Record a neuron access in the session, incrementing its priming count."""
        if not self.config.enabled:
            return
        sp = self.get_or_create_session(session_id)
        sp.accessed_neurons[neuron_id] = sp.accessed_neurons.get(neuron_id, 0) + 1
        sp.last_access = datetime.now(timezone.utc).timestamp()
        if content and len(sp.neuron_contents) < self.config.max_tracked_neurons:
            sp.neuron_contents[neuron_id] = content[:200]
        if query:
            sp.query_history.append(query)
            # Limit history
            if len(sp.query_history) > 50:
                sp.query_history = sp.query_history[-50:]

    def get_priming_boost(self, session_id: str, neuron_id: str) -> float:
        """Get the boost multiplier for a primed neuron.

        Returns 1.0 (no boost) if unprimed or disabled.
        Higher access count = higher boost, subject to decay.
        """
        if not self.config.enabled:
            return 1.0
        sp = self.get_or_create_session(session_id)
        count = sp.accessed_neurons.get(neuron_id, 0)
        if count == 0:
            return 1.0
        # Exponential decay based on access count
        decay_factor = self.config.boost_decay ** (count // self.config.decay_half_life)
        boost = 1.0 + (self.config.boost_max - 1.0) * decay_factor
        return round(boost, 3)

    def get_primed_neuron_ids(self, session_id: str) -> list[str]:
        """Get list of primed neuron IDs (sorted by access count, descending)."""
        sp = self.get_or_create_session(session_id)
        return sorted(sp.accessed_neurons.keys(), key=lambda n: -sp.accessed_neurons[n])

    def get_all_boosts(self, session_id: str) -> dict[str, float]:
        """Get boost multipliers for all primed neurons."""
        boosts = {}
        sp = self.get_or_create_session(session_id)
        for nid in sp.accessed_neurons:
            boosts[nid] = self.get_priming_boost(session_id, nid)
        return boosts

    def reset_session(self, session_id: str) -> None:
        """Reset priming state for a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]

    # ── State persistence (optional) ─────────────────────────────────────────

    def save_state(self) -> dict[str, Any]:
        """Serialize priming state to dict (for persistence)."""
        return {
            name: {
                "accessed_neurons": sp.accessed_neurons.copy(),
                "query_history": sp.query_history.copy(),
                "last_access": sp.last_access,
                "neuron_contents": sp.neuron_contents.copy(),
            }
            for name, sp in self._sessions.items()
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore priming state from dict."""
        for name, data in state.items():
            self._sessions[name] = SessionPriming(
                session_id=name,
                accessed_neurons=data.get("accessed_neurons", {}),
                query_history=data.get("query_history", []),
                last_access=data.get("last_access", 0.0),
                neuron_contents=data.get("neuron_contents", {}),
            )


# ── Global singleton ─────────────────────────────────────────────────────────

_PRIMING_TRACKER: PrimingTracker | None = None


def get_priming_tracker() -> PrimingTracker:
    """Get or create the global PrimingTracker singleton."""
    global _PRIMING_TRACKER
    if _PRIMING_TRACKER is None:
        _PRIMING_TRACKER = PrimingTracker()
    return _PRIMING_TRACKER


def apply_priming_to_recall(
    session_id: str,
    results: list[dict[str, Any]],
    content_key: str = "content",
    id_key: str = "neuron_id",
) -> list[dict[str, Any]]:
    """Apply priming boosts to recall results in-place.

    Modifies results by adding '_priming_boost' and '_priming_score' keys.
    The original 'score' field is boosted multiplicatively if primed.
    """
    try:
        tracker = get_priming_tracker()
        for r in results:
            nid = r.get(id_key, r.get("id", ""))
            if nid:
                boost = tracker.get_priming_boost(session_id, nid)
                r["_priming_boost"] = boost
                if boost > 1.0:
                    current_score = r.get("score", r.get("activation_level", 0.5))
                    r["_priming_score"] = round(current_score * boost, 4)
    except Exception as e:
        logger.debug("priming apply failed: %s", e)
    return results
