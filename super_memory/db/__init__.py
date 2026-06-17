"""Database adapter layer for Super-Memory.

Provides a pluggable adapter pattern so the same service code works
with SQLite (default) or PostgreSQL (experimental).

Backward-compatible: also re-exports DBMixin, validate_*, row_dicts
from the legacy _db_legacy module so existing imports continue to work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export legacy helpers for backward compatibility
from .._db_legacy import (
    DBMixin,
    row_dicts,
    validate_agent_scope,
    validate_session_scope,
    validate_status,
)
from .base import AbstractDBAdapter
from .sqlite import SQLiteAdapter

if TYPE_CHECKING:
    from ..config import SuperMemoryConfig


def get_adapter(config: "SuperMemoryConfig") -> AbstractDBAdapter:
    """Factory: return the appropriate DB adapter for the current config.

    - If POSTGRES_URL env is set, returns PostgresAdapter (experimental).
    - Otherwise, returns SQLiteAdapter (default).
    """
    import os

    if os.environ.get("POSTGRES_URL"):
        try:
            from .postgres import PostgresAdapter
            return PostgresAdapter(config)
        except ImportError:
            pass

    return SQLiteAdapter(config)


__all__ = [
    "AbstractDBAdapter",
    "DBMixin",
    "SQLiteAdapter",
    "get_adapter",
    "row_dicts",
    "validate_agent_scope",
    "validate_session_scope",
    "validate_status",
]
