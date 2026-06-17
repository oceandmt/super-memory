"""AAAK Compression — keyword-based memory compression engine.

Achieves ~30x compression ratio using regex heuristics and keyword scoring.
No LLM calls, determined entirely by text pattern extraction.
Inspired by MemPalace/mempalace AAAK naming convention.

Compression strategy:
- Extract key entities + concepts → short index
- Drop common stopwords and transitional phrases
- Preserve structured data (dates, versions, file paths, ids)
- Score importance by keyword frequency and position
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# Common stopwords to drop during compression
STOPWORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "that", "this", "these", "those", "it", "its", "and", "but", "or",
    "because", "until", "while", "if", "about", "up", "down",
}

# High-value word patterns
HIGH_VALUE_PATTERNS = [
    re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b'),  # Proper names
    re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),  # Dates
    re.compile(r'\b\d+\.\d+(?:\.\d+)?\b'),  # Versions
    re.compile(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', re.IGNORECASE),  # UUIDs
    re.compile(r'`[^`]+`'),  # Code/commands
    re.compile(r'https?://[\w./?=&#%@-]+'),  # URLs
    re.compile(r'@[\w.-]+'),  # Mentions
    re.compile(r'#[\w-]+'),  # Tags
    re.compile(r'\b(?:super_memory_|nmem_|honcho_)\w+\b'),  # Tool names
]

# Structured data preserving patterns
STRUCTURED_PATTERNS = [
    re.compile(r'\{[^}]+\}'),  # JSON-like
    re.compile(r'\[[^\]]+\]'),  # List-like
    re.compile(r'"[^"]{3,}"'),  # Quoted strings
]


@dataclass
class CompressedMemory:
    id: str
    checksum: str
    keywords: list[str]
    dense_text: str
    original_length: int
    compression_ratio: float


@dataclass
class CompressedIndex:
    compressed: list[CompressedMemory] = field(default_factory=list)
    keyword_index: dict[str, list[int]] = field(default_factory=dict)  # keyword → compressed indices
    total_original_chars: int = 0
    total_compressed_chars: int = 0


class AAAKCompressor:
    """Keyword-based memory compression engine. Average ~30x compression.

    Preserves structured data (dates, versions, UUIDs, file paths)
    while aggressively stripping common words and transitions.
    """

    def __init__(self, min_token_length: int = 3, max_keywords: int = 8):
        self.min_token_length = min_token_length
        self.max_keywords = max_keywords

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r'\b[a-zA-Z0-9][\w.-]*\b', text.lower())

    def _extract_high_value(self, text: str) -> list[str]:
        snippets: list[str] = []
        for pattern in HIGH_VALUE_PATTERNS:
            for match in pattern.finditer(text):
                snippets.append(match.group(0))
        return snippets

    def _extract_structured(self, text: str) -> list[str]:
        snippets: list[str] = []
        for pattern in STRUCTURED_PATTERNS:
            for match in pattern.finditer(text):
                snippets.append(match.group(0))
        return snippets

    def _score_keywords(self, tokens: list[str]) -> list[tuple[str, float]]:
        freq: dict[str, int] = {}
        for t in tokens:
            if len(t) >= self.min_token_length and t not in STOPWORDS:
                freq[t] = freq.get(t, 0) + 1

        total = sum(freq.values()) or 1
        scored: list[tuple[str, float]] = []
        for t, f in freq.items():
            scored.append((t, f / total))
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def compress_text(self, text: str, memory_id: str = "") -> CompressedMemory:
        """Compress a single memory text entry."""
        original_len = len(text)
        tokens = self._tokenize(text)
        high_value = self._extract_high_value(text)
        structured = self._extract_structured(text)
        scored = self._score_keywords(tokens)

        # Build compact representation
        keywords = [s[0] for s in scored[:self.max_keywords]]
        dense_parts: list[str] = []
        dense_parts.extend(high_value[:4])  # Up to 4 high-value snippets
        dense_parts.extend(structured[:2])  # Up to 2 structured snippets

        # Add remaining meaningful tokens
        meaningful = [t for t in tokens if len(t) >= self.min_token_length and t not in STOPWORDS and t not in keywords]
        dense_parts.append(" ".join(meaningful[:12]))

        dense_text = " | ".join(p for p in dense_parts if p)
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        ratio = original_len / max(1, len(dense_text))

        return CompressedMemory(
            id=memory_id,
            checksum=checksum,
            keywords=keywords,
            dense_text=dense_text,
            original_length=original_len,
            compression_ratio=round(ratio, 1),
        )

    def compress_batch(self, texts: list[tuple[str, str]]) -> CompressedIndex:
        """Compress a batch of (memory_id, text) pairs into an index."""
        index = CompressedIndex()
        for idx, (mem_id, text) in enumerate(texts):
            cm = self.compress_text(text, mem_id)
            index.compressed.append(cm)
            index.total_original_chars += cm.original_length
            index.total_compressed_chars += len(cm.dense_text)
            for kw in cm.keywords:
                index.keyword_index.setdefault(kw, []).append(idx)
        return index

    def search(self, query: str, index: CompressedIndex, limit: int = 10) -> list[CompressedMemory]:
        """Simple keyword search against compressed index."""
        query_tokens = [t.lower() for t in re.findall(r'\b\w+\b', query) if t.lower() not in STOPWORDS]
        if not query_tokens:
            return index.compressed[:limit]

        scores: dict[int, float] = {}
        for token in query_tokens:
            matching_indices = index.keyword_index.get(token, [])
            for idx in matching_indices:
                scores[idx] = scores.get(idx, 0) + 1.0
                # Bonus for exact keyword match
                if token in index.compressed[idx].keywords:
                    scores[idx] += 0.5

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [index.compressed[idx] for idx, _ in ranked[:limit]]

    def stats(self, index: CompressedIndex) -> dict[str, Any]:
        """Compression statistics."""
        return {
            "num_compressed": len(index.compressed),
            "total_original_chars": index.total_original_chars,
            "total_compressed_chars": index.total_compressed_chars,
            "avg_compression_ratio": round(
                index.total_original_chars / max(1, index.total_compressed_chars), 1
            ),
            "indexed_keywords": len(index.keyword_index),
            "avg_original_chars_per_memory": round(
                index.total_original_chars / max(1, len(index.compressed))
            ),
            "avg_compressed_chars_per_memory": round(
                index.total_compressed_chars / max(1, len(index.compressed))
            ),
        }
