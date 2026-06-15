"""Dialectic reasoning engine — derives insights from turns.

Local deterministic implementation of Honcho-style dialectic reasoning.
No LLM required; uses pattern detection to extract preferences, goals, habits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .peer import PeerFact, PeerModel


@dataclass
class DialecticResult:
    facts: list[PeerFact] = field(default_factory=list)
    preferences: list[PeerFact] = field(default_factory=list)
    habits: list[PeerFact] = field(default_factory=list)
    goals: list[PeerFact] = field(default_factory=list)
    blockers: list[PeerFact] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    confidence: float = 0.5
    depth: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": [f.__dict__ for f in self.facts],
            "preferences": [f.__dict__ for f in self.preferences],
            "habits": [f.__dict__ for f in self.habits],
            "goals": [f.__dict__ for f in self.goals],
            "blockers": [f.__dict__ for f in self.blockers],
            "insights": self.insights,
            "confidence": self.confidence,
            "depth": self.depth,
            "metadata": self.metadata,
        }


# Pattern groups
PREFERENCE_PATTERNS = [
    re.compile(r'\b(?:i|boss|user)\s+(?:prefer|prefers|like|likes|want|wants)\s+(.+)', re.I),
    re.compile(r'\b(?:default|always)\s+(?:to|use|prefer)\s+(.+)', re.I),
    re.compile(r'\b(?:don\'t|do not|never)\s+(.+)', re.I),
]

GOAL_PATTERNS = [
    re.compile(r'\b(?:need to|should|must|todo|implement|build|create|deploy|finish)\s+(.+)', re.I),
    re.compile(r'\b(?:goal|objective|target)\s*[:\-]\s*(.+)', re.I),
    re.compile(r'\b(?:hãy|cần|phải|triển khai|tạo|làm)\s+(.+)', re.I),
]

BLOCKER_PATTERNS = [
    re.compile(r'\b(?:blocked|blocker|stuck|failed|error|bug|crash|timeout|sigterm)\b[:\-]?\s*(.*)', re.I),
    re.compile(r'\b(?:lỗi|kẹt|bị gián đoạn|không chạy|fail)\b[:\-]?\s*(.*)', re.I),
]

HABIT_PATTERNS = [
    re.compile(r'\b(?:usually|often|always|typically|normally)\s+(.+)', re.I),
    re.compile(r'\b(?:thường|luôn|hay)\s+(.+)', re.I),
]

FACT_PATTERNS = [
    re.compile(r'\b(.+?)\s+(?:is|are|was|were|has|have|uses|runs)\s+(.+)', re.I),
    re.compile(r'\b(.+?)\s+(?:là|có|dùng|chạy)\s+(.+)', re.I),
]


class DialecticEngine:
    """Local deterministic dialectic reasoning."""

    def analyze_turn(
        self,
        user_msg: str,
        assistant_msg: str = "",
        peer_model: PeerModel | None = None,
        depth: int = 2,
    ) -> DialecticResult:
        """Analyze a conversation turn and derive peer updates.
        
        Depth 1: Direct facts/preferences/goals from user message.
        Depth 2: Session-scoped patterns + assistant outcome.
        Depth 3: Deep insights/hypotheses from combined context.
        """
        result = DialecticResult(depth=depth, metadata={"user_len": len(user_msg), "assistant_len": len(assistant_msg)})
        
        # Pass 1: Direct extraction
        result.facts.extend(self._extract_facts(user_msg))
        result.preferences.extend(self._extract_preferences(user_msg))
        result.goals.extend(self._extract_goals(user_msg))
        result.blockers.extend(self._extract_blockers(user_msg + "\n" + assistant_msg))
        result.habits.extend(self._extract_habits(user_msg))
        
        # Pass 2: Session-scoped patterns
        if depth >= 2:
            result.insights.extend(self._session_insights(user_msg, assistant_msg, peer_model))
            # If assistant completed a goal, lower confidence but save as fact
            if any(word in assistant_msg.lower() for word in ["done", "completed", "verified", "deployed", "xong", "đã"]):
                result.facts.append(PeerFact(
                    content="Recent requested task appears to have progressed or completed",
                    type="fact",
                    confidence=0.6,
                    source="dialectic:assistant_outcome",
                ))
        
        # Pass 3: Deep insights/hypotheses
        if depth >= 3:
            result.insights.extend(self._deep_insights(user_msg, assistant_msg, peer_model))
        
        # Confidence based on extracted volume and message clarity
        total_items = sum(len(x) for x in [result.facts, result.preferences, result.goals, result.blockers, result.habits])
        result.confidence = min(0.9, 0.4 + total_items * 0.1 + (0.1 if result.insights else 0))
        
        return result

    def apply_to_peer(self, peer_model: PeerModel, result: DialecticResult) -> PeerModel:
        """Apply dialectic result to peer model."""
        for fact in result.facts + result.preferences + result.habits + result.goals + result.blockers:
            peer_model.add_fact(fact)
        return peer_model

    def _extract_preferences(self, text: str) -> list[PeerFact]:
        out: list[PeerFact] = []
        for pattern in PREFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                content = match.group(1).strip().rstrip(".")
                if len(content) >= 5:
                    out.append(PeerFact(content=content, type="preference", confidence=0.7, source="dialectic:preference"))
        return out[:5]

    def _extract_goals(self, text: str) -> list[PeerFact]:
        out: list[PeerFact] = []
        for pattern in GOAL_PATTERNS:
            for match in pattern.finditer(text):
                content = match.group(1).strip().rstrip(".")
                if len(content) >= 5:
                    out.append(PeerFact(content=content, type="goal", confidence=0.75, source="dialectic:goal"))
        return out[:5]

    def _extract_blockers(self, text: str) -> list[PeerFact]:
        out: list[PeerFact] = []
        for pattern in BLOCKER_PATTERNS:
            for match in pattern.finditer(text):
                content = match.group(0).strip().rstrip(".")
                if len(content) >= 5:
                    out.append(PeerFact(content=content, type="blocker", confidence=0.8, source="dialectic:blocker"))
        return out[:5]

    def _extract_habits(self, text: str) -> list[PeerFact]:
        out: list[PeerFact] = []
        for pattern in HABIT_PATTERNS:
            for match in pattern.finditer(text):
                content = match.group(1).strip().rstrip(".")
                if len(content) >= 5:
                    out.append(PeerFact(content=content, type="habit", confidence=0.65, source="dialectic:habit"))
        return out[:5]

    def _extract_facts(self, text: str) -> list[PeerFact]:
        out: list[PeerFact] = []
        for pattern in FACT_PATTERNS:
            for match in pattern.finditer(text):
                content = match.group(0).strip().rstrip(".")
                if 8 <= len(content) <= 200:
                    out.append(PeerFact(content=content, type="fact", confidence=0.6, source="dialectic:fact"))
        return out[:5]

    def _session_insights(self, user_msg: str, assistant_msg: str, peer_model: PeerModel | None) -> list[str]:
        insights: list[str] = []
        combined = (user_msg + "\n" + assistant_msg).lower()
        if "super-memory" in combined or "mempalace" in combined or "honcho" in combined:
            insights.append("Current session is focused on Super-Memory architecture and implementation.")
        if "phase" in combined and any(x in combined for x in ["implement", "triển khai", "deploy"]):
            insights.append("User is driving phased implementation with expectation of auto-continuation.")
        if "heartbeat" in combined or "reminder" in combined or "gián đoạn" in combined:
            insights.append("User wants resilience against interruption via scheduled follow-up.")
        if peer_model and len(peer_model.goals) > 3:
            insights.append("Peer has multiple active implementation goals; context should prioritize current task continuity.")
        return insights

    def _deep_insights(self, user_msg: str, assistant_msg: str, peer_model: PeerModel | None) -> list[str]:
        insights: list[str] = []
        combined = (user_msg + "\n" + assistant_msg).lower()
        if "markdown" in combined and "canonical" in combined:
            insights.append("Architecture preference: preserve Markdown as canonical truth while derived layers add intelligence.")
        if "auto complete" in combined or "auto-complete" in combined:
            insights.append("Operational preference: agent should complete implementation proactively rather than stopping at proposal.")
        return insights
