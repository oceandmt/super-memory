"""Hypothesis + evidence engine — structured knowledge accumulation.

Ported concept from neural-memory v4.58.0 `engine/hypothesis.py`.
Creates hypotheses, collects supporting/contradicting evidence, and
tracks confidence evolution over time.

Bayesian-like confidence update:
- Evidence FOR: confidence += (1 - confidence) * weight * 0.3
- Evidence AGAINST: confidence *= (1 - weight * 0.5)
- Auto-resolve: confidence >= 0.9 → confirmed, <= 0.1 → refuted
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("super-memory.hypothesis")


@dataclass
class Hypothesis:
    """A structured hypothesis with Bayesian confidence tracking."""
    id: str
    content: str
    confidence: float = 0.5
    status: str = "active"  # active | confirmed | refuted | superseded
    tags: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    superseded_by: str | None = None
    version: int = 1


@dataclass
class EvidenceItem:
    """A piece of evidence for or against a hypothesis."""
    id: str
    hypothesis_id: str
    content: str
    direction: str  # "for" or "against"
    weight: float = 0.5
    created_at: str = ""


class HypothesisEngine:
    """Manage hypotheses with evidence accumulation."""

    def __init__(self) -> None:
        self._hypotheses: dict[str, Hypothesis] = {}
        self._evidence: dict[str, EvidenceItem] = {}
        self._hypo_evidence: dict[str, list[str]] = {}  # hypo_id -> [evidence_ids]

    def create_hypothesis(
        self,
        content: str,
        confidence: float = 0.5,
        tags: list[str] | None = None,
    ) -> Hypothesis:
        """Create a new hypothesis."""
        now = datetime.now(timezone.utc).isoformat()
        hypo = Hypothesis(
            id=str(uuid.uuid4()),
            content=content,
            confidence=max(0.01, min(0.99, confidence)),
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._hypotheses[hypo.id] = hypo
        self._hypo_evidence[hypo.id] = []
        logger.debug("hypothesis created", id=hypo.id, content=content[:60])
        return hypo

    def add_evidence(
        self,
        hypothesis_id: str,
        content: str,
        direction: str = "for",
        weight: float = 0.5,
    ) -> EvidenceItem | None:
        """Add evidence for/against a hypothesis. Updates confidence."""
        hypo = self._hypotheses.get(hypothesis_id)
        if not hypo or hypo.status in ("confirmed", "refuted"):
            return None

        weight = max(0.1, min(1.0, weight))
        ev = EvidenceItem(
            id=str(uuid.uuid4()),
            hypothesis_id=hypothesis_id,
            content=content,
            direction=direction,
            weight=weight,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._evidence[ev.id] = ev
        self._hypo_evidence.setdefault(hypothesis_id, []).append(ev.id)

        # Update confidence (Bayesian-like)
        if direction == "for":
            hypo.confidence += (1.0 - hypo.confidence) * weight * 0.3
        else:
            hypo.confidence *= (1.0 - weight * 0.5)

        hypo.confidence = max(0.01, min(0.99, hypo.confidence))
        hypo.updated_at = datetime.now(timezone.utc).isoformat()

        # Auto-resolve
        if hypo.confidence >= 0.9 and len(self._hypo_evidence.get(hypothesis_id, [])) >= 3:
            hypo.status = "confirmed"
            logger.debug("hypothesis confirmed", id=hypothesis_id, confidence=hypo.confidence)
        elif hypo.confidence <= 0.1 and len(self._hypo_evidence.get(hypothesis_id, [])) >= 3:
            hypo.status = "refuted"
            logger.debug("hypothesis refuted", id=hypothesis_id, confidence=hypo.confidence)

        return ev

    def evolve_hypothesis(
        self,
        hypothesis_id: str,
        new_content: str,
        reason: str = "",
    ) -> Hypothesis | None:
        """Create a new version of a hypothesis (SUPERSEDES old one)."""
        old = self._hypotheses.get(hypothesis_id)
        if not old:
            return None

        old.status = "superseded"
        old.superseded_by = None

        now = datetime.now(timezone.utc).isoformat()
        new = Hypothesis(
            id=str(uuid.uuid4()),
            content=new_content,
            confidence=old.confidence,
            tags=old.tags.copy(),
            created_at=now,
            updated_at=now,
            version=old.version + 1,
        )
        old.superseded_by = new.id
        self._hypotheses[new.id] = new
        self._hypo_evidence[new.id] = self._hypo_evidence.get(hypothesis_id, []).copy()

        if reason:
            self.add_evidence(new.id, f"Evolved: {reason}", "for", 0.4)

        return new

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        return self._hypotheses.get(hypothesis_id)

    def get_evidence(self, hypothesis_id: str) -> list[EvidenceItem]:
        ev_ids = self._hypo_evidence.get(hypothesis_id, [])
        return [self._evidence[eid] for eid in ev_ids if eid in self._evidence]

    def list_hypotheses(self, status: str | None = None) -> list[Hypothesis]:
        if status:
            return [h for h in self._hypotheses.values() if h.status == status]
        return list(self._hypotheses.values())

    def to_save_dict(self) -> dict[str, Any]:
        """Serialize for persistence as metadata."""
        return {
            "hypotheses": {
                hid: {
                    "content": h.content,
                    "confidence": h.confidence,
                    "status": h.status,
                    "tags": h.tags,
                    "created_at": h.created_at,
                    "version": h.version,
                }
                for hid, h in self._hypotheses.items()
            },
            "evidence_count": len(self._evidence),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: HypothesisEngine | None = None


def get_engine() -> HypothesisEngine:
    global _engine
    if _engine is None:
        _engine = HypothesisEngine()
    return _engine
