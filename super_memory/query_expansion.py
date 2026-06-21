"""Lightweight query expansion for Super Memory.

Expands search queries with:
1. Morphological variants (stemming suffixes/prefixes)
2. Graph-based expansions (RELATED_TO neurons from cognitive graph)
3. Entity synonyms from MemPalace entity registry
"""

from __future__ import annotations

import re
from typing import Any

# ── Morphological expansion ────────────────────────────────────────────────
_EXPANSION_SUFFIXES: tuple[str, ...] = (
    "tion", "ment", "ing", "ed", "er", "ity", "ness", "ize", "ise", "ate",
    "al", "ial", "ual", "ive", "able", "ible", "ous", "ful", "less",
)
_EXPANSION_PREFIXES: tuple[str, ...] = ("un", "re", "pre", "de", "dis", "mis", "over", "under")


def _morphological_expansions(word: str) -> set[str]:
    """Generate morphological variants of a word."""
    variants: set[str] = {word}
    lower = word.lower()

    # Strip common suffixes and try alternate forms
    for suffix in _EXPANSION_SUFFIXES:
        if lower.endswith(suffix):
            base = lower[: -len(suffix)]
            if len(base) >= 3:
                variants.add(base)
                # Try adding common suffixes to base
                for alt_suffix in ("ing", "ed", "er", "tion"):
                    if alt_suffix != suffix:
                        variants.add(base + alt_suffix)
        else:
            # Try adding suffix
            for alt_suffix in ("ing", "ed", "er", "tion"):
                cand = lower + alt_suffix
                variants.add(cand)

    # Strip common prefixes
    for prefix in _EXPANSION_PREFIXES:
        if lower.startswith(prefix) and len(lower) > len(prefix) + 2:
            variants.add(lower[len(prefix) :])
        else:
            cand = prefix + lower
            variants.add(cand)

    return variants


def expand_query(query: str, store: Any = None) -> list[str]:
    """Expand a search query into multiple query variants.

    Args:
        query: Original query string.
        store: Optional SuperMemoryStore for graph/entity expansion.

    Returns:
        List of query variants (original first).
    """
    if not query or not query.strip():
        return [query]

    # Split into words
    words = re.findall(r"\w+", query)
    variants: set[str] = {query}

    # Per-word morphological expansion
    for word in set(words):
        if len(word) < 3:
            continue
        morphed = _morphological_expansions(word)
        for morph in morphed:
            if morph == word:
                continue
            # Replace word in original query
            for original in [query, query.lower()]:
                if word.lower() in original.lower():
                    variant = re.sub(
                        re.escape(word), morph, original, flags=re.IGNORECASE
                    )
                    variants.add(variant)

    # Graph-based expansion via RELATED_TO neurons
    if store is not None:
        try:
            with store.connect() as conn:
                for word in set(words):
                    if len(word) < 3:
                        continue
                    # Find cognitive neurons matching this word
                    rows = conn.execute(
                        """
                        SELECT DISTINCT cn.content FROM cognitive_neurons cn
                        JOIN cognitive_synapses cs ON cs.source_neuron_id = cn.id
                        WHERE cs.relation IN ('related_to', 'similar_to')
                        AND cn.content LIKE ?
                        LIMIT 3
                        """,
                        (f"%{word}%",),
                    ).fetchall()
                    for row in rows:
                        related = str(row["content"])
                        if related.lower() != word.lower():
                            variants.add(f"{query} {related}")
        except Exception:
            pass  # Non-fatal; fall back to morphological only

    # Deduplicate, clean, and sort by length (original first)
    cleaned: set[str] = set()
    for v in variants:
        v_stripped = re.sub(r"\s+", " ", v).strip()
        if v_stripped and len(v_stripped) >= 3:
            cleaned.add(v_stripped)

    # Return with original first, then by length desc
    result = [query] if query in cleaned else []
    others = sorted(
        [c for c in cleaned if c != query], key=len, reverse=True
    )
    result.extend(others)

    # Cap to avoid too many expansions
    return result[:6]
