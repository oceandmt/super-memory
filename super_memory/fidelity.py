"""Fidelity — single-sentence essence extraction from memory content.

Extracts the core single-sentence essence from any memory text.
Used for:
1. **Compression summaries** — replace verbatim content with essence
2. **Confidence fidelity layer** — determine if content is verbatim/detail/summary/gist/essence
3. **Quick recall previews** — show essence before expanding full content

The essence is the minimal self-contained sentence that captures the
memory's core meaning, preserving entities, actions, and outcomes.
"""
from __future__ import annotations

import logging
import re
from typing import Any

__all__ = [
    "extract_essence",
    "classify_fidelity_layer",
    "FidelityLayer",
]

logger = logging.getLogger("super-memory.fidelity")

# ── Constants ────────────────────────────────────────────────────────────────

FidelityLayer = str
# Type aliases for clarity
FIDELITY_VERBATIM: FidelityLayer = "verbatim"   # Exact text preserved
FIDELITY_DETAIL: FidelityLayer = "detail"       # Rich but not exact
FIDELITY_SUMMARY: FidelityLayer = "summary"     # Condensed
FIDELITY_GIST: FidelityLayer = "gist"           # Approximate meaning
FIDELITY_ESSENCE: FidelityLayer = "essence"     # Single sentence core


# ── Essence Extraction ───────────────────────────────────────────────────────

def _score_sentence(sentence: str, content_lower: str, keywords: set[str]) -> float:
    """Score a sentence's suitability as the essence of the content.

    Higher scores for sentences that:
    - Contain key entities (capitalized words)
    - Contain domain keywords matching the overall content
    - Have action verbs (decided, implemented, fixed, etc.)
    - Are not too short (< 10 chars) or too long (> 500 chars)
    - Are not boilerplate (greetings, signatures, etc.)
    """
    s_lower = sentence.lower()
    s_words = sentence.split()
    word_count = len(s_words)

    # Length filter
    if word_count < 5 or word_count > 80:
        return 0.0

    # Boilerplate detection
    boilerplate = {
        "hello", "hi there", "thanks", "thank you", "best regards",
        "sincerely", "---", "```", "attachment", "from:",
        "to:", "subject:", "original message",
    }
    flat = s_lower[:40]
    for bp in boilerplate:
        if bp in flat:
            return 0.0

    score = 0.0

    # Keyword match (up to 0.4)
    if keywords:
        match_count = sum(1 for kw in keywords if kw.lower() in s_lower)
        score += min(match_count * 0.05, 0.4)

    # Capitalized entities (up to 0.2)
    entities = re.findall(r'\b[A-Z][a-z]{2,}\b', sentence)
    score += min(len(entities) * 0.03, 0.2)

    # Action verbs (up to 0.2)
    actions = re.findall(
        r'\b(?:decided|chose|selected|implemented|deployed|fixed|'
        r'created|added|changed|migrated|upgraded|configured|'
        r'discovered|learned|resolved|determined|concluded|'
        r'recommended|proposed|built|launched|released)\b',
        sentence, re.IGNORECASE
    )
    score += min(len(actions) * 0.05, 0.2)

    # Position bonus: first meaningful sentence often states the core (up to 0.2)
    # We don't know position here, so use specificity signals instead

    # Specificity: numbers, code terms, dates (up to 0.1)
    specifics = len(re.findall(r'\b\d+\b|'
                                r'\b[A-Z][a-z]*\.[A-Z][a-z]*\b|'
                                r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b',
                                sentence))
    score += min(specifics * 0.02, 0.1)

    # Question penalty: questions rarely capture essence
    if "?" in sentence:
        score *= 0.5

    return score


def extract_essence(content: str, max_sentences: int = 1) -> str:
    """Extract single-sentence essence from memory content.

    Strategy:
    1. Extract domain keywords from the full content
    2. Split into sentences
    3. Score each sentence for essence suitability
    4. Return highest-scoring sentence (or top N with max_sentences)

    Args:
        content: Full memory text.
        max_sentences: Number of essence sentences to return (default 1).

    Returns:
        Essence string. Empty string if no suitable sentence found.
    """
    if not content or len(content) < 20:
        return ""

    # Extract domain keywords from full content
    content_lower = content.lower()
    words = re.findall(r"\w{3,}", content_lower)
    # Use top 30 most frequent non-stop words as domain keywords
    from collections import Counter
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "this", "that", "these", "those", "i", "you", "he", "she",
        "it", "we", "they", "me", "him", "her", "us", "them", "my", "your",
        "his", "its", "our", "their", "mine", "yours", "hers", "its", "ours",
        "theirs", "what", "which", "who", "whom", "whose", "when", "where",
        "why", "how", "all", "each", "every", "both", "few", "more", "most",
        "some", "any", "no", "not", "only", "own", "same", "so", "than",
        "too", "very", "just", "because", "as", "until", "while", "of",
        "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "to",
        "from", "up", "down", "in", "out", "on", "off", "over", "under",
        "again", "further", "then", "once", "here", "there", "and", "but",
        "or", "if", "while", "that", "also", "well", "get", "got", "make",
        "made", "said", "like", "just", "really", "much", "still", "even",
        "back", "way", "thing", "things", "something", "everything",
    }
    keyword_freq = Counter(w for w in words if w not in stop_words and len(w) > 2)
    keywords = set(w for w, _ in keyword_freq.most_common(30))

    # Split into sentences
    # Handle common abbreviations to avoid false splits
    text = content.strip()
    # Protect abbreviations from being split
    text = re.sub(r'\b(Dr|Mr|Mrs|Ms|Prof|Sr|Jr|St|Ave|Blvd|Rd|vs|etc|inc|corp|ltd)\.', r'\1<DOT>', text)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Restore dots
    sentences = [s.replace('<DOT>', '.') for s in sentences]

    # Filter out empty/trivial sentences
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    if not sentences:
        # Fallback: use first meaningful segment
        first = content[:200].strip()
        return first if len(first) > 20 else ""

    if len(sentences) == 1:
        # Single sentence — if it's short enough, it IS the essence
        if len(content) < 300:
            return content.strip()
        # Otherwise score it
        score = _score_sentence(sentences[0], content_lower, keywords)
        return sentences[0] if score > 0 else ""

    # Score each sentence
    scored = [(s, _score_sentence(s, content_lower, keywords)) for s in sentences]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Return top N
    best = [s for s, sc in scored if sc > 0][:max_sentences]
    if best:
        return " ".join(best)

    # Last resort: first substantial sentence
    for s in sentences:
        if len(s) > 40 and len(s) < 600:
            return s

    return sentences[0] if sentences else ""


# ── Fidelity Layer Classification ────────────────────────────────────────────

_MARKDOWN_PATTERNS = re.compile(r'#{1,6}\s|\*\*|`{1,3}|\[.*?\]\(.*?\)|```|---')
_LIST_PATTERNS = re.compile(r'^\s*[-*+]\s|^\s*\d+\.\s', re.MULTILINE)
_CODE_PATTERNS = re.compile(r'(?:^|\n)\s*(?:def |class |import |from\s+\S+|function|const |let |var |'
                             r'public |private |static |void |int |str |return |'
                             r'if |elif |else |while |for |try |except |with |async |await )')


def classify_fidelity_layer(content: str) -> FidelityLayer:
    """Classify content into a fidelity layer based on structure and richness.

    Rules:
    - **verbatim**: Markdown/code content preserved exactly
    - **detail**: 200+ chars with entities and specifics
    - **summary**: 80-500 chars, condensed but not minimal
    - **gist**: 40-200 chars, approximate meaning
    - **essence**: < 100 chars, single-sentence core

    Args:
        content: Memory text content.

    Returns:
        FidelityLayer string constant.
    """
    if not content:
        return FIDELITY_ESSENCE

    length = len(content)
    has_markdown = bool(_MARKDOWN_PATTERNS.search(content))
    has_lists = bool(_LIST_PATTERNS.search(content))
    has_code = False  # (recomputed below with line-anchor)
    # Entities: capitalized words including CamelCase and ALLCAPS
    entities = re.findall(r'\b[A-Z][a-z]+[A-Z]\w*\b|\b[A-Z][a-z]{2,}\b|\b[A-Z]{2,}\b', content)

    # Verbatim: structured/rich content preserved exactly
    if has_markdown or has_lists:
        return FIDELITY_VERBATIM

    has_code = bool(_CODE_PATTERNS.search('\n' + content))  # anchor to line-start

    # Verbatim: structured/rich content preserved exactly
    if has_markdown or has_lists or has_code:
        return FIDELITY_VERBATIM


    # Detail: substantial with specifics
    if length >= 150 and len(entities) > 0:
        return FIDELITY_DETAIL

    # Summary: condensed
    if 60 <= length < 150:
        return FIDELITY_SUMMARY

    # Gist: approximate
    if 30 <= length < 60:
        return FIDELITY_GIST

    # Gist: approximate
    if 40 <= length < 200:
        return FIDELITY_GIST

    # Essence: single sentence
    return FIDELITY_ESSENCE

# ── Safe wrapper ─────────────────────────────────────────────────────────────

def extract_fidelity_safe(content: str) -> dict:
    """Safe wrapper for extract_fidelity with error handling."""
    try:
        result = extract_fidelity(content)
        return {
            "essence": result.essence,
            "layer": result.layer.value,
            "confidence": result.confidence,
            "tokens_saved": result.tokens_saved,
        }
    except Exception as e:
        logger.error("extract_fidelity failed: %s", e, exc_info=True)
        return {"essence": "", "layer": "detail", "confidence": 0.0, "error": str(e)}
