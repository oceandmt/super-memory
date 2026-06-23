"""Neighbor Expansion + Line Citations — enrich recall results with source context.

P2 — extends recall results with:
1. Line number citations (line_start, line_end) for canonical markdown sources
2. Neighbor chunk expansion (±N chunks/closet entries around a match)
3. Source file path, content hash, offset tracking

Borrowed from:
- MemPalace: neighbor expansion (_expand_with_neighbors), virtual line numbering
- Neural Memory: source context in recall results

Use after recall_arbitrate_v3() to enrich selected results with source context.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import load_config
from ..storage import SuperMemoryStore

logger = logging.getLogger("super-memory.recall.line_citations")

DEFAULT_NEIGHBOR_LINES = 3  # lines of context before/after matched line
MAX_CITATION_CHARS = 4000   # max chars per citation expansion


# ── Line Number Utilities ─────────────────────────────────────────────────

ESTIMATED_LINE_LENGTH = 80  # conservative estimate for offset→line conversion


def _offset_to_line(offset: int) -> int:
    """Convert character offset to estimated line number."""
    return offset // ESTIMATED_LINE_LENGTH + 1


def _extract_line_range(content: str, line_start: int, line_end: int) -> str:
    """Extract a range of lines from content."""
    lines = content.split("\n")
    start = max(0, line_start - 1)
    end = min(len(lines), line_end)
    return "\n".join(lines[start:end])


def _find_line_numbers(content: str, search_text: str) -> dict[str, int]:
    """Find the line number range of search_text within content.

    Returns {line_start, line_end} or None if not found.
    """
    try:
        idx = content.index(search_text)
    except (ValueError, IndexError):
        return {"line_start": 0, "line_end": 0}
    lines_before = content[:idx].count("\n")
    line_end = lines_before + search_text.count("\n")
    return {"line_start": lines_before + 1, "line_end": line_end + 1}


# ── Evidence Citation ─────────────────────────────────────────────────────

def build_citation(
    memory_id: str,
    content: str,
    source: str = "",
    line_start: int = 0,
    line_end: int = 0,
) -> dict[str, Any]:
    """Build a structured citation for a memory.

    Includes:
    - memory_id: canonical ID
    - source: source path/URL
    - line_start, line_end: line range
    - excerpt: ±neighbor_lines context
    - citation string for display
    """
    if line_start == 0 and line_end == 0:
        lines = _find_line_numbers(content, content[:min(len(content), 200)])
        line_start = lines["line_start"]
        line_end = lines["line_end"]

    excerpt = _extract_line_range(content, line_start, line_end)

    citation_str = f"📄 {source or 'memory'} L{line_start}-L{line_end}"
    if memory_id:
        citation_str += f" [{memory_id[:8]}]"

    return {
        "memory_id": memory_id,
        "source": source,
        "line_start": line_start,
        "line_end": line_end,
        "excerpt": excerpt,
        "citation": citation_str,
    }


def build_citations_from_recall(
    recall_result: dict[str, Any],
    max_chars: int = MAX_CITATION_CHARS,
    neighbor_lines: int = DEFAULT_NEIGHBOR_LINES,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Build enriched citations from a recall_arbitrate_v3() result.

    For each selected result, adds:
    - line numbers (from source metadata or content estimation)
    - neighbor context (±N lines)
    - source file path
    - formatted citation string
    """
    selected = recall_result.get("selected", [])
    if not selected:
        return {"ok": True, "query": recall_result.get("query", ""), "citations": [], "count": 0}

    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    citations = []
    total_chars = 0

    for sel in selected:
        record = sel.get("record", {})
        mem_id = record.get("id", "")
        content = record.get("content", "")
        source = record.get("source", "")

        # Try to get source path from metadata
        meta = record.get("metadata", {}) or {}
        file_path = meta.get("file") or meta.get("source") or source

        # Get offset info from closets if available
        line_start = meta.get("line_start", 0)
        line_end = meta.get("line_end", 0)

        if line_start == 0:
            # Estimate from content
            lines = _find_line_numbers(content, content[:min(len(content), 300)])
            line_start = lines.get("line_start", 1)
            line_end = lines.get("line_end", min(len(content.split("\n")), 50))

        # Expand neighbors
        expanded_start = max(1, line_start - neighbor_lines)
        expanded_end = line_end + neighbor_lines
        excerpt = _extract_line_range(content, expanded_start, expanded_end)

        if len(excerpt) > 500:
            excerpt = excerpt[:497] + "..."

        citation_str = f"📄 {file_path or 'memory'} L{line_start}-L{line_end}"
        if mem_id:
            citation_str += f" [{mem_id[:8]}]"

        total_chars += len(excerpt)
        if total_chars > max_chars:
            break

        citations.append({
            "memory_id": mem_id,
            "source": file_path or "",
            "line_start": line_start,
            "line_end": line_end,
            "expanded_range": f"L{expanded_start}-L{expanded_end}",
            "excerpt": excerpt,
            "score": sel.get("score", 0),
            "citation": citation_str,
            "why": sel.get("why", {}),
        })

    return {
        "ok": True,
        "query": recall_result.get("query", ""),
        "citations": citations,
        "count": len(citations),
    }


# ── Source File Tracking ──────────────────────────────────────────────────

def track_memory_source(
    memory_id: str,
    file_path: str,
    line_start: int = 0,
    content_hash: str = "",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Register source file tracking for a memory.

    This lets recall returns know which file and line range a memory
    originated from, enabling neighbor expansion and source citations.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    # Store in projection_meta
    from ..projections.drift_repair import register_projection
    result = register_projection(
        "source_tracking",
        memory_id,
        f"{file_path}:L{line_start}",
        content_hash=content_hash,
        config_path=config_path,
    )

    return {
        "ok": True,
        "memory_id": memory_id,
        "file_path": file_path,
        "line_start": line_start,
        "registered": result.get("ok", False),
    }


def resolve_source_tracking(
    memory_id: str,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Resolve source tracking for a memory."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    try:
        with store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projection_meta WHERE memory_id=? AND table_name='source_tracking' ORDER BY created_at DESC LIMIT 1",
                (memory_id,),
            ).fetchone()
    except Exception:
        row = None

    if not row:
        return {"ok": True, "memory_id": memory_id, "found": False}

    key = (row.get("projection_key") or "").split(":L")
    file_path = key[0] if key else ""
    line_start = int(key[1]) if len(key) > 1 and key[1].isdigit() else 0

    return {
        "ok": True,
        "memory_id": memory_id,
        "found": True,
        "file_path": file_path,
        "line_start": line_start,
        "content_hash": row.get("content_hash", ""),
    }
