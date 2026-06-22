"""Reflex Arc — always-on pinned neurons for boosted recall.

Reflex neurons are "always-on" in every recall query. They bypass spreading
activation and are injected directly into context at the top of results.
Use for: critical rules, user preferences, project constraints, safety boundaries.

Based on neural-memory v4.58.0 engine/reflex_activation.py but simplified.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ReflexConfig", "ReflexManager", "get_reflex_manager",
    "apply_reflexes_to_recall",
]

logger = logging.getLogger("super-memory.reflex")


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class ReflexConfig:
    """Configuration for the Reflex Arc.

    Attributes:
        enabled: Set False to disable reflex injection.
        max_reflex_results: Maximum neurons to inject in recall.
        min_boost_score: Minimum reflex boost multiplier.
        auto_pin_on_save: Auto-pin boundary and instruction type memories.
    """
    enabled: bool = True
    max_reflex_results: int = 5
    min_boost_multiplier: float = 1.5
    auto_pin_on_save: bool = True


# ── Reflex Manager ───────────────────────────────────────────────────────────

@dataclass
class ReflexManager:
    """Manages reflex-pinned neurons.

    Reflexes are stored in-memory (fast) with optional SQLite persistence.
    """

    config: ReflexConfig = field(default_factory=ReflexConfig)
    _reflex_ids: set[str] = field(default_factory=set)
    _reflex_contents: dict[str, str] = field(default_factory=dict)

    def pin(self, neuron_id: str, content: str = "") -> bool:
        """Pin a neuron as a reflex (always-on in recall)."""
        if not neuron_id:
            return False
        self._reflex_ids.add(neuron_id)
        if content:
            self._reflex_contents[neuron_id] = content[:500]
        logger.debug("reflex pinned: %s", neuron_id[:40])
        return True

    def unpin(self, neuron_id: str) -> bool:
        """Remove a neuron from reflex status."""
        if neuron_id in self._reflex_ids:
            self._reflex_ids.discard(neuron_id)
            self._reflex_contents.pop(neuron_id, None)
            return True
        return False

    def is_reflex(self, neuron_id: str) -> bool:
        """Check if a neuron is pinned as reflex."""
        return neuron_id in self._reflex_ids

    def get_all_reflexes(self) -> list[dict[str, Any]]:
        """Get all reflex neurons as lightweight dicts."""
        return [
            {"neuron_id": nid, "content": self._reflex_contents.get(nid, ""), "reflex": True}
            for nid in self._reflex_ids
        ]

    def get_reflex_content(self, neuron_id: str) -> str:
        """Get stored content for a reflex neuron."""
        return self._reflex_contents.get(neuron_id, "")

    def count(self) -> int:
        """Number of pinned reflexes."""
        return len(self._reflex_ids)

    def clear(self) -> None:
        """Remove all reflexes."""
        self._reflex_ids.clear()
        self._reflex_contents.clear()

    # ── Persistence ─────────────────────────────────────────────────────────

    def save_state(self) -> dict[str, Any]:
        """Serialize reflex state for persistence."""
        return {
            "reflex_ids": list(self._reflex_ids),
            "reflex_contents": self._reflex_contents.copy(),
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore reflex state from serialized data."""
        self._reflex_ids = set(state.get("reflex_ids", []))
        self._reflex_contents = state.get("reflex_contents", {})

    def store_persist(self, store: Any) -> None:
        """Persist reflexes to SQLite store (if available)."""
        try:
            with store.connect() as conn:
                conn.execute("DELETE FROM cognitive_reflexes")  # noqa
                for nid in self._reflex_ids:
                    content = self._reflex_contents.get(nid, "")
                    conn.execute(
                        "INSERT OR REPLACE INTO cognitive_reflexes (neuron_id, content) VALUES (?, ?)",
                        (nid, content),
                    )
        except Exception as e:
            logger.debug("reflex persist failed: %s", e)

    def store_load(self, store: Any) -> None:
        """Load reflexes from SQLite store."""
        try:
            with store.connect() as conn:
                rows = conn.execute("SELECT neuron_id, content FROM cognitive_reflexes").fetchall()
                self._reflex_ids = {r["neuron_id"] for r in rows}
                self._reflex_contents = {r["neuron_id"]: r["content"] for r in rows}
        except Exception as e:
            logger.debug("reflex load failed: %s", e)


# ── Global singleton ─────────────────────────────────────────────────────────

_REFLEX_MANAGER: ReflexManager | None = None


def get_reflex_manager() -> ReflexManager:
    """Get or create the global ReflexManager singleton."""
    global _REFLEX_MANAGER
    if _REFLEX_MANAGER is None:
        _REFLEX_MANAGER = ReflexManager()
    return _REFLEX_MANAGER


# ── Recall Integration ───────────────────────────────────────────────────────

def apply_reflexes_to_recall(
    query: str,
    recall_results: list[dict[str, Any]],
    max_reflex: int | None = None,
) -> list[dict[str, Any]]:
    """Inject reflex neurons at the top of recall results.

    Args:
        query: Recall query (used to filter relevant reflexes).
        recall_results: Results from spreading activation.
        max_reflex: Max reflexes to inject (default from config).

    Returns:
        Combined results with reflexes at top, deduplicated.
    """
    try:
        mgr = get_reflex_manager()
        if not mgr.config.enabled or mgr.count() == 0:
            return recall_results

        max_r = max_reflex or mgr.config.max_reflex_results
        existing_ids = {r.get("neuron_id", r.get("id", "")) for r in recall_results if r}

        reflex_list = mgr.get_all_reflexes()
        # Rank reflexes: prefer those matching query
        query_lower = (query or "").lower()
        query_terms = set(query_lower.split())

        def _relevance(r: dict[str, Any]) -> float:
            content_lower = (r.get("content", "") or "").lower()
            matches = sum(1 for t in query_terms if t in content_lower and len(t) > 2)
            return matches / max(len(query_terms), 1)

        reflex_list.sort(key=_relevance, reverse=True)

        injected = 0
        for r in reflex_list:
            nid = r.get("neuron_id", "")
            if nid not in existing_ids:
                r["_reflex"] = True
                r["_priming_boost"] = 2.0
                r["score"] = 1.0
                recall_results.insert(0, r)
                existing_ids.add(nid)
                injected += 1
                if injected >= max_r:
                    break

    except Exception as e:
        logger.debug("reflex apply failed: %s", e)

    return recall_results
