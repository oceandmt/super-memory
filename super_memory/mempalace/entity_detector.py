"""Entity detector — scan text for person/entity mentions with disambiguation.

Differentiates names from common words using context analysis.
Deterministic regex + keyword heuristics. No LLM. No network.

Usage:
    from super_memory.mempalace.entity_detector import scan_text
    results = scan_text("I talked with Max about the project with Alice")
    # → [{"name": "Max", "kind": "person", "confidence": 0.9}, ...]
"""

from __future__ import annotations

import re
from typing import Any

# ── Patterns for detecting entity mentions ──────────────────────────────────

# Patterns that strongly indicate a person
PERSON_INDICATORS: list[re.Pattern] = [
    re.compile(r"(?:I|we|they)\s+(?:talked|spoke|met|chatted|worked|paired|collaborated)\s+(?:to|with)\s+([A-Z][a-z]{2,})", re.IGNORECASE),
    re.compile(r"(?:my|our|their|his|her)\s+(?:friend|partner|wife|husband|colleague|brother|sister|dad|mom|son|daughter|boss|teammate|mentor)\s*(?:,?\s*([A-Z][a-z]{2,})\b)?", re.IGNORECASE),
    re.compile(r"([A-Z][a-z]{2,})\s+(?:is|was|has been)\s+(?:my|our|their|a)\s+(?:friend|partner|colleague|boss|agent|assistant)", re.IGNORECASE),
    re.compile(r"([A-Z][a-z]{2,})\s+(?:said|told|mentioned|wrote|asked|replied|noted|reported|suggested|explained|recommended|decided|agreed)", re.IGNORECASE),
    re.compile(r"(?:go|went|going)\s+(?:to|with)\s+([A-Z][a-z]{2,})(?:'s)?\s+(?:place|house|office|room)", re.IGNORECASE),
    re.compile(r"(?:call|called|contact|text|email|message)\s+([A-Z][a-z]{2,})", re.IGNORECASE),
    re.compile(r"(?:ask|told)\s+([A-Z][a-z]{2,})\s+to", re.IGNORECASE),
]

# Patterns that indicate a project/thing
PROJECT_INDICATORS: list[re.Pattern] = [
    re.compile(r"(?:project|repo|repository)\s+([A-Z][a-zA-Z0-9_-]{2,})", re.IGNORECASE),
    re.compile(r"The\s+([A-Z][a-zA-Z]{2,})\s+(?:project|system|tool|service|plugin|module|engine)", re.IGNORECASE),
    re.compile(r"(?:working|work)\s+(?:on|with)\s+(?:the\s+)?([A-Z][a-zA-Z]{2,})\s+(?:project|system|tool)", re.IGNORECASE),
]

# Known code/tech indicators (not people)
TECH_INDICATORS: set[str] = {
    "python", "javascript", "typescript", "react", "docker", "kubernetes",
    "fastapi", "sqlite", "postgresql", "redis", "nginx", "openclaw",
    "super", "memory", "neural", "graph", "palace", "drawer",
    "git", "github", "vscode", "chrome", "firefox", "safari",
}

# Common words that often appear after "project/repo" but are NOT projects
NOT_PROJECT_WORDS: set[str] = {
    "looks", "seems", "appears", "sounds", "feels", "is", "was",
    "has", "had", "will", "would", "could", "should", "might",
    "does", "goes", "gets", "makes", "takes", "gives", "comes",
    "became", "remains", "stays", "keeps", "needs", "wants",
    "great", "good", "bad", "nice", "fine", "okay", "done",
    "ready", "almost", "really", "quite", "very", "pretty",
    "already", "still", "always", "never", "soon", "now",
}

# Name patterns (capitalized, non-common)
NAME_PATTERN = re.compile(r'\b([A-Z][a-z]{2,})\b')
AGENT_PATTERN = re.compile(r'\b(lucas|alex|max|isol|boss)\b', re.IGNORECASE)
MENTION_PATTERN = re.compile(r'@(\w[\w.-]{1,30})')


def scan_text(text: str, known_entities: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Scan text for entity mentions with disambiguation.

    Args:
        text: The text to scan
        known_entities: Optional dict of name→entity for known entities

    Returns:
        List of detected entities with kind, confidence, and source
    """
    detections: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1. Agent mentions (known agents)
    for match in AGENT_PATTERN.finditer(text):
        name = match.group(1)
        if name.lower() not in seen:
            seen.add(name.lower())
            detections.append({
                "name": name.capitalize() if name.lower() != "boss" else "Boss",
                "kind": "agent",
                "confidence": 1.0,
                "source": "known_agent",
                "span": (match.start(), match.end()),
            })

    # 2. @ mentions
    for match in MENTION_PATTERN.finditer(text):
        name = match.group(1)
        if name.lower() not in seen:
            seen.add(name.lower())
            detections.append({
                "name": name,
                "kind": "person" if _looks_like_name(name) else "reference",
                "confidence": 0.9,
                "source": "mention",
                "span": (match.start(), match.end()),
            })

    # 3. Strong person indicators
    for pattern in PERSON_INDICATORS:
        for match in pattern.finditer(text):
            name = None
            try:
                name = match.group(1)
            except (IndexError, AttributeError):
                continue
            if name and name.lower() not in seen and name.lower() not in TECH_INDICATORS:
                if _looks_like_name(name):
                    seen.add(name.lower())
                    detections.append({
                        "name": name,
                        "kind": "person",
                        "confidence": 0.85,
                        "source": "context_pattern",
                    })

    # 4. Project indicators
    for pattern in PROJECT_INDICATORS:
        for match in pattern.finditer(text):
            try:
                name = match.group(1)
            except (IndexError, AttributeError):
                continue
            if name and name.lower() not in seen and name.lower() not in TECH_INDICATORS and name.lower() not in NOT_PROJECT_WORDS:
                seen.add(name.lower())
                detections.append({
                    "name": name,
                    "kind": "project",
                    "confidence": 0.75,
                    "source": "context_pattern",
                })

    # 5. Capitalized names (lower confidence)
    for match in NAME_PATTERN.finditer(text):
        name = match.group(1)
        if name.lower() not in seen and name.lower() not in TECH_INDICATORS:
            if _looks_like_name(name):
                # Check if in known entities
                if known_entities and name.lower() in known_entities:
                    ee = known_entities[name.lower()]
                    detections.append({
                        "name": name,
                        "kind": ee.get("kind", "person"),
                        "confidence": ee.get("confidence", 0.7),
                        "source": "known_entity",
                    })
                else:
                    detections.append({
                        "name": name,
                        "kind": "person" if _is_likely_person(name, text) else "unknown",
                        "confidence": 0.4,
                        "source": "capitalized",
                    })
            seen.add(name.lower())

    return detections


def _looks_like_name(word: str) -> bool:
    """Check if a word looks like a name (not a common word)."""
    from .entity_registry import COMMON_ENGLISH_WORDS_LOWER
    w = word.strip().lower()
    if len(w) < 2:
        return False
    if w in COMMON_ENGLISH_WORDS_LOWER:
        return False
    if not word[0].isupper():
        return False
    if not word.isalpha():
        return False
    return True


def _is_likely_person(name: str, context: str) -> bool:
    """Score likelihood a capitalized word is a person."""
    from .entity_registry import PERSON_VERBS
    
    idx = context.lower().find(name.lower())
    if idx < 0:
        return True  # Default: assume proper noun = person
    
    # Check surrounding words for person verbs
    words = context.lower().split()
    word_idx = -1
    for i, w in enumerate(words):
        if w == name.lower():
            word_idx = i
            break
    
    if word_idx >= 0:
        window = words[max(0, word_idx-2):word_idx+3]
        if any(v in window for v in PERSON_VERBS):
            return True
    
    return True  # Default assume person for capitalized words


def detect_and_register(
    text: str,
    registry_path: str = "",
    min_confidence: float = 0.6,
    auto_save: bool = True,
) -> dict[str, Any]:
    """Scan text, detect entities, and auto-register high-confidence ones.

    Returns summary of what was detected and registered.
    """
    from .entity_registry import EntityRegistry
    
    reg = EntityRegistry.load(registry_path=registry_path)
    known = {k: {"kind": v["kind"], "confidence": v["confidence"]} 
             for k, v in reg._entities.items()}
    for alias, canonical in reg._aliases.items():
        if canonical in reg._entities:
            known[alias] = {
                "kind": reg._entities[canonical]["kind"],
                "confidence": reg._entities[canonical]["confidence"],
            }
    
    detections = scan_text(text, known_entities=known)
    
    newly_registered: list[str] = []
    for d in detections:
        if d["confidence"] >= min_confidence:
            if d["name"].lower() not in reg._entities and d["name"].lower() not in reg._aliases:
                if d["kind"] in ("person", "project", "agent"):
                    reg.add(
                        name=d["name"],
                        kind=d["kind"],
                        source="learned",
                        confidence=d["confidence"],
                        metadata={"detected_in": text[:120]},
                    )
                    newly_registered.append(d["name"])
    
    if newly_registered and auto_save:
        reg.save()
    
    return {
        "detections": detections,
        "newly_registered": newly_registered,
        "registry_stats": reg.stats(),
    }
