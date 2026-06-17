"""Abstract base class for database adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractDBAdapter(ABC):
    """Abstract database adapter.

    All backend-specific adapters must implement this interface so the
    rest of the codebase can remain database-agnostic.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the database."""
        ...

    @abstractmethod
    def execute(self, sql: str, params: tuple | None = None) -> Any:
        """Execute a SQL statement and return a cursor-like object."""
        ...

    @abstractmethod
    def executemany(self, sql: str, params_list: list[tuple]) -> Any:
        """Execute a SQL statement against all parameter sequences."""
        ...

    @abstractmethod
    def fetchone(self, cursor: Any) -> dict[str, Any] | None:
        """Fetch the next row from a cursor as a dict."""
        ...

    @abstractmethod
    def fetchall(self, cursor: Any) -> list[dict[str, Any]]:
        """Fetch all remaining rows from a cursor as dicts."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
        ...

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...
