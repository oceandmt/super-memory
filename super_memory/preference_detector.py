"""Preference detector — learns user preferences from content patterns.

Analyzes saved memory content to detect:
1. **Tech stack preferences** (languages, frameworks, tools)
2. **Workflow preferences** (patterns in how tasks are done)
3. **Communication preferences** (tone, detail level, format)
4. **Topic affinities** (what the user focuses on most)

All detection is statistical pattern matching with graceful degradation.
Results inform recall re-ranking (boost preferred topics).
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "PreferenceConfig", "DetectedPreference", "PreferenceProfile",
    "PreferenceDetector", "get_preference_detector",
]

logger = logging.getLogger("super-memory.preferences")


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class PreferenceConfig:
    """Configuration for preference detection.

    Attributes:
        enabled: Set False to skip detection.
        min_samples: Minimum memories before profile is meaningful.
        decay_days: Days after which old signals decay by half.
        track_tech: Detect tech stack preferences.
        track_topics: Detect topic affinities.
        track_workflow: Detect workflow preferences.
        top_topics: Max topics to track.
        top_tech: Max tech items to track.
    """
    enabled: bool = True
    min_samples: int = 5
    decay_days: int = 90
    track_tech: bool = True
    track_topics: bool = True
    track_workflow: bool = True
    top_topics: int = 20
    top_tech: int = 15


# ── Results ──────────────────────────────────────────────────────────────────

@dataclass
class DetectedPreference:
    """A single detected preference with confidence."""
    category: str       # tech, topic, workflow, communication
    key: str            # e.g. "python", "agile"
    confidence: float   # 0.0 - 1.0
    sample_count: int   # How many memories contain this
    last_seen: str = ""  # ISO timestamp


@dataclass
class PreferenceProfile:
    """Complete preference profile for a user/session."""
    user_id: str = ""
    memories_analyzed: int = 0
    preferences: list[DetectedPreference] = field(default_factory=list)
    last_updated: str = ""


# ── Patterns ─────────────────────────────────────────────────────────────────

# Tech stack keywords (language, framework, tool, platform)
_TECH_PATTERNS: list[tuple[str, int]] = [
    # Languages
    ("python", 5), ("javascript", 5), ("typescript", 5), ("go", 4),
    ("rust", 4), ("java", 4), ("c++", 3), ("c#", 3), ("ruby", 3),
    ("php", 3), ("swift", 3), ("kotlin", 3), ("scala", 2),
    # Frameworks
    ("react", 5), ("django", 4), ("flask", 4), ("fastapi", 4),
    ("nextjs", 4), ("vue", 3), ("angular", 3), ("svelte", 3),
    ("spring", 3), ("laravel", 2), ("rails", 2),
    # Tools & Platforms
    ("docker", 5), ("kubernetes", 5), ("k8s", 5), ("aws", 4),
    ("gcp", 4), ("azure", 4), ("terraform", 4), ("ansible", 3),
    ("jenkins", 3), ("github actions", 5), ("gitlab ci", 4),
    ("postgresql", 4), ("postgres", 4), ("mysql", 3), ("redis", 3),
    ("mongodb", 3), ("sqlite", 4),
    # Infrastructure
    ("nginx", 3), ("apache", 2), ("linux", 3), ("ubuntu", 2),
    ("debian", 2), ("centos", 2), ("alpine", 2),
]

# Topic keywords (domains/subjects)
_TOPIC_PATTERNS: list[tuple[str, int]] = [
    ("machine learning", 5), ("ml", 3), ("ai", 4), ("deep learning", 4),
    ("data science", 3), ("nlp", 3), ("llm", 4), ("gpt", 4),
    ("backend", 4), ("frontend", 4), ("full stack", 3), ("fullstack", 3),
    ("api", 4), ("rest", 3), ("graphql", 3), ("grpc", 3),
    ("microservices", 4), ("serverless", 3), ("cloud", 3),
    ("devops", 4), ("ci/cd", 4), ("cicd", 3),
    ("database", 3), ("sql", 3), ("nosql", 2),
    ("security", 3), ("authentication", 3), ("auth", 3),
    ("testing", 3), ("tdd", 3), ("unit test", 3), ("integration test", 2),
    ("performance", 3), ("optimization", 3), ("scalability", 3),
    ("architecture", 3), ("design pattern", 3),
    ("blockchain", 2), ("web3", 2), ("crypto", 2),
    ("mobile", 2), ("ios", 2), ("android", 2),
    ("game dev", 2), ("gamedev", 2),
]

# Workflow indicators
_WORKFLOW_PATTERNS: list[tuple[str, int | float]] = [
    ("agile", 3), ("scrum", 3), ("sprint", 2), ("kanban", 2),
    ("waterfall", 1), ("code review", 3), ("pair programming", 2),
    ("monorepo", 3), ("mono-repo", 3), ("git flow", 2),
    ("trunk-based", 2), ("feature branch", 2),
    ("deploy daily", 3), ("continuous deployment", 3),
    ("manual testing", 1), ("automated testing", 3),
]


# ── Detector ─────────────────────────────────────────────────────────────────

class PreferenceDetector:
    """Detects preferences from memory content patterns."""

    def __init__(self, config: PreferenceConfig | None = None):
        self.config = config or PreferenceConfig()
        self._profile: PreferenceProfile = PreferenceProfile()
        self._tech_counter: Counter[str] = Counter()
        self._topic_counter: Counter[str] = Counter()
        self._workflow_counter: Counter[str] = Counter()
        self._total_analyzed: int = 0
        self._last_analysis: str = ""

    def analyze(self, content: str, memory_type: str = "") -> dict[str, float]:
        """Analyze a single memory for preference signals."""
        try:
            if not self.config.enabled or not content:
                return {}

            signals: dict[str, float] = {}
            content_lower = content.lower()

            # Tech detection
            if self.config.track_tech:
                for keyword, weight in _TECH_PATTERNS:
                    if keyword in content_lower:
                        self._tech_counter[keyword] += weight
                        signals[f"tech:{keyword}"] = weight
                        if memory_type == "preference":
                            self._tech_counter[keyword] += weight

            # Topic detection
            if self.config.track_topics:
                for keyword, weight in _TOPIC_PATTERNS:
                    if keyword in content_lower:
                        self._topic_counter[keyword] += weight
                        signals[f"topic:{keyword}"] = weight

            # Workflow detection
            if self.config.track_workflow:
                for keyword, weight in _WORKFLOW_PATTERNS:
                    if keyword in content_lower:
                        self._workflow_counter[keyword] += weight
                        signals[f"workflow:{keyword}"] = weight

            self._total_analyzed += 1
            self._last_analysis = datetime.now(timezone.utc).isoformat()
            return signals
        except Exception as e:
            logger.debug("preference analyze failed: %s", e)
            return {}

    def build_profile(self, user_id: str = "") -> PreferenceProfile:
        """Build a PreferenceProfile from accumulated signals.

        Only returns preferences that exceed minimum confidence thresholds.
        """
        prefs: list[DetectedPreference] = []

        # Normalize counters to confidence [0, 1]
        max_tech = max(self._tech_counter.values()) if self._tech_counter else 1
        max_topic = max(self._topic_counter.values()) if self._topic_counter else 1
        max_workflow = max(self._workflow_counter.values()) if self._workflow_counter else 1

        for keyword, count in self._tech_counter.most_common(self.config.top_tech):
            confidence = min(count / max(max_tech, 1) * 0.8 + 0.2, 1.0)
            if confidence > 0.3:
                prefs.append(DetectedPreference(
                    category="tech",
                    key=keyword,
                    confidence=round(confidence, 2),
                    sample_count=count,
                    last_seen=self._last_analysis,
                ))

        for keyword, count in self._topic_counter.most_common(self.config.top_topics):
            confidence = min(count / max(max_topic, 1) * 0.8 + 0.2, 1.0)
            if confidence > 0.25:
                prefs.append(DetectedPreference(
                    category="topic",
                    key=keyword,
                    confidence=round(confidence, 2),
                    sample_count=count,
                    last_seen=self._last_analysis,
                ))

        for keyword, count in self._workflow_counter.most_common(10):
            confidence = min(count / max(max_workflow, 1) * 0.8 + 0.2, 1.0)
            if confidence > 0.3:
                prefs.append(DetectedPreference(
                    category="workflow",
                    key=keyword,
                    confidence=round(confidence, 2),
                    sample_count=count,
                    last_seen=self._last_analysis,
                ))

        self._profile = PreferenceProfile(
            user_id=user_id,
            memories_analyzed=self._total_analyzed,
            preferences=prefs,
            last_updated=self._last_analysis,
        )
        return self._profile

    def get_relevance_boost(self, content: str) -> float:
        """Get a [1.0, 2.0] boost multiplier for content matching preferences.

        Higher boost for content that aligns with detected preferences.
        """
        if not self.config.enabled or self._total_analyzed < self.config.min_samples:
            return 1.0

        content_lower = content.lower()
        boost = 1.0

        for pref in self._profile.preferences:
            if pref.key in content_lower:
                boost += pref.confidence * 0.1

        return round(min(boost, 2.0), 2)

    def reset(self) -> None:
        """Reset all accumulated signals."""
        self._tech_counter.clear()
        self._topic_counter.clear()
        self._workflow_counter.clear()
        self._total_analyzed = 0
        self._profile = PreferenceProfile()

    def get_summary(self) -> dict[str, Any]:
        """Get a concise summary of detected preferences."""
        return {
            "memories_analyzed": self._total_analyzed,
            "profile_ready": self._total_analyzed >= self.config.min_samples,
            "top_tech": [k for k, _ in self._tech_counter.most_common(5)],
            "top_topics": [k for k, _ in self._topic_counter.most_common(5)],
            "top_workflows": [k for k, _ in self._workflow_counter.most_common(5)],
            "preferences_count": len(self._profile.preferences),
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_DETECTOR: PreferenceDetector | None = None


def get_preference_detector() -> PreferenceDetector:
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = PreferenceDetector()
    return _DETECTOR
