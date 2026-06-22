"""Memory maturation lifecycle — STM → Working → Episodic → Semantic.

Inspired by neural-memory v4.58.0 engine/memory_stages.py.
Implements biologically-inspired memory consolidation stages:

- SHORT_TERM: First ~30 min, fragile, decays 5x faster
- WORKING: ~30 min to 4 hours, still volatile, decays 2x faster
- EPISODIC: 4 hours to ~3 days, normal decay
- SEMANTIC: 3+ days with spacing effect, resistant to forgetting (0.3x decay)

The spacing effect requires reinforcement across 2+ distinct days
for promotion from EPISODIC to SEMANTIC, modeling how spaced
repetition strengthens long-term memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any


# ── Memory Stage Definition ───────────────────────────────────────────────────

class MemoryStage(StrEnum):
    """Memory maturation stages in order of consolidation."""

    SHORT_TERM = "stm"
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


# Decay multipliers per stage (higher = faster forgetting)
STAGE_DECAY_MULTIPLIERS: dict[MemoryStage, float] = {
    MemoryStage.SHORT_TERM: 5.0,
    MemoryStage.WORKING: 2.0,
    MemoryStage.EPISODIC: 1.0,
    MemoryStage.SEMANTIC: 0.3,
}

# Time thresholds for automatic stage promotion (in seconds)
STAGE_PROMOTION_THRESHOLDS: dict[MemoryStage, float] = {
    MemoryStage.SHORT_TERM: 1800.0,      # 30 min → Working
    MemoryStage.WORKING: 14400.0,         # 4 hours → Episodic
    MemoryStage.EPISODIC: 259200.0,       # 3 days → Semantic (requires 2+ distinct days)
}

# Reinforcement count needed for semantic promotion
SEMANTIC_MIN_REINFORCEMENTS = 2
SEMANTIC_MIN_SEPARATE_DAYS = 2


@dataclass
class StageRecord:
    """Memory stage tracking record stored in metadata."""
    stage: MemoryStage = MemoryStage.SHORT_TERM
    created_at: str = ""  # ISO timestamp
    promoted_at: list[str] = field(default_factory=list)  # ISO timestamps for each promotion
    reinforcements: int = 0   # Access/rehearsal count
    distinct_reinforcement_dates: set[str] = field(default_factory=set)  # YYYY-MM-DD dates
    last_reinforced_at: str = ""


# ── Stage Helpers ─────────────────────────────────────────────────────────────

def compute_stage_age_seconds(created_at: str, now: datetime | None = None) -> float:
    """Compute age in seconds of a memory."""
    if not created_at:
        return 0.0
    try:
        created = datetime.fromisoformat(created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        return (now - created).total_seconds()
    except (ValueError, TypeError):
        return 0.0


def get_decay_multiplier(stage: MemoryStage | str) -> float:
    """Get decay multiplier for a stage."""
    if isinstance(stage, str):
        try:
            stage = MemoryStage(stage)
        except ValueError:
            return 1.0
    return STAGE_DECAY_MULTIPLIERS.get(stage, 1.0)


def get_promotion_threshold(stage: MemoryStage) -> float:
    """Get age threshold in seconds for promoting from this stage."""
    return STAGE_PROMOTION_THRESHOLDS.get(stage, float("inf"))


def compute_next_stage(
    current_stage: MemoryStage | str,
    age_seconds: float,
    reinforcements: int = 0,
    distinct_dates: set[str] | None = None,
) -> MemoryStage:
    """Determine the next stage based on age and reinforcement count."""
    if isinstance(current_stage, str):
        try:
            current_stage = MemoryStage(current_stage)
        except ValueError:
            current_stage = MemoryStage.SHORT_TERM

    if current_stage == MemoryStage.SHORT_TERM:
        if age_seconds >= STAGE_PROMOTION_THRESHOLDS[MemoryStage.SHORT_TERM]:
            return MemoryStage.WORKING

    elif current_stage == MemoryStage.WORKING:
        if age_seconds >= STAGE_PROMOTION_THRESHOLDS[MemoryStage.WORKING]:
            return MemoryStage.EPISODIC

    elif current_stage == MemoryStage.EPISODIC:
        if age_seconds >= STAGE_PROMOTION_THRESHOLDS[MemoryStage.EPISODIC]:
            distinct = distinct_dates or set()
            if len(distinct) >= SEMANTIC_MIN_SEPARATE_DAYS and reinforcements >= SEMANTIC_MIN_REINFORCEMENTS:
                return MemoryStage.SEMANTIC

    # No promotion needed
    return current_stage


def promote_stage(
    current_stage: MemoryStage | str,
    metadata: dict[str, Any],
    now: datetime | None = None,
) -> tuple[MemoryStage, dict[str, Any], bool]:
    """Try to promote a memory's stage. Returns (new_stage, updated_metadata, promoted).

    Reads stage info from metadata['memory_stage'] dict.
    Writes back updated stage info.
    """
    if isinstance(current_stage, str):
        try:
            current_stage = MemoryStage(current_stage)
        except ValueError:
            current_stage = MemoryStage.SHORT_TERM

    now = now or datetime.now(timezone.utc)
    stage_info = metadata.get("memory_stage", {})
    if isinstance(stage_info, str):
        try:
            stage_info = json.loads(stage_info)
        except (json.JSONDecodeError, TypeError):
            stage_info = {}

    created_at = stage_info.get("created_at", metadata.get("created_at", ""))
    if not created_at:
        created_at = now.isoformat()

    age = compute_stage_age_seconds(created_at, now)
    reinforcements = stage_info.get("reinforcements", 0)
    distinct_dates = set(stage_info.get("distinct_reinforcement_dates", []))

    next_stage = compute_next_stage(current_stage, age, reinforcements, distinct_dates)

    if next_stage == current_stage:
        return current_stage, metadata, False

    # Promote!
    promoted_at_list = stage_info.get("promoted_at", [])
    promoted_at_list.append(now.isoformat())

    metadata["memory_stage"] = {
        "stage": next_stage.value,
        "created_at": created_at,
        "promoted_at": promoted_at_list,
        "reinforcements": reinforcements,
        "distinct_reinforcement_dates": sorted(distinct_dates),
        "last_reinforced_at": stage_info.get("last_reinforced_at", ""),
    }

    return next_stage, metadata, True


def record_reinforcement(metadata: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Record a reinforcement (access/recall) event for a memory.

    Updates reinforcement count and distinct dates.
    Returns updated metadata.
    """
    now = now or datetime.now(timezone.utc)
    stage_info = metadata.get("memory_stage", {})
    if isinstance(stage_info, str):
        try:
            stage_info = json.loads(stage_info)
        except (json.JSONDecodeError, TypeError):
            stage_info = {}

    stage_info["reinforcements"] = stage_info.get("reinforcements", 0) + 1
    stage_info["last_reinforced_at"] = now.isoformat()

    distinct = set(stage_info.get("distinct_reinforcement_dates", []))
    distinct.add(now.strftime("%Y-%m-%d"))
    stage_info["distinct_reinforcement_dates"] = sorted(distinct)

    if "created_at" not in stage_info:
        stage_info["created_at"] = metadata.get("created_at", now.isoformat())

    metadata["memory_stage"] = stage_info
    return metadata
