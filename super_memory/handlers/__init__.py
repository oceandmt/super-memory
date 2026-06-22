"""Handler registry — collects all tool handlers by domain group."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .core import get_core_handlers, get_recall_handlers, get_working_memory_handlers, get_search_index_handlers, get_sanitize_handlers
from .cognitive import get_cognitive_handlers
from .lifecycle import get_lifecycle_handlers
from .quality import get_quality_handlers
from .graph import get_graph_handlers
from .ops import (
    get_safety_handlers,
    get_diagnostics_handlers,
    get_sync_handlers,
    get_durable_pack_handlers,
    get_optional_heavy_handlers,
    get_leitner_handlers,
    get_local_handlers,
)

if TYPE_CHECKING:
    from .base import ToolHandler


# ── Global registry ───────────────────────────────────────────────────────────

def get_all_handlers() -> list[ToolHandler]:
    """Return every registered ToolHandler across all domain groups."""
    collectors = [
        get_core_handlers,
        get_recall_handlers,
        get_working_memory_handlers,
        get_search_index_handlers,
        get_sanitize_handlers,
        get_cognitive_handlers,
        get_lifecycle_handlers,
        get_quality_handlers,
        get_graph_handlers,
        get_safety_handlers,
        get_diagnostics_handlers,
        get_sync_handlers,
        get_durable_pack_handlers,
        get_optional_heavy_handlers,
        get_leitner_handlers,
        get_local_handlers,
    ]
    handlers: list[ToolHandler] = []
    seen: set[str] = set()
    for collect in collectors:
        for h in collect():
            if h.name not in seen:
                seen.add(h.name)
                handlers.append(h)
    return handlers


def get_handler(name: str) -> ToolHandler | None:
    """Lookup a handler by tool name."""
    for h in get_all_handlers():
        if h.name == name:
            return h
    return None


def get_handler_map() -> dict[str, ToolHandler]:
    """Return {name: handler} dict for O(1) lookup."""
    return {h.name: h for h in get_all_handlers()}


__all__ = [
    "get_all_handlers",
    "get_handler",
    "get_handler_map",
]
