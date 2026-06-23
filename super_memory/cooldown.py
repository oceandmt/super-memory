"""Tool cooldown manager for Super Memory.

Implements timeout + cooldown pattern matching OpenClaw memory-core:
- 15s deadline per search/recall call
- 60s cooldown cache on unrecoverable errors
- Abort signal for in-flight work
"""

from __future__ import annotations

import time
import threading
from typing import Any, Callable


# ── Cooldown state ──────────────────────────────────────────────────────────


class CooldownEntry:
    """Tracks one cooldown period for a key (agent/query type)."""

    __slots__ = ("until", "error", "reason")

    def __init__(self, until: float, error: str, reason: str = "") -> None:
        self.until = until
        self.error = error
        self.reason = reason


class CooldownManager:
    """Thread-safe cooldown cache for search/recall tools.

    Matches memory-core behaviour:
    - On unrecoverable error → cache error for COOLDOWN_MS (default 60s)
    - On success or transient error → no cooldown
    - Auto-evicts expired entries on read
    """

    COOLDOWN_MS = 60_000  # 60 seconds

    def __init__(self) -> None:
        self._entries: dict[str, CooldownEntry] = {}
        self._lock = threading.Lock()

    def _now(self) -> float:
        return time.time()

    def check(self, key: str) -> str | None:
        """Return cached error string if key is in cooldown, else None."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._now() < entry.until:
                return entry.error
            # Expired — remove
            del self._entries[key]
            return None

    def record_error(self, key: str, error: str, reason: str = "") -> None:
        """Cache an unrecoverable error for COOLDOWN_MS."""
        with self._lock:
            self._entries[key] = CooldownEntry(
                until=self._now() + self.COOLDOWN_MS / 1000.0,
                error=error,
                reason=reason,
            )

    def record_success(self, key: str) -> None:
        """Clear any cooldown for this key on success."""
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        """Clear all cooldowns."""
        with self._lock:
            self._entries.clear()

    @property
    def active_count(self) -> int:
        now = self._now()
        with self._lock:
            return sum(1 for e in self._entries.values() if e.until > now)


# ── Deadline / Timeout ──────────────────────────────────────────────────────


class Deadline:
    """15-second timeout helper for search/recall tools.

    Usage:
        deadline = Deadline(timeout_ms=15000)
        result = deadline.run(lambda: expensive_search())
        if deadline.timed_out:
            # handle timeout
    """

    DEFAULT_TIMEOUT_MS = 15_000

    def __init__(self, timeout_ms: int | None = None) -> None:
        self._timeout_ms = timeout_ms or self.DEFAULT_TIMEOUT_MS
        self._deadline = time.monotonic() + self._timeout_ms / 1000.0
        self._timed_out = False
        self._cancelled = False

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    @property
    def remaining_ms(self) -> float:
        remaining = max(0.0, self._deadline - time.monotonic())
        return remaining * 1000.0

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self._deadline

    def check(self) -> None:
        """Raise TimeoutError if deadline exceeded."""
        if self._cancelled:
            raise CancelledError("Operation cancelled")
        if self.expired:
            self._timed_out = True
            raise TimeoutError(f"Operation timed out after {self._timeout_ms}ms")

    def run(self, fn: Callable[[], Any]) -> Any:
        """Run a callable with deadline enforcement.

        The callable should periodically call self.check() for cooperative
        cancellation, or wrap I/O calls with remaining_ms for blocking ops.
        """
        try:
            result = fn()
            if self.expired:
                self._timed_out = True
                raise TimeoutError(f"Operation timed out after {self._timeout_ms}ms")
            return result
        except (TimeoutError, CancelledError):
            self._timed_out = True
            raise

    def cancel(self) -> None:
        """Mark as cancelled."""
        self._cancelled = True

    def reset(self) -> None:
        """Reset deadline to now + timeout_ms."""
        self._deadline = time.monotonic() + self._timeout_ms / 1000.0
        self._timed_out = False
        self._cancelled = False


class TimeoutError(Exception):
    """Raised when a search/recall operation exceeds its deadline."""


class CancelledError(Exception):
    """Raised when a search/recall operation is cancelled."""


# ── Global singleton ────────────────────────────────────────────────────────

_cooldown_manager: CooldownManager | None = None


def get_cooldown_manager() -> CooldownManager:
    global _cooldown_manager
    if _cooldown_manager is None:
        _cooldown_manager = CooldownManager()
    return _cooldown_manager


def reset_cooldown_manager() -> None:
    global _cooldown_manager
    _cooldown_manager = None
