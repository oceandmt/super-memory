"""Relation extraction — causal, comparative, sequential, and code patterns.

Ported from neural-memory v4.58.0 extraction/relations.py.
Detects relations between text spans for graph enrichment.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("super-memory.extraction.relations")


class RelationType(StrEnum):
    CAUSAL = "causal"
    COMPARATIVE = "comparative"
    SEQUENTIAL = "sequential"
    CODE = "code"


@dataclass(frozen=True)
class RelationCandidate:
    source_span: str
    target_span: str
    relation_type: RelationType
    synapse_type: str
    confidence: float
    source_start: int = 0
    source_end: int = 0
    target_start: int = 0
    target_end: int = 0


# Build patterns
_PatternEntry = tuple[re.Pattern, str, RelationType, float, bool]


def _build_patterns() -> list[_PatternEntry]:
    patterns: list[_PatternEntry] = []
    # Causal: "X because Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+because\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "caused_by", RelationType.CAUSAL, 0.80, False))
    # Causal: "X caused by Y" / "X due to Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+(?:caused\s+by|due\s+to)\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "caused_by", RelationType.CAUSAL, 0.85, False))
    # Causal: "X leads to Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+leads?\s+to\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "leads_to", RelationType.CAUSAL, 0.80, False))
    # Causal: "X results in Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+results?\s+in\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "leads_to", RelationType.CAUSAL, 0.80, False))
    # Causal: "X therefore Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+therefore\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "leads_to", RelationType.CAUSAL, 0.75, False))
    # Causal: "so X, Y" (Y because X)
    patterns.append((re.compile(r"(?:so|thus|hence)\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "caused_by", RelationType.CAUSAL, 0.65, True))
    # Causal: "X triggers Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+triggers?\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "leads_to", RelationType.CAUSAL, 0.78, False))

    # Comparative: "X better than Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+(?:better|faster|cheaper|stronger|more\s+\w+)\s+than\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "related_to", RelationType.COMPARATIVE, 0.70, False))
    # Comparative: "X vs Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+(?:vs\.?|versus)\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "related_to", RelationType.COMPARATIVE, 0.75, False))
    # Comparative: "X instead of Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+instead\s+of\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "related_to", RelationType.COMPARATIVE, 0.72, False))
    # Comparative: "prefer X over Y"
    patterns.append((re.compile(r"prefer\s+(.{5,80}?)\s+over\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "related_to", RelationType.COMPARATIVE, 0.68, False))

    # Sequential: "first X, then Y"
    patterns.append((re.compile(r"(?:first|initially)\s+(.{5,80}?),?\s+(?:then|next|afterwards)\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "sequential", RelationType.SEQUENTIAL, 0.75, True))
    # Sequential: "X before Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+before\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "sequential", RelationType.SEQUENTIAL, 0.78, False))
    # Sequential: "after X, Y"
    patterns.append((re.compile(r"after\s+(.{5,80}?),?\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "sequential", RelationType.SEQUENTIAL, 0.80, True))
    # Sequential: "X followed by Y"
    patterns.append((re.compile(r"(.{5,80}?)\s+followed\s+by\s+(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "sequential", RelationType.SEQUENTIAL, 0.82, False))
    # Sequential: "step 1: X, step 2: Y"
    patterns.append((re.compile(r"step\s+\d+\s*[.:]\s*(.{5,80}?)\s*[,;]\s*step\s+\d+\s*[.:]\s*(.{5,80}?)(?:\.|;|,|$)", re.IGNORECASE), "sequential", RelationType.SEQUENTIAL, 0.85, True))

    # Code: "X import Y"
    patterns.append((re.compile(r"(?:import|from)\s+(\w+(?:\.\w+)*)\s+.*(?:import|use)\s+(\w+)", re.IGNORECASE), "imports", RelationType.CODE, 0.85, True))
    # Code: "function X calls Y"
    patterns.append((re.compile(r"(?:function|def|fn)\s+(\w+).*?(?:calls|invokes|uses)\s+(\w+)", re.IGNORECASE), "calls", RelationType.CODE, 0.75, False))
    # Code: "X extends Y" / "X implements Y"
    patterns.append((re.compile(r"(\w+)\s+(?:extends|implements|inherits\s+from)\s+(\w+)"), "inherits", RelationType.CODE, 0.90, False))
    # Code: "X calls Y with"
    patterns.append((re.compile(r"(\w+)\s+(?:calls|invokes|runs|executes)\s+(\w+)"), "calls", RelationType.CODE, 0.70, False))
    return patterns


_PATTERNS = _build_patterns()


def extract_relations(text: str) -> list[RelationCandidate]:
    """Extract relation candidates from text using pattern matching."""
    if not text or len(text) < 20:
        return []
    results: list[RelationCandidate] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for pattern, syn_type, rel_type, confidence, is_reversed in _PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups) >= 2:
                if is_reversed:
                    source, target = groups[1], groups[0]
                else:
                    source, target = groups[0], groups[1]
                source = source.strip().lower()[:60]
                target = target.strip().lower()[:60]
                if len(source) < 3 or len(target) < 3:
                    continue
                pair_key = (source, target, rel_type.value)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                results.append(RelationCandidate(
                    source_span=source, target_span=target,
                    relation_type=rel_type, synapse_type=syn_type,
                    confidence=confidence,
                    source_start=match.start(), source_end=match.end(),
                    target_start=match.end() - len(groups[-1]), target_end=match.end(),
                ))
    return results[:20]  # Cap at 20 per text
