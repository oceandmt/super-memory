"""Temporal decay scoring for search results.

Matches OpenClaw memory-core temporal decay behaviour:
- Recent results get higher scores
- Decay follows exponential curve: score *= exp(-age_days / half_life)
- Session-scoped results have slower decay
- Configurable half-life per corpus
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


# ── Default half-lives (in days) ───────────────────────────────────────────

DEFAULT_HALF_LIVES: dict[str, float] = {
    "memory": 90.0,       # 90 days for durable memory
    "sessions": 30.0,     # 30 days for session transcripts
    "super-memory": 60.0, # 60 days for super-memory layers
    "all": 60.0,
}


# ── Temporal score adjustment ──────────────────────────────────────────────


def apply_temporal_decay(
    items: list[dict[str, Any]],
    timestamp_key: str = "timestamp",
    score_key: str = "score",
    corpus: str = "memory",
    half_life: float | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Apply exponential temporal decay to search result scores.

    Args:
        items: List of search result dicts
        timestamp_key: Dict key for ISO datetime or unix timestamp
        score_key: Dict key for score value (mutated in place)
        corpus: Corpus name for default half-life lookup
        half_life: Override half-life in days (None = use default for corpus)
        now: Reference time (default: UTC now)

    Returns:
        Same list with scores adjusted in-place
    """
    if not items:
        return items

    hl = half_life or DEFAULT_HALF_LIVES.get(corpus, 60.0)
    ref = now or datetime.now(timezone.utc)

    for item in items:
        ts = _extract_timestamp(item, timestamp_key)
        if ts is None:
            continue  # No timestamp = no decay adjustment

        age_days = max(0.0, (ref - ts).total_seconds() / 86400.0)
        decay_factor = math.exp(-age_days / hl)

        original_score = max(0.0, min(1.0, item.get(score_key, 0.0)))
        item[score_key] = original_score * decay_factor

        # Annotate decay info
        item["_decay"] = {
            "age_days": round(age_days, 1),
            "half_life_days": hl,
            "decay_factor": round(decay_factor, 4),
        }

    return items


def _extract_timestamp(item: dict[str, Any], key: str) -> datetime | None:
    """Extract datetime from item using various formats."""
    raw = item.get(key)
    if raw is None:
        return None

    # Unix timestamp (float/int)
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (OSError, ValueError):
            return None

    # ISO string
    if isinstance(raw, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

    # 'created_at' or 'updated_at' subkey
    for subkey in ("created_at", "updated_at", "timestamp"):
        val = item.get(subkey)
        if isinstance(val, str):
            return _extract_timestamp({"ts": val}, "ts")

    return None


# ── Freshness tier classifier ──────────────────────────────────────────────


def freshness_tier(age_days: float) -> str:
    """Classify a result's freshness tier."""
    if age_days <= 1:
        return "fresh"
    elif age_days <= 7:
        return "recent"
    elif age_days <= 30:
        return "normal"
    elif age_days <= 90:
        return "stale"
    else:
        return "archived"
