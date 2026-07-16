"""Deterministic, auditable semantic memory classification.

Semantic type is deliberately orthogonal to truth level, scope, projection and
lifecycle.  The classifier reports calibrated confidence and ambiguity rather
than pretending every short utterance has an obvious type.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

SEMANTIC_CLASSIFIER_VERSION = "1.0.0"
SEMANTIC_TYPES = ("decision", "preference", "todo", "blocker", "workflow", "lesson", "event", "fact", "context")

_PATTERNS: dict[str, tuple[tuple[re.Pattern[str], float], ...]] = {
    "decision": ((re.compile(r"\b(?:we|i|team)?\s*(?:have\s+)?decided\b|\bdecision\s*:|\b(?:chose|selected|adopted)\b", re.I), .92),),
    "preference": ((re.compile(r"\b(?:i|we|user|team|the user|the team)\s+(?:strongly\s+)?(?:prefer|prefers|like|likes|want|wants)\b|\bpreference\s*:", re.I), .92),),
    "todo": ((re.compile(r"\b(?:todo|next action|action item)\s*:|\b(?:need to|must|should)\s+(?:implement|add|fix|review|run|update|remove|write|deploy)\b", re.I), .90),),
    "blocker": ((re.compile(r"\b(?:blocked|blocker|stuck|cannot proceed|can't proceed|waiting (?:for|on))\b", re.I), .94), (re.compile(r"\b(?:fails?|failed|errors?)\b.*\b(?:prevents?|blocks?|cannot|can't)\b|\b(?:prevents?|blocks?)\b.*\b(?:progress|release|deploy)", re.I), .88)),
    "workflow": ((re.compile(r"\b(?:workflow|procedure|runbook)\s*:|\b(?:first|step 1)\b.+\b(?:then|step 2)\b", re.I), .91),),
    "lesson": ((re.compile(r"\b(?:lesson learned|we learned|takeaway)\b|\b(?:avoid|remember)\b.+\bnext time\b", re.I), .91),),
    "event": ((re.compile(r"\b(?:today|yesterday|on 20\d\d[-/]\d\d[-/]\d\d|at \d{1,2}:\d{2})\b.+\b(?:met|deployed|released|occurred|completed|started)\b", re.I), .88),),
    "fact": ((re.compile(r"\b(?:is|are|was|were|has|uses|contains|runs|lives|located)\b", re.I), .70), (re.compile(r"\b(?:version|path|port|config|status)\s*(?:is|=|:)\s*\S+", re.I), .86)),
}
_RESOLVED = re.compile(r"\b(?:fixed|resolved|recovered|now passes?|completed successfully|all tests pass(?:ed)?|no (?:remaining )?(?:errors?|failures?))\b", re.I)
_NEGATED_BLOCK = re.compile(r"\b(?:not blocked|no blockers?|without blockers?)\b", re.I)

@dataclass(frozen=True)
class SemanticClassification:
    semantic_type: str
    confidence: float
    ambiguous: bool
    alternatives: tuple[tuple[str, float], ...]
    classifier_version: str = SEMANTIC_CLASSIFIER_VERSION

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["alternatives"] = [{"type": t, "confidence": c} for t, c in self.alternatives]
        return out

def classify_semantic_type(content: str) -> SemanticClassification:
    text = " ".join((content or "").split())
    scores: dict[str, float] = {}
    for typ, rules in _PATTERNS.items():
        scores[typ] = max((weight for pattern, weight in rules if pattern.search(text)), default=0.0)
    # A completion report may truthfully mention old errors/failed tests.  A
    # resolved state is not an active blocker; retain its event/fact semantics.
    if _RESOLVED.search(text) or _NEGATED_BLOCK.search(text):
        scores["blocker"] = 0.0
        if re.search(r"\b(?:complete(?:d)?|deployed|released|tests? pass)", text, re.I):
            scores["event"] = max(scores["event"], .86)
        else:
            scores["fact"] = max(scores["fact"], .78)
    ranked = sorted(((t, s) for t, s in scores.items() if s), key=lambda x: (-x[1], SEMANTIC_TYPES.index(x[0])))
    if not ranked:
        return SemanticClassification("context", .55 if len(text) >= 12 else .40, True, ())
    top_type, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    ambiguous = top < .72 or (second >= .70 and top - second < .10)
    confidence = round(max(.35, min(.99, top - (.08 if ambiguous else 0))), 3)
    return SemanticClassification(top_type, confidence, ambiguous, tuple((t, round(s, 3)) for t, s in ranked[1:4]))
