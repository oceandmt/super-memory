"""Flush plan — plan and execute memory-to-disk flush operations.

Matches OpenClaw memory-core MemoryFlushPlan behaviour:
- Tracks pending flushes (save operations not yet written to canonical markdown)
- Executes flush in batch
- Reports flush stats
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import load_config
from .models import MemoryLayer, MemoryScope
from .storage import SuperMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class FlushPlanEntry:
    """One pending flush operation."""

    memory_id: str
    content: str
    layer: str
    scope: str
    project: str | None = None
    agent_id: str | None = None
    status: str = "pending"


class FlushPlan:
    """Plan and execute batched memory flush to canonical markdown."""

    def __init__(self, config_path: str | None = None):
        self.cfg = load_config(config_path)
        self.store = SuperMemoryStore(self.cfg)
        self._entries: list[FlushPlanEntry] = []

    def plan_flush(
        self,
        limit: int = 100,
        min_priority: int = 3,
    ) -> list[FlushPlanEntry]:
        """Plan flush: find session-scoped memories that should be flushed to durable."""
        self._entries = []
        with self.store.connect() as conn:
            rows = conn.execute(
                """
                SELECT m.id, m.content, m.layer, m.scope, m.project, m.agent_id
                FROM memories m
                WHERE m.scope = ?
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (MemoryScope.SESSION.value, limit),
            ).fetchall()

        for row in rows:
            entry = FlushPlanEntry(
                memory_id=str(row[0]),
                content=str(row[1]),
                layer=str(row[2]),
                scope=str(row[3]),
                project=str(row[4]) if row[4] else None,
                agent_id=str(row[5]) if row[5] else None,
            )
            self._entries.append(entry)

        return self._entries

    def execute_flush(self) -> dict[str, Any]:
        """Execute all planned flushes — promote session -> project scope."""
        flushed = 0
        errors = 0

        for entry in self._entries:
            try:
                with self.store.connect() as conn:
                    conn.execute(
                        "UPDATE memories SET scope = ? WHERE id = ? AND layer = ?",
                        (MemoryScope.PROJECT.value, entry.memory_id, entry.layer),
                    )
                entry.status = "flushed"
                flushed += 1
            except Exception as exc:
                logger.error(f"flush_plan: error flushing {entry.memory_id}: {exc}")
                entry.status = "error"
                errors += 1

        self._entries.clear()
        return {
            "flushed": flushed,
            "errors": errors,
            "total": flushed + errors,
        }

    def pending_count(self) -> int:
        """Return number of pending flush candidates."""
        try:
            with self.store.connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE scope = ?",
                    (MemoryScope.SESSION.value,),
                ).fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def status(self) -> dict[str, Any]:
        """Return full flush status."""
        return {
            "pending": self.pending_count(),
            "entries_planned": len(self._entries),
        }


def flush_plan_status(config_path: str | None = None) -> dict[str, Any]:
    """Quick flush plan status check."""
    plan = FlushPlan(config_path=config_path)
    return plan.status()


def flush_session_memories(
    limit: int = 100,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Plan + execute flush of session-scoped memories to project scope."""
    plan = FlushPlan(config_path=config_path)
    plan.plan_flush(limit=limit)
    return plan.execute_flush()
