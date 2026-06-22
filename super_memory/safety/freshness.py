"""Memory freshness evaluation.

Ported from neural-memory v4.58.0 safety/freshness.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class FreshnessLevel(StrEnum):
    FRESH = "fresh"
    RECENT = "recent"
    AGING = "aging"
    STALE = "stale"
    ANCIENT = "ancient"


@dataclass(frozen=True)
class FreshnessResult:
    level: FreshnessLevel
    age_days: int
    warning: str | None
    should_verify: bool
    score: float


DEFAULT_THRESHOLDS = {
    FreshnessLevel.FRESH: 7,
    FreshnessLevel.RECENT: 30,
    FreshnessLevel.AGING: 90,
    FreshnessLevel.STALE: 365,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_freshness(
    created_at: datetime,
    reference_time: datetime | None = None,
    thresholds: dict[FreshnessLevel, int] | None = None,
) -> FreshnessResult:
    if reference_time is None:
        reference_time = utcnow()
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS
    age = reference_time - created_at
    age_days = max(0, age.days)
    if age_days < thresholds[FreshnessLevel.FRESH]:
        return FreshnessResult(FreshnessLevel.FRESH, age_days, None, False, 1.0)
    elif age_days < thresholds[FreshnessLevel.RECENT]:
        return FreshnessResult(FreshnessLevel.RECENT, age_days, None, False, 0.8)
    elif age_days < thresholds[FreshnessLevel.AGING]:
        return FreshnessResult(FreshnessLevel.AGING, age_days, f"[~] {age_days}d old — may have changed", True, 0.5)
    elif age_days < thresholds[FreshnessLevel.STALE]:
        return FreshnessResult(FreshnessLevel.STALE, age_days, f"[!] STALE: {age_days}d old — verify", True, 0.3)
    else:
        return FreshnessResult(FreshnessLevel.ANCIENT, age_days, f"[!!] ANCIENT: {age_days}d — likely outdated", True, 0.1)


def get_freshness_warning(created_at: datetime, reference_time: datetime | None = None) -> str | None:
    return evaluate_freshness(created_at, reference_time).warning


def format_age(age_days: int) -> str:
    if age_days == 0: return "today"
    elif age_days == 1: return "yesterday"
    elif age_days < 7: return f"{age_days} days ago"
    elif age_days < 30: return f"{age_days // 7} week{'s' if age_days // 7 > 1 else ''} ago"
    elif age_days < 365: return f"{age_days // 30} month{'s' if age_days // 30 > 1 else ''} ago"
    else: return f"{age_days // 365} year{'s' if age_days // 365 > 1 else ''} ago"


def get_freshness_indicator(level: FreshnessLevel) -> str:
    return {
        FreshnessLevel.FRESH: "[+]", FreshnessLevel.RECENT: "[+]",
        FreshnessLevel.AGING: "[~]", FreshnessLevel.STALE: "[!]", FreshnessLevel.ANCIENT: "[!!]",
    }.get(level, "[ ]")


@dataclass(frozen=True)
class MemoryFreshnessReport:
    total: int
    fresh: int
    recent: int
    aging: int
    stale: int
    ancient: int
    average_age_days: float
    oldest_days: int
    newest_days: int

    def summary(self) -> str:
        return (
            f"Total: {self.total} | "
            f"Fresh: {self.fresh} | Recent: {self.recent} | "
            f"Aging: {self.aging} | Stale: {self.stale} | Ancient: {self.ancient} | "
            f"Avg age: {self.average_age_days:.1f}d"
        )


def analyze_freshness(
    created_dates: list[datetime],
    reference_time: datetime | None = None,
) -> MemoryFreshnessReport:
    if not created_dates:
        return MemoryFreshnessReport(0, 0, 0, 0, 0, 0, 0, 0, 0)
    results = [evaluate_freshness(dt, reference_time) for dt in created_dates]
    ages = [r.age_days for r in results]
    return MemoryFreshnessReport(
        total=len(results),
        fresh=sum(1 for r in results if r.level == FreshnessLevel.FRESH),
        recent=sum(1 for r in results if r.level == FreshnessLevel.RECENT),
        aging=sum(1 for r in results if r.level == FreshnessLevel.AGING),
        stale=sum(1 for r in results if r.level == FreshnessLevel.STALE),
        ancient=sum(1 for r in results if r.level == FreshnessLevel.ANCIENT),
        average_age_days=sum(ages) / len(ages),
        oldest_days=max(ages),
        newest_days=min(ages),
    )
