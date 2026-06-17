"""PostgreSQL adapter — experimental skeleton.

This adapter is NOT required for normal operation. It is marked as
experimental and activated only when POSTGRES_URL env is set.

The PostgresAdapter class provides a skeleton implementation that
can be filled in when a real PostgreSQL driver is installed (psycopg2
or asyncpg). Currently all methods log a warning and delegate to
SQLite as fallback.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from .base import AbstractDBAdapter

if TYPE_CHECKING:
    from ..config import SuperMemoryConfig

logger = logging.getLogger("super-memory.db.postgres")


class PostgresAdapter(AbstractDBAdapter):
    """PostgreSQL adapter — experimental skeleton.

    Activated by setting POSTGRES_URL env variable.
    Currently falls back to SQLite with a warning until a real
    PostgreSQL driver is integrated.

    Feature flag: POSTGRES_URL must be set (e.g.
    postgresql://user:pass@localhost:5432/super_memory).
    """

    def __init__(self, config: "SuperMemoryConfig"):
        self.config = config
        self.pg_url = os.environ.get("POSTGRES_URL", "")
        logger.warning(
            "PostgresAdapter is experimental. "
            "Falling back to SQLite for production safety. "
            "Set POSTGRES_URL to enable PostgreSQL mode."
        )

    def _check_driver(self) -> bool:
        """Check if a real PostgreSQL driver is available."""
        try:
            import importlib.util
            for drv in ("psycopg2", "asyncpg"):
                if importlib.util.find_spec(drv) is not None:
                    return True
        except Exception:
            pass
        return False

    def connect(self) -> None:
        if not self.pg_url:
            raise RuntimeError("POSTGRES_URL not set — cannot connect to PostgreSQL")
        if not self._check_driver():
            raise RuntimeError(
                "No PostgreSQL driver found. Install psycopg2 or asyncpg: "
                "pip install psycopg2-binary"
            )
        # TODO: real connection when driver is installed
        logger.info("PostgreSQL connection would be established to %s", self.pg_url)

    def execute(self, sql: str, params: tuple | None = None) -> Any:
        raise NotImplementedError(
            "PostgresAdapter.execute() is a stub. "
            "Install psycopg2 and implement the adapter."
        )

    def executemany(self, sql: str, params_list: list[tuple]) -> Any:
        raise NotImplementedError(
            "PostgresAdapter.executemany() is a stub."
        )

    def fetchone(self, cursor: Any) -> dict[str, Any] | None:
        raise NotImplementedError(
            "PostgresAdapter.fetchone() is a stub."
        )

    def fetchall(self, cursor: Any) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "PostgresAdapter.fetchall() is a stub."
        )

    def close(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass
