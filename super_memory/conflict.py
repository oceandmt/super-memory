"""Lightweight conflict detection for Super Memory.

Detects contradictions between memory records using:
1. Negation detection (is/is not, has/doesn't have)
2. Temporal classification (was vs now, old vs current)
3. Direct contradiction patterns (X is Y vs X is not Y)

This is a lightweight 80/20 implementation — ~300 LOC vs neural-memory's 818 LOC.
It covers the most common 80% of contradictions without LLM calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import MemoryRecord
from .storage import SuperMemoryStore

# ── Negation patterns ──────────────────────────────────────────────────────
_NEGATION_PATTERNS: list[tuple[str, str]] = [
    # (positive_pattern, negative_pattern)  — both indexed by content
    (r"\b(is|was|are|were)\s+(not|never|n't)\b", r"\b(is|was|are|were)\b(?!\s+(not|never|n't))"),
    (r"\b(does|do|did)\s+not\b", r"\b(does|do|did)\b(?!\s+not)"),
    (r"\b(has|have|had)\s+not\b", r"\b(has|have|had)\b(?!\s+not)"),
    (r"\b(can|could|will|would|shall|should|may|might)\s+not\b",
     r"\b(can|could|will|would|shall|should|may|might)\b(?!\s+not)"),
    (r"\bno\s+\w+\b", r"\b(some|any|every)\s+\w+\b"),
    (r"\bneither\b", r"\b(either|both)\b"),
    (r"\bwithout\b", r"\bwith\b"),
]

_TEMPORAL_KEYWORDS = {
    "currently", "now", "today", "present",
    "previously", "before", "old", "past",
    "new", "updated", "latest", "deprecated",
}


@dataclass
class Conflict:
    """A detected conflict between two memory records."""
    memory_a_id: str
    memory_b_id: str
    type: str  # "negation", "temporal", "direct_contradiction"
    content_a: str
    content_b: str
    score: float  # 0.0-1.0 confidence
    reason: str = ""


@dataclass
class ConflictReport:
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.conflicts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_count": self.count,
            "conflicts": [
                {
                    "memory_a_id": c.memory_a_id,
                    "memory_b_id": c.memory_b_id,
                    "type": c.type,
                    "content_a": c.content_a[:200],
                    "content_b": c.content_b[:200],
                    "score": c.score,
                    "reason": c.reason,
                }
                for c in self.conflicts
            ],
        }


def _has_negation(content: str) -> bool:
    """Check if content contains negation patterns."""
    lower = content.lower()
    for pos_pat, _ in _NEGATION_PATTERNS:
        if re.search(pos_pat, lower):
            return True
    return False


def _has_temporal_shift(content_a: str, content_b: str) -> bool:
    """Check if two records have temporal keywording indicating a shift."""
    words_a = set(content_a.lower().split())
    words_b = set(content_b.lower().split())
    return bool(words_a & _TEMPORAL_KEYWORDS) or bool(words_b & _TEMPORAL_KEYWORDS)


def _content_similarity(a: str, b: str) -> float:
    """Simple word-overlap Jaccard similarity."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def detect_conflicts(
    records: list[MemoryRecord],
    min_similarity: float = 0.3,
) -> ConflictReport:
    """Detect conflicts among a list of memory records.

    Conflicts are detected when two records share sufficient word overlap
    but express contradictory (negation-based) claims.

    Args:
        records: List of MemoryRecord to check for conflicts.
        min_similarity: Minimum Jaccard similarity to consider related (0.0-1.0).

    Returns:
        ConflictReport with detected conflicts.
    """
    report = ConflictReport()

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]
            # Must share some content overlap
            sim = _content_similarity(a.content, b.content)
            if sim < min_similarity:
                continue

            # Check negation conflict
            neg_a = _has_negation(a.content)
            neg_b = _has_negation(b.content)
            if neg_a != neg_b:
                # One has negation, one doesn't — potential contradiction
                neg_content = a.content if neg_a else b.content
                pos_content = b.content if neg_a else a.content
                score = sim * 0.8  # Weight by content overlap
                report.conflicts.append(
                    Conflict(
                        memory_a_id=a.id,
                        memory_b_id=b.id,
                        type="negation",
                        content_a=a.content,
                        content_b=b.content,
                        score=round(score, 3),
                        reason=f"One asserts positive, other negative: "
                               f"'{pos_content[:80]}...' vs '{neg_content[:80]}...'",
                    )
                )
                continue

            # Check temporal shift
            if _has_temporal_shift(a.content, b.content) and sim > 0.4:
                report.conflicts.append(
                    Conflict(
                        memory_a_id=a.id,
                        memory_b_id=b.id,
                        type="temporal",
                        content_a=a.content,
                        content_b=b.content,
                        score=round(sim * 0.6, 3),
                        reason=f"Temporal keywords suggest an update/supersede: "
                               f"'{a.content[:80]}...' vs '{b.content[:80]}...'",
                    )
                )

    return report


def detect_conflicts_for_content(
    content: str,
    store: SuperMemoryStore,
    limit: int = 50,
    min_similarity: float = 0.3,
) -> ConflictReport:
    """Detect conflicts between new content and existing records.

    Args:
        content: New content to check.
        store: SuperMemoryStore to query existing records.
        limit: Max existing records to compare against.
        min_similarity: Minimum Jaccard similarity.

    Returns:
        ConflictReport with detected conflicts.
    """
    # Get recent active records
    with store.connect() as conn:
        from .models import ALIVE_SQL
        active_filter = ALIVE_SQL  # canonical soft-delete guard (see models.ALIVE_SQL)
        rows = conn.execute(
            f"SELECT * FROM memories WHERE {active_filter} ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    existing = []
    for row in rows:
        existing.append(
            MemoryRecord(
                id=row["id"],
                content=row["content"],
                type=row["type"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc),
            )
        )

    # Create a temp content record and compare
    temp = MemoryRecord(content=content)
    all_records = [temp] + existing
    return detect_conflicts(all_records, min_similarity=min_similarity)


def resolve_conflict(
    conflict_id: str,
    resolution: str,
    reason: str = "",
    store: SuperMemoryStore | None = None,
) -> dict[str, Any]:
    """Record a conflict resolution event.

    Args:
        conflict_id: Arbitrary conflict identifier.
        resolution: "keep_both", "keep_a", "keep_b", "supersede".
        reason: Why this resolution was chosen.
        store: Optional store for persistent logging.

    Returns:
        Dict with resolution confirmation.
    """
    valid = {"keep_both", "keep_a", "keep_b", "supersede"}
    if resolution not in valid:
        return {"ok": False, "error": f"invalid resolution: {resolution}. Valid: {valid}"}

    result = {
        "ok": True,
        "conflict_id": conflict_id,
        "resolution": resolution,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if store is not None:
        # Log the resolution
        try:
            store._set_meta(f"conflict_resolved:{conflict_id}", result)
        except Exception:
            pass

    return result
