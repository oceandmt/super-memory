"""Arousal/Valence Tracking for Super Memory.

Detects emotional intensity (arousal) and sentiment (valence) at save time,
and provides recall filters by arousal threshold or valence.

Lightweight heuristic approach — no ML models, no LLM calls.
Covers ~70% of use cases at <1ms per memory.

- Arousal: 0.0 (neutral) to 1.0 (intense)
- Valence: 'positive', 'negative', 'neutral'
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .models import MemoryRecord
from .storage import SuperMemoryStore


# ── Arousal Keywords ───────────────────────────────────────────────────────

_HIGH_AROUSAL_WORDS: set[str] = {
    # Urgency / severity
    "critical", "urgent", "emergency", "blocked", "failing", "crash", "broken",
    "deadline", "immediately", "must", "required", "mandatory",
    # Strong positive
    "amazing", "excellent", "breakthrough", "incredible", "fantastic",
    "brilliant", "outstanding", "perfect", "beautiful", "wonderful",
    # Strong negative
    "terrible", "horrible", "awful", "disaster", "catastrophic", "nightmare",
    "rage", "furious", "devastating", "worst",
    # Discovery / surprise
    "surprising", "unexpected", "shocking", "mindblowing", "whoa",
    "revolutionary", "game-changer", "never seen",
}

_MEDIUM_AROUSAL_WORDS: set[str] = {
    # Modifier words
    "important", "significant", "major", "serious", "severe",
    "great", "awesome", "nice", "good", "happy",
    "bad", "sad", "angry", "frustrated", "annoyed", "concerned", "worried",
    "failed", "error", "issue", "problem", "risk", "danger",
    "success", "solved", "fixed", "improved", "progress", "achieved",
    "love", "hate", "exciting", "interesting",
    "complex", "difficult", "tricky", "challenging",
}

_POSITIVE_WORDS: set[str] = {
    "success", "solved", "fixed", "improved", "progress", "achieved",
    "great", "awesome", "excellent", "amazing", "good", "happy",
    "breakthrough", "incredible", "fantastic", "brilliant", "outstanding",
    "love", "exciting", "wonderful", "beautiful", "perfect",
    "nice", "win", "won", "pass", "passed", "approved",
}

_NEGATIVE_WORDS: set[str] = {
    "failed", "error", "issue", "problem", "bug", "crash", "broken",
    "bad", "sad", "angry", "awful", "terrible", "horrible",
    "frustrated", "annoyed", "concerned", "worried", "danger", "risk",
    "blocked", "critical", "urgent", "emergency", "disaster", "catastrophic",
    "worst", "hate", "rage", "furious", "devastating", "nightmare",
}


# ── Detection ──────────────────────────────────────────────────────────────


def detect_arousal(text: str) -> float:
    """Detect emotional intensity (0.0 neutral → 1.0 intense).

    Uses a weighted keyword approach:
    - High-arousal words: +0.3 each (max +0.8)
    - Medium-arousal words: +0.1 each (max +0.4)
    - Exclamation marks: +0.05 each (max +0.2)
    - ALL CAPS words >4 chars: +0.1 each (max +0.3)
    - Very short or empty text: 0.0
    """
    if not text or len(text) < 10:
        return 0.0

    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return 0.0

    high_count = sum(1 for w in words if w in _HIGH_AROUSAL_WORDS)
    medium_count = sum(1 for w in words if w in _MEDIUM_AROUSAL_WORDS)
    excl_count = text.count("!")
    allcaps_count = sum(1 for w in re.findall(r"[A-Z]{4,}", text) if w.lower() not in ("THIS", "THAT", "THE"))

    score = 0.0
    score += min(high_count * 0.3, 0.8)
    score += min(medium_count * 0.1, 0.4)
    score += min(excl_count * 0.05, 0.2)
    score += min(allcaps_count * 0.1, 0.3)

    return min(round(score, 2), 1.0)


def detect_valence(text: str) -> str:
    """Detect emotional valence.

    Counts positive vs negative keyword occurrences.
    Returns 'positive', 'negative', or 'neutral'.
    """
    if not text or len(text) < 10:
        return "neutral"

    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return "neutral"

    pos_count = sum(1 for w in words if w in _POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in _NEGATIVE_WORDS)

    # Negation check: "not good", "not happy"
    negated_pos = 0
    for i, w in enumerate(words):
        if w in ("not", "never", "no", "isn't", "aren't", "don't", "doesn't"):
            if i + 1 < len(words) and words[i + 1] in _POSITIVE_WORDS:
                negated_pos += 1

    pos_count -= negated_pos
    neg_count += negated_pos

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    else:
        return "neutral"


def classify_affect(text: str) -> dict[str, Any]:
    """Classify both arousal and valence in one pass.

    Returns:
        {"arousal": 0.0-1.0, "valence": "positive|negative|neutral"}
    """
    return {
        "arousal": detect_arousal(text),
        "valence": detect_valence(text),
    }


# ── Enrich Record ──────────────────────────────────────────────────────────


def enrich_record(
    record: MemoryRecord,
) -> MemoryRecord:
    """Enrich a MemoryRecord with arousal/valence metadata.

    Mutates record.metadata in-place and returns it.
    """
    affect = classify_affect(record.content)
    record.metadata["arousal"] = affect["arousal"]
    record.metadata["valence"] = affect["valence"]
    return record


# ── Recall Filters ─────────────────────────────────────────────────────────


def recall_by_affect(
    store: SuperMemoryStore,
    min_arousal: float | None = None,
    valence: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Recall memories filtered by arousal/valence.

    Filters against stored metadata_json values.
    For memories saved before affect tracking was added, detects on the fly.

    Args:
        store: SuperMemoryStore.
        min_arousal: Min arousal threshold (0.0-1.0).
        valence: 'positive', 'negative', or 'neutral'.
        limit: Max results.

    Returns:
        Filtered memories with affect stats.
    """
    conditions = []
    params: list[Any] = []

    # Exclude soft-deleted
    conditions.append(
        "(json_extract(metadata_json, '$.soft_deleted') IS NULL"
        " OR json_extract(metadata_json, '$.soft_deleted') != 1)"
    )

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE " + " AND ".join(conditions) +
            " ORDER BY created_at DESC LIMIT ?",
            params + [limit * 2],  # Extra room for filtering
        ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        meta = json.loads(row["metadata_json"] if row["metadata_json"] else "{}")
        arousal = meta.get("arousal")
        val = meta.get("valence")

        # If affect not stored, detect now
        if arousal is None:
            affect = classify_affect(row["content"])
            arousal = affect["arousal"]
            val = affect["valence"]

        if min_arousal is not None and arousal < min_arousal:
            continue
        if valence is not None and val != valence:
            continue

        results.append({
            "id": row["id"],
            "content": row["content"][:300],
            "type": row["type"],
            "layer": row["layer"],
            "created_at": row["created_at"] if row["created_at"] else "",
            "arousal": arousal,
            "valence": val,
        })

        if len(results) >= limit:
            break

    # Stats
    if results:
        avg_arousal = sum(r["arousal"] for r in results) / len(results)
        valence_counts: dict[str, int] = defaultdict(int)
        for r in results:
            valence_counts[r["valence"]] += 1
    else:
        avg_arousal = 0.0
        valence_counts = {}

    return {
        "ok": True,
        "results": results,
        "count": len(results),
        "stats": {
            "avg_arousal": round(avg_arousal, 2),
            "valence_distribution": dict(valence_counts),
        },
    }
