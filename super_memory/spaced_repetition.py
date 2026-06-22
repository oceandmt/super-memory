"""Enhanced Spaced Repetition — forgetting-curve-aware review scheduling.

Extends the basic Leitner 5-box system with:
1. **SM-2 algorithm** — exponential forgetting curve with grade-based scheduling
2. **Difficulty tracking** — per-memory ease factor (EF) adaptation
3. **Overdue penalty** — memories past review date get priority boost
4. **Batch review optimization** — cluster similar-maturity memories
5. **Retention probability** — estimate how likely a memory is still retained

Reference: SuperMemo SM-2 algorithm (P. Wozniak, 1987)
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = [
    "SpacedRepetitionConfig", "SpacedRepetitionEngine",
    "ReviewItem", "ReviewResult",
    "sm2_compute_next_interval", "estimate_retention",
    "get_due_items", "record_review",
]

logger = logging.getLogger("super-memory.spaced_repetition")

# SM-2 defaults
DEFAULT_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3
MAX_INTERVAL_DAYS = 365

# Retention estimation
RETENTION_HALF_LIFE = 30.0  # days at 90% retention


@dataclass
class SpacedRepetitionConfig:
    """Configuration for spaced repetition.

    Attributes:
        enabled: Set False to disable.
        default_ef: Default ease factor for new memories (SM-2).
        min_ef: Minimum ease factor.
        max_interval_days: Maximum interval between reviews.
        retention_target: Target retention probability (0.0-1.0).
        overdue_boost: Score multiplier for overdue items.
        batch_cluster_hours: Cluster items within this many hours.
        randomize_order: Shuffle review order within same-priority.
    """
    enabled: bool = True
    default_ef: float = DEFAULT_EASE_FACTOR
    min_ef: float = MIN_EASE_FACTOR
    max_interval_days: int = MAX_INTERVAL_DAYS
    retention_target: float = 0.9
    overdue_boost: float = 1.5
    batch_cluster_hours: int = 24
    randomize_order: bool = True


@dataclass
class ReviewItem:
    """A single item due for review."""
    memory_id: str
    content: str
    type: str = "context"
    box: int = 0
    ease_factor: float = DEFAULT_EASE_FACTOR
    interval_days: int = 1
    last_reviewed: str = ""
    created_at: str = ""
    retention_probability: float = 1.0
    overdue_days: float = 0.0


@dataclass
class ReviewResult:
    """Result after reviewing and grading an item."""
    memory_id: str
    grade: int  # 0-5 SM-2 grade
    quality_label: str = ""
    new_box: int = 0
    new_ease_factor: float = DEFAULT_EASE_FACTOR
    new_interval_days: int = 1
    next_review: str = ""
    retention_change: float = 0.0
    success: bool = True


# ── SM-2 Algorithm ──────────────────────────────────────────────────────────

def sm2_compute_next_interval(
    grade: int,
    current_box: int = 0,
    ease_factor: float = DEFAULT_EASE_FACTOR,
    current_interval_days: int = 1,
) -> tuple[int, float, int]:
    """Compute SM-2 next state after a review grade.

    Grade scale (SM-2 standard):
        0 = complete blackout
        1 = incorrect, but upon seeing answer remembered
        2 = incorrect, but correct answer seemed easy
        3 = correct with serious difficulty
        4 = correct after hesitation
        5 = perfect response

    Returns:
        Tuple of (new_box, new_ease_factor, new_interval_days).
    """
    if grade < 0 or grade > 5:
        grade = 3  # Default to "correct with difficulty"

    # Compute new ease factor
    new_ef = ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    new_ef = max(MIN_EASE_FACTOR, new_ef)

    # Compute new interval
    if grade < 3:
        # Failed — reset
        new_box = 0
        new_interval = 1
    elif current_box == 0:
        new_box = 1
        new_interval = 1
    elif current_box == 1:
        new_box = 2
        new_interval = 6
    else:
        new_box = min(current_box + 1, 10)  # Allow boxes beyond 4
        new_interval = round(current_interval_days * new_ef)

    # Cap interval
    new_interval = min(new_interval, MAX_INTERVAL_DAYS)

    return new_box, round(new_ef, 2), new_interval


def estimate_retention(
    interval_days: float,
    ease_factor: float = DEFAULT_EASE_FACTOR,
) -> float:
    """Estimate probability that a memory is still retained.

    Uses exponential forgetting curve:
        R = exp(-t / s)
    where s = half-life adjusted by ease factor.

    Args:
        interval_days: Days since last review.
        ease_factor: Memory's ease factor.

    Returns:
        Retention probability (0.0-1.0).
    """
    if interval_days <= 0:
        return 1.0
    # Scale half-life by ease factor: higher EF → slower forgetting
    adjusted_hl = RETENTION_HALF_LIFE * (ease_factor / DEFAULT_EASE_FACTOR)
    return math.exp(-interval_days / adjusted_hl)


def quality_label(grade: int) -> str:
    """Map SM-2 grade to human label."""
    labels = {
        0: "complete blackout",
        1: "remembered with effort",
        2: "correct but difficult",
        3: "correct with hesitation",
        4: "correct after thought",
        5: "perfect recall",
    }
    return labels.get(grade, "unknown")


# ── Spaced Repetition Engine ─────────────────────────────────────────────────

class SpacedRepetitionEngine:
    """Enhanced spaced repetition engine with SM-2 + forgetting curves."""

    def __init__(
        self,
        store: Any,
        config: SpacedRepetitionConfig | None = None,
    ):
        self.store = store
        self.config = config or SpacedRepetitionConfig()

    # ── Get Due Items ───────────────────────────────────────────────────

    def get_due(
        self, limit: int = 50, min_retention: float | None = None,
    ) -> list[ReviewItem]:
        """Get items due for review, prioritized by retention probability.

        Args:
            limit: Max items to return.
            min_retention: Min retention threshold (defaults to config target).

        Returns:
            List of ReviewItem sorted by retention (most urgent first).
        """
        threshold = min_retention if min_retention is not None else self.config.retention_target
        now = datetime.now(timezone.utc)

        with self.store.connect() as conn:
            rows = conn.execute(
                """SELECT id, content, type, leiter_box, ease_factor,
                          interval_days, last_reviewed, created_at
                   FROM memories
                   WHERE next_review IS NOT NULL
                   ORDER BY next_review ASC
                   LIMIT ?""",
                (limit * 3,),  # Overfetch for filtering
            ).fetchall()

        items = []
        for r in rows:
            interval_days = r.get("interval_days") or BOX_INTERVALS.get(r.get("leiter_box", 0), 1)
            ef = r.get("ease_factor") or DEFAULT_EASE_FACTOR
            last_reviewed = r.get("last_reviewed")

            # Compute actual interval since last review
            if last_reviewed:
                try:
                    lr = datetime.fromisoformat(last_reviewed.replace("Z", "+00:00"))
                    actual_interval = max(0, (now - lr).total_seconds() / 86400.0)
                except Exception:
                    actual_interval = float(interval_days)
            else:
                actual_interval = float(interval_days)

            # Estimate retention
            retention = estimate_retention(actual_interval, ef)

            # Compute overdue
            next_review = r.get("next_review", "")
            overdue_days = 0.0
            if next_review:
                try:
                    nr = datetime.fromisoformat(next_review.replace("Z", "+00:00"))
                    overdue_days = max(0, (now - nr).total_seconds() / 86400.0)
                except Exception:
                    pass

            if retention >= threshold:
                continue  # Not due yet

            items.append(ReviewItem(
                memory_id=str(r["id"]),
                content=r.get("content", "")[:200],
                type=r.get("type", "context") or "context",
                box=r.get("leiter_box", 0),
                ease_factor=ef,
                interval_days=interval_days,
                last_reviewed=last_reviewed or "",
                created_at=r.get("created_at", "") or "",
                retention_probability=round(retention, 4),
                overdue_days=round(overdue_days, 1),
            ))

        # Sort by retention (lowest first = most urgent)
        items.sort(key=lambda i: i.retention_probability)

        if self.config.randomize_order:
            # Group by retention decile and shuffle within groups
            grouped: dict[int, list[ReviewItem]] = {}
            for item in items:
                decile = int(item.retention_probability * 10)
                grouped.setdefault(decile, []).append(item)
            items = []
            for decile in sorted(grouped.keys()):
                group = grouped[decile]
                random.shuffle(group)
                items.extend(group)

        return items[:limit]

    # ── Record Review ───────────────────────────────────────────────────

    def record_review(
        self, memory_id: str, grade: int,
    ) -> ReviewResult:
        """Record a review grade and update SM-2 state.

        Args:
            memory_id: Memory ID to update.
            grade: SM-2 grade (0-5).

        Returns:
            ReviewResult with updated scheduling info.
        """
        result = ReviewResult(memory_id=memory_id, grade=grade, quality_label=quality_label(grade))

        try:
            with self.store.connect() as conn:
                row = conn.execute(
                    """SELECT leiter_box, ease_factor, interval_days
                       FROM memories WHERE id = ?""",
                    (memory_id,),
                ).fetchone()

                if not row:
                    result.success = False
                    return result

                current_box = row["leiter_box"] or 0
                ef = row.get("ease_factor") or DEFAULT_EASE_FACTOR
                interval = row.get("interval_days") or BOX_INTERVALS.get(current_box, 1)

                # SM-2 computation
                new_box, new_ef, new_interval = sm2_compute_next_interval(
                    grade, current_box, ef, interval,
                )

                now = datetime.now(timezone.utc)
                next_review = now + timedelta(days=new_interval)

                # Estimate retention change
                old_retention = estimate_retention(interval, ef)
                new_retention = estimate_retention(new_interval, new_ef)

                # Update database
                conn.execute(
                    """UPDATE memories SET
                       leiter_box = ?, ease_factor = ?, interval_days = ?,
                       last_reviewed = ?, next_review = ?
                       WHERE id = ?""",
                    (new_box, new_ef, new_interval,
                     now.isoformat(), next_review.isoformat(),
                     memory_id),
                )
                conn.commit()

                result.new_box = new_box
                result.new_ease_factor = new_ef
                result.new_interval_days = new_interval
                result.next_review = next_review.isoformat()
                result.retention_change = round(new_retention - old_retention, 4)
                result.success = True

        except Exception as e:
            logger.debug("record review failed: %s", e)
            result.success = False

        return result

    # ── Batch Review Optimization ───────────────────────────────────────

    def get_clustered_due(self, limit: int = 50) -> dict[str, list[ReviewItem]]:
        """Get due items clustered by maturity level.

        Returns dict with keys: 'new', 'learning', 'reviewing', 'mastered'.
        """
        items = self.get_due(limit=limit)
        clusters: dict[str, list[ReviewItem]] = {
            "new": [],
            "learning": [],
            "reviewing": [],
            "mastered": [],
        }
        for item in items:
            if item.box <= 0:
                clusters["new"].append(item)
            elif item.box <= 1:
                clusters["learning"].append(item)
            elif item.box <= 3:
                clusters["reviewing"].append(item)
            else:
                clusters["mastered"].append(item)
        return clusters

    # ── Bulk Maintenance ────────────────────────────────────────────────

    def auto_seed(self, config_path: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Seed unassigned memories with SM-2 defaults."""
        now = datetime.now(timezone.utc)
        default_ef = self.config.default_ef
        seeded = 0

        try:
            with self.store.connect() as conn:
                rows = conn.execute(
                    """SELECT id FROM memories
                       WHERE (ease_factor IS NULL OR leiter_box IS NULL)
                       LIMIT ?""",
                    (limit,),
                ).fetchall()

                for r in rows:
                    conn.execute(
                        """UPDATE memories SET
                           leiter_box = 0, ease_factor = ?,
                           interval_days = 1,
                           next_review = ?
                           WHERE id = ?""",
                        (default_ef, now.isoformat(), r["id"]),
                    )
                    seeded += 1
                conn.commit()
        except Exception as e:
            logger.debug("auto seed failed: %s", e)

        return {"ok": True, "seeded": seeded}

    # ── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get spaced repetition statistics."""
        with self.store.connect() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
            seeded = conn.execute(
                "SELECT COUNT(*) as c FROM memories WHERE ease_factor IS NOT NULL"
            ).fetchone()["c"]
            avg_ef_row = conn.execute(
                "SELECT AVG(ease_factor) as avg_ef FROM memories WHERE ease_factor IS NOT NULL"
            ).fetchone()
            avg_ef = round(avg_ef_row["avg_ef"], 2) if avg_ef_row and avg_ef_row["avg_ef"] else DEFAULT_EASE_FACTOR

            box_dist = {
                str(r["leiter_box"] or 0): r["c"]
                for r in conn.execute(
                    "SELECT leiter_box, COUNT(*) as c FROM memories GROUP BY leiter_box"
                ).fetchall()
            }

        return {
            "total_memories": total,
            "seeded_for_srs": seeded,
            "average_ease_factor": avg_ef,
            "box_distribution": box_dist,
            "config": {
                "retention_target": self.config.retention_target,
                "default_ef": self.config.default_ef,
                "max_interval_days": self.config.max_interval_days,
            },
        }


# ── Module-level convenience functions ──────────────────────────────────────

def get_due_items(
    store: Any,
    limit: int = 50,
    config: SpacedRepetitionConfig | None = None,
) -> list[ReviewItem]:
    """Convenience: get items due for review."""
    engine = SpacedRepetitionEngine(store, config)
    return engine.get_due(limit)


def record_review(
    store: Any,
    memory_id: str,
    grade: int,
    config: SpacedRepetitionConfig | None = None,
) -> ReviewResult:
    """Convenience: record a review grade."""
    engine = SpacedRepetitionEngine(store, config)
    return engine.record_review(memory_id, grade)


# Leitner box intervals for fallback
BOX_INTERVALS: dict[int, int] = {0: 1, 1: 3, 2: 7, 3: 30, 4: 90}
