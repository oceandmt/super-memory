"""Trigger engine — auto-capture patterns for save pipeline.

Ported from neural-memory v4.58.0 core/trigger_engine.py.
Checks content against registered triggers for auto-capture/save.
"""
from __future__ import annotations

__all__ = ["TriggerType", "TriggerResult", "check_triggers", "estimate_session_tokens"]
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger("super-memory.trigger")

class TriggerType(StrEnum):
    KEYWORD = "keyword"
    PATTERN = "pattern"
    FREQUENCY = "frequency"
    PERIODIC = "periodic"

@dataclass
class TriggerResult:
    matched: bool
    trigger_type: TriggerType | None = None
    trigger_name: str = ""
    confidence: float = 0.0
    extracted: list[str] = None

    def __post_init__(self) -> None:
        """Validate trigger result after creation."""
        if self.extracted is None:
            self.extracted = []


# Built-in trigger patterns
_TRIGGERS = [
    (re.compile(r"(?:production|critical|urgent)\s+(?:issue|bug|incident|outage)", re.IGNORECASE), "critical_incident", 0.9),
    (re.compile(r"(?:decision|decided|chosen)\s+(?:to\s+)?(?:use|adopt|implement|migrate|upgrade)", re.IGNORECASE), "decision_made", 0.8),
    (re.compile(r"(?:lesson|learned|key\s+takeaway|insight)", re.IGNORECASE), "lesson_learned", 0.85),
    (re.compile(r"(?:workflow|process|pipeline|deploy)\s*(?:change|update|fix|improve)", re.IGNORECASE), "workflow_change", 0.7),
    (re.compile(r"(?:TODO|FIXME|HACK|XXX|BUG)\s*[:()]", re.IGNORECASE), "code_annotation", 0.75),
    (re.compile(r"(?:architecture|design|pattern)\s+(?:decision|change|review)", re.IGNORECASE), "architecture_change", 0.8),
]


def check_triggers(content: str) -> list[TriggerResult]:
    """Check content against all registered triggers."""
    try:
        if not content or not isinstance(content, str):
            return []
        results = []
        for pattern, name, confidence in _TRIGGERS:
            matches = pattern.findall(content)
            if matches:
                results.append(TriggerResult(
                    matched=True, trigger_type=TriggerType.PATTERN,
                    trigger_name=name, confidence=confidence,
                    extracted=list(set(matches))[:5],
                ))
        return results
    except Exception:
        return []


def estimate_session_tokens(content: str) -> int:
    """Rough token estimate for session context."""
    if not content:
        return 0
    return len(content) // 4  # ~4 chars per token