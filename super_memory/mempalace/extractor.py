"""Spatial extraction layer — entities, concepts, relationships from text.

Deterministic regex/keyword extraction. No LLM calls, no embeddings.
Inspired by MemPalace/mempalace Layer 2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    name: str
    kind: str  # person, project, tool, file, date, url, etc.
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Concept:
    name: str
    domain: str  # trading, memory, social, devops, etc.
    weight: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relationship:
    source: str
    target: str
    relation: str  # uses, caused, depends_on, part_of, etc.
    confidence: float = 0.5


# Domain keyword tables
DOMAIN_SIGNALS: dict[str, list[str]] = {
    "trading": [
        "forex", "gold", "xauusd", "btc", "eth", "chart", "candle",
        "support", "resistance", "trend", "pip", "lot", "broker",
        "backtest", "signal", "entry", "exit", "stoploss", "takeprofit",
        "m5", "m15", "h1", "h4", "d1", "mt5", "mt4", "bull", "bear",
    ],
    "memory": [
        "memory", "remember", "recall", "neural", "graph", "synapse",
        "neuron", "consolidation", "mempalace", "honcho", "markdown",
        "fts5", "meilisearch", "sqlite", "index", "retrieval", "forget",
    ],
    "social": [
        "facebook", "tiktok", "youtube", "instagram", "threads",
        "discord", "telegram", "post", "comment", "fanpage", "content",
        "viral", "engagement", "follower", "like", "share",
    ],
    "devops": [
        "docker", "kubernetes", "nginx", "systemd", "cron", "vps",
        "deploy", "ssh", "restart", "service", "plugin", "config",
        "gateway", "openclaw",
    ],
    "development": [
        "python", "javascript", "typescript", "react", "api", "mcp",
        "sql", "test", "bug", "fix", "feature", "refactor", "build",
        "pip", "npm", "git", "commit", "branch", "merge", "pr",
    ],
}

# Entity extraction patterns
ENTITY_PATTERNS: dict[str, re.Pattern] = {
    "file": re.compile(r'\b([\w./-]+\.(?:py|js|ts|md|json|yml|yaml|toml|sh|html|css))\b'),
    "date": re.compile(r'\b(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?)\b'),
    "url": re.compile(r'https?://[\w./?=&#%:@-]+'),
    "agent": re.compile(r'\b(lucas|alex|max|isol|boss)\b', re.IGNORECASE),
    "project": re.compile(r'\b(?:project[:\s]+|repo[:\s]+)?([\w-]+/[a-zA-Z0-9_-]+)\b'),
    "version": re.compile(r'\b(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+)?)\b'),
    "command": re.compile(r'`([^`]+)`'),
    "mention": re.compile(r'@(\w[\w.-]*)'),
    "tag": re.compile(r'#([\w-]+)'),
}

# Concept extraction patterns
CONCEPT_PATTERNS = [
    (re.compile(r'\b(spreading\s+activation|graph\s+recall|neural\s+graph)\b'), "neural_memory"),
    (re.compile(r'\b(markdown\s+first|canonical\s+truth|workspace\s+markdown)\b'), "architecture"),
    (re.compile(r'\b(save\s+order|write\s+order|layer\s+order)\b'), "workflow"),
    (re.compile(r'\b(contradiction|dedup|duplicate)\b'), "quality"),
    (re.compile(r'\b(scaling|scale|performance|latency|benchmark)\b'), "performance"),
    (re.compile(r'\b(security|auth|token|secret|credential)\b'), "security"),
    (re.compile(r'\b(trading\s+mode|news\s+warning|blackout\s+window)\b'), "trading_ops"),
    (re.compile(r'\b(chart\s+analysis|technical\s+analysis|price\s+action)\b'), "trading_technical"),
    (re.compile(r'\b(facebook\s+post|social\s+post|fanpage|content\s+creation)\b'), "content_ops"),
    (re.compile(r'\b(mcp\s+server|mcp\s+tool|plugin\s+manifest)\b'), "mcp_integration"),
]

# Relationship extraction patterns
RELATION_PATTERNS = [
    (re.compile(r'(\w+)\s+(?:uses|runs|depends on|needs|requires|imports)\s+(\w+)', re.IGNORECASE), "uses"),
    (re.compile(r'(\w+)\s+(?:caused|broke|triggered|created)\s+(\w+)', re.IGNORECASE), "caused"),
    (re.compile(r'(\w+)\s+(?:fixed|resolved|patched|solved)\s+(\w+)', re.IGNORECASE), "resolved"),
    (re.compile(r'(\w+)\s+(?:part of|belongs to|inside|within)\s+(\w+)', re.IGNORECASE), "part_of"),
    (re.compile(r'(\w+)\s+(?:before|after|precedes|follows)\s+(\w+)', re.IGNORECASE), "temporal"),
    (re.compile(r'(\w+)\s+(?:supersedes|replaces|overrides)\s+(\w+)', re.IGNORECASE), "supersedes"),
    (re.compile(r'(\w+)\s+(?:contradicts|conflicts|disagrees)\s+(\w+)', re.IGNORECASE), "contradicts"),
]


class SpatialExtractor:
    """Deterministic entity/concept/relationship extractor. No LLM cost."""

    def __init__(self, custom_patterns: dict[str, re.Pattern] | None = None):
        self.entity_patterns = {**ENTITY_PATTERNS, **(custom_patterns or {})}
        self.concept_patterns = list(CONCEPT_PATTERNS)
        self.relation_patterns = list(RELATION_PATTERNS)
        self.domain_signals = {**DOMAIN_SIGNALS}

    def extract_entities(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        seen: set[tuple[str, str]] = set()
        for kind, pattern in self.entity_patterns.items():
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                key = (name.lower(), kind)
                if key in seen:
                    continue
                seen.add(key)
                entities.append(Entity(
                    name=name,
                    kind=kind,
                    source=text[:80] if len(text) <= 80 else text[match.start():match.start()+80],
                ))
        return entities

    def extract_concepts(self, text: str) -> list[Concept]:
        concepts: list[Concept] = []
        seen: set[str] = set()
        text_lower = text.lower()
        for pattern, domain in self.concept_patterns:
            for match in pattern.finditer(text_lower):
                name = match.group(1).strip().lower()
                if name in seen:
                    continue
                seen.add(name)
                concepts.append(Concept(name=name, domain=domain, weight=0.7))
        return concepts

    def classify_domain(self, text: str) -> list[tuple[str, float]]:
        text_lower = text.lower()
        scores: list[tuple[str, float]] = []
        for domain, keywords in self.domain_signals.items():
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits:
                scores.append((domain, min(1.0, hits / max(1, len(text_lower.split()) / 10))))
        return sorted(scores, key=lambda x: x[1], reverse=True)

    def extract_relationships(self, text: str) -> list[Relationship]:
        rels: list[Relationship] = []
        seen: set[tuple[str, str, str]] = set()
        for pattern, relation in self.relation_patterns:
            for match in pattern.finditer(text):
                source = match.group(1).strip().lower()
                target = match.group(2).strip().lower()
                key = (source, target, relation)
                if key in seen or source == target:
                    continue
                seen.add(key)
                rels.append(Relationship(
                    source=source, target=target,
                    relation=relation, confidence=0.6,
                ))
        return rels

    def extract_all(self, text: str) -> dict[str, Any]:
        return {
            "entities": [e.__dict__ for e in self.extract_entities(text)],
            "concepts": [c.__dict__ for c in self.extract_concepts(text)],
            "domains": [{"domain": d, "score": round(s, 3)} for d, s in self.classify_domain(text)],
            "relationships": [r.__dict__ for r in self.extract_relationships(text)],
        }
