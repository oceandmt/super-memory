"""Eternal context — session-start injection from curated memories.

Ported from neural-memory v4.58.0 core/eternal_context.py.
"""
from __future__ import annotations
import json, logging
__all__ = ["EternalContext"]
from typing import Any

logger = logging.getLogger("super-memory.eternal")

class EternalContext:
    """Manages session-start context injection from pinned memories."""

    def __init__(self, store: Any) -> None:
        """Initialize EternalContext with storage backend."""
        self._store = store
        self._message_count = 0

    def get_injection(self, level: int = 1) -> str:
        """Get session-start context injection.

        Level 1: quick (~500 tokens)
        Level 2: detailed (~1300 tokens)
        Level 3: full (~3300 tokens)
        """
        try:
            if level == 1:
                return self._get_quick_context()
            elif level == 2:
                return self._get_detailed_context()
            else:
                return self._get_full_context()
        except Exception as e:
            logger.debug("eternal context failed: %s", e)
            return "[Context unavailable]"

    def _get_quick_context(self) -> str:
        """Get quick (~500 tokens) session context."""
        lines = ["[Eternal Context]"]
        with self._store.connect() as conn:
            pinned = conn.execute(
                "SELECT content, type, created_at FROM memories "
                "WHERE (json_extract(metadata_json, '$.pinned') = 1 OR scope = 'shared') "
                "AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1 "
                "AND type IN ('decision', 'doctrine', 'instruction') "
                "ORDER BY rowid DESC LIMIT 5"
            ).fetchall()
        for r in pinned:
            content = (r["content"] or "")[:100]
            lines.append(f"  [{r['type']}] {content}")
        return "\n".join(lines)

    def _get_detailed_context(self) -> str:
        """Get detailed (~1300 tokens) session context."""
        lines = ["[Eternal Context — Detailed]"]
        with self._store.connect() as conn:
            pinned = conn.execute(
                "SELECT content, type, created_at FROM memories "
                "WHERE (json_extract(metadata_json, '$.pinned') = 1 OR scope = 'shared') "
                "AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1 "
                "AND type IN ('decision', 'doctrine', 'instruction', 'workflow', 'lesson') "
                "ORDER BY rowid DESC LIMIT 12"
            ).fetchall()
        for r in pinned:
            content = (r["content"] or "")[:150]
            lines.append(f"  [{r['type']}] {content}")
        return "\n".join(lines)

    def _get_full_context(self) -> str:
        """Get full (~3300 tokens) session context."""
        lines = ["[Eternal Context — Full]"]
        with self._store.connect() as conn:
            pinned = conn.execute(
                "SELECT content, type, created_at FROM memories "
                "WHERE (json_extract(metadata_json, '$.pinned') = 1 OR scope = 'shared') "
                "AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1 "
                "ORDER BY rowid DESC LIMIT 30"
            ).fetchall()
        for r in pinned:
            content = (r["content"] or "")[:200]
            lines.append(f"  [{r['type']}] {content}")
        return "\n".join(lines)

    def increment_message_count(self) -> int:
        """Increment and return message counter."""
        self._message_count += 1
        return self._message_count