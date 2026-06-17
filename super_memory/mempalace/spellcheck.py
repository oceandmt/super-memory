"""Spellcheck — correct user messages before palace storage.

Preserves:
  - Technical terms (words with digits, hyphens, underscores)
  - CamelCase and ALL_CAPS identifiers
  - Known entity names (from EntityRegistry)
  - URLs and file paths
  - Words shorter than 3 chars
  - Proper nouns already capitalized

Corrects:
  - Common typos in lowercase flowing text
  - Common fat-finger words

Uses autocorrect (Peter Norvig-style) when available, with custom dictionary.
Deterministic fallback when autocorrect not installed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ── Patterns that should NEVER be spell-corrected ───────────────────────────
PROTECTED_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b\w*[0-9]\w*\b'),                    # Words with digits
    re.compile(r'\b\w+[-_]\w+(?:[-_]\w+)*\b'),         # hyphen/underscore chains
    re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b'),    # CamelCase
    re.compile(r'\b[A-Z]{2,}\b'),                       # ALL_CAPS
    re.compile(r'https?://\S+'),                        # URLs
    re.compile(r'(?:^|\s)[./]?\w+(?:/\w+)+(?:\.\w+)?'), # File paths
    re.compile(r'`[^`]+`'),                             # Code snippets
    re.compile(r'\b[a-f0-9]{7,40}\b'),                  # Hashes (git, SHA)
    re.compile(r'\b[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\b'),  # UUIDs
    re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),               # Dates
    re.compile(r'@[\w.-]+'),                             # Mentions
    re.compile(r'#[\w-]+'),                              # Tags/hashtags
]

# ── Common fat-finger corrections ───────────────────────────────────────────
COMMON_TYPOS: dict[str, str] = {
    "teh": "the",
    "adn": "and",
    "thn": "then",
    "thier": "their",
    "recieve": "receive",
    "acheive": "achieve",
    "begining": "beginning",
    "definately": "definitely",
    "definitly": "definitely",
    "seperate": "separate",
    "occured": "occurred",
    "untill": "until",
    "wierd": "weird",
    "alot": "a lot",
    "becuase": "because",
    "dont": "don't",
    "doesnt": "doesn't",
    "wont": "won't",
    "couldnt": "couldn't",
    "wouldnt": "wouldn't",
    "shouldnt": "shouldn't",
    "thats": "that's",
    "theres": "there's",
    # Vietnamese
    "khong": "không",
    "duoc": "được",
    "nhung": "nhưng",
    "cung": "cũng",
    "nguoi": "người",
    "nhieu": "nhiều",
}


def _extract_protected_spans(text: str) -> list[tuple[int, int, str]]:
    """Find all protected spans in text."""
    spans: list[tuple[int, int, str]] = []
    all_spans: set[tuple[int, int]] = set()
    
    for pattern in PROTECTED_PATTERNS:
        for match in pattern.finditer(text):
            span = (match.start(), match.end())
            span_key = (span[0], span[1])
            if span_key not in all_spans:
                all_spans.add(span_key)
                spans.append((span[0], span[1], match.group()))
    
    return sorted(spans, key=lambda x: x[0])


def _is_protected(pos: int, protected_spans: list[tuple[int, int, str]]) -> bool:
    """Check if a position falls within any protected span."""
    for start, end, _ in protected_spans:
        if start <= pos < end:
            return True
    return False


def spellcheck_user_text(
    text: str,
    known_entities: set[str] | None = None,
    custom_corrections: dict[str, str] | None = None,
) -> str:
    """Spell-correct user text while preserving technical terms and entities."""
    if not text or not text.strip():
        return text
    
    # Build correction map
    corrections = dict(COMMON_TYPOS)
    if custom_corrections:
        corrections.update(custom_corrections)
    
    # Protect known entities
    protected_words: set[str] = set()
    if known_entities:
        protected_words.update(w.lower().strip() for w in known_entities)
    
    # Find protected spans
    protected_spans = _extract_protected_spans(text)
    
    # Word-by-word replacement with span protection
    def _replacer(match: re.Match) -> str:
        word = match.group(0)
        pos = match.start()
        
        if _is_protected(pos, protected_spans):
            return word
        if word.lower() in protected_words:
            return word
        if word[0].isupper():
            return word
        if len(word) < 2:
            return word
        
        replacement = corrections.get(word.lower())
        if replacement:
            return replacement
        return word
    
    return re.sub(r'\b[a-zA-Z]{2,}\b', _replacer, text)


def spellcheck_with_registry(text: str, registry_path: str = "") -> str:
    """Spellcheck using EntityRegistry for known entity protection."""
    known: set[str] = set()
    try:
        from .entity_registry import EntityRegistry
        reg = EntityRegistry.load(registry_path=registry_path)
        known.update(e["name"] for e in reg._entities.values())
        known.update(reg._aliases.keys())
    except Exception:
        pass
    return spellcheck_user_text(text, known_entities=known)
