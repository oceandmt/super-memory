"""Prompt section builder — build markdown context sections for prompts.

Matches OpenClaw memory-core prompt-section.ts:
- Builds a memory context block from search results
- Respects token budget limits
- Formats with citations
"""

from __future__ import annotations

from typing import Any


def build_memory_section(
    results: list[dict[str, Any]],
    *,
    title: str = "Memory Context",
    max_tokens: int = 4000,
    include_citations: bool = True,
    max_items: int | None = None,
) -> str:
    """Build a markdown memory context section from search results.

    Args:
        results: List of search result dicts
        title: Section title (default: "Memory Context")
        max_tokens: Maximum token count (approximate char/4 = tokens)
        include_citations: Include citation footnotes
        max_items: Max results to include (default: all)

    Returns:
        Markdown string for prompt injection
    """
    if not results:
        return ""

    max_chars = max_tokens * 4
    sections: list[str] = []
    used_chars = 0

    items = results[:max_items] if max_items else results

    for idx, item in enumerate(items, 1):
        snippet = str(item.get("snippet", item.get("content", "")))
        score = item.get("score", 0.0)
        source = item.get("source", "memory")
        path = item.get("path", "")
        corpus = item.get("corpus", source)

        # Build entry
        entry = (
            f"{idx}. **Score:** {score:.2f} | **Corpus:** {corpus}\n"
            f"   {snippet}\n"
        )
        if include_citations and path:
            citation = _make_citation(item)
            entry += f"   *Source: {citation}*\n"

        entry_chars = len(entry)
        if used_chars + entry_chars > max_chars and sections:
            break
        sections.append(entry)
        used_chars += entry_chars

    if not sections:
        return ""

    header = f"## {title}\n\n"
    body = "\n".join(sections)
    return header + body


def _make_citation(item: dict[str, Any]) -> str:
    """Build inline citation from item metadata."""
    path = item.get("path", "")
    citation = item.get("citation", "")
    source = item.get("source", "memory")
    if citation:
        return f"{citation} ({source})"
    if path:
        return f"{path} ({source})"
    return source


def build_context_block(
    results: list[dict[str, Any]],
    *,
    max_tokens: int = 2000,
) -> str:
    """Quick context block builder for agent prompt injection."""
    return build_memory_section(
        results,
        title="Relevant Memory",
        max_tokens=max_tokens,
        include_citations=True,
    )
