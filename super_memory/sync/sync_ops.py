"""Sync operations — interval-based sync with startup catchup.

Mirrors memory-core manager-sync-ops.ts:
- Periodic sync at configurable interval
- Startup catchup: detect and sync missed changes
- Sync state tracking (pending/active/done/error)
- Delta sync: only sync changed memories
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Thread, Event
from typing import Any, Callable

logger = logging.getLogger(__name__)


__all__ = [
    "SyncIntervalConfig",
    "SyncState",
    "SyncStatus",
    "SyncManager",
    "create_sync_manager",
    "sync_interval_status",
    "sync_startup_catchup",
]


class SyncState(str, Enum):
    """Sync operation state."""
    IDLE = "idle"
    PENDING = "pending"
    SYNCING = "syncing"
    DONE = "done"
    ERROR = "error"


@dataclass
class SyncIntervalConfig:
    """Configuration for interval-based sync.

    Mirrors memory-core interval sync config:
    - interval_seconds: how often to sync (default 300 = 5 min)
    - startup_catchup: sync on init (default True)
    - catchup_window_minutes: how far back to check for missed changes
    """
    interval_seconds: int = 300
    startup_catchup: bool = True
    catchup_window_minutes: int = 60
    enabled: bool = True


@dataclass
class SyncStatus:
    """Current sync status."""
    state: SyncState = SyncState.IDLE
    last_sync_at: str = ""
    last_sync_duration_ms: float = 0
    last_error: str = ""
    items_synced: int = 0
    items_failed: int = 0
    total_syncs: int = 0
    config: SyncIntervalConfig = field(default_factory=SyncIntervalConfig)


class SyncManager:
    """Interval-based sync manager with startup catchup."""

    def __init__(self, config: SyncIntervalConfig | None = None):
        self.config = config or SyncIntervalConfig()
        self.status = SyncStatus(config=self.config)
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._sync_fn: Callable[[], dict[str, Any]] | None = None
        self._dirty_sources: set[str] = set()
        self._last_catchup: float = 0.0

    def set_sync_fn(self, sync_fn: Callable[[], dict[str, Any]]) -> None:
        """Set the actual sync function to call."""
        self._sync_fn = sync_fn

    def mark_dirty(self, source: str = "memory") -> None:
        """Mark a source as needing sync."""
        self._dirty_sources.add(source)
        if self.status.state == SyncState.IDLE:
            self.status.state = SyncState.PENDING

    def clear_dirty(self) -> None:
        """Clear all dirty markers."""
        self._dirty_sources.clear()

    @property
    def has_dirty(self) -> bool:
        """Check if any sources need sync."""
        return len(self._dirty_sources) > 0

    def run_startup_catchup(self) -> dict[str, Any]:
        """Run startup catchup — detect and sync missed changes."""
        if not self.config.startup_catchup:
            return {"ok": True, "note": "startup catchup disabled"}

        self.status.state = SyncState.SYNCING
        try:
            result = self._do_sync(catchup=True)
            self._last_catchup = time.time()
            return result
        except Exception as exc:
            self.status.state = SyncState.ERROR
            self.status.last_error = str(exc)
            return {"ok": False, "error": str(exc)}

    def _do_sync(self, catchup: bool = False) -> dict[str, Any]:
        """Internal sync execution."""
        t0 = time.time()
        if self._sync_fn:
            try:
                result = self._sync_fn()
                synced = result.get("synced", result.get("items_synced", 1))
                self.status.items_synced += synced
                self.status.last_sync_at = datetime.now(timezone.utc).isoformat()
                self.status.state = SyncState.DONE
            except Exception as exc:
                self.status.items_failed += 1
                self.status.last_error = str(exc)
                self.status.state = SyncState.ERROR
                result = {"ok": False, "error": str(exc)}
        else:
            self.status.items_synced += 0
            self.status.last_sync_at = datetime.now(timezone.utc).isoformat()
            self.status.state = SyncState.DONE
            result = {"ok": True, "note": "no sync function configured", "synced": 0}

        duration = (time.time() - t0) * 1000
        self.status.last_sync_duration_ms = duration
        self.status.total_syncs += 1
        self.clear_dirty()

        result["duration_ms"] = round(duration, 1)
        result["catchup"] = catchup
        return result

    def sync_once(self) -> dict[str, Any]:
        """Execute a single sync operation."""
        self.status.state = SyncState.SYNCING
        return self._do_sync(catchup=False)

    def start_interval(self) -> dict[str, Any]:
        """Start periodic sync in background thread."""
        if self._thread and self._thread.is_alive():
            return {"ok": True, "already_running": True}

        if not self.config.enabled:
            return {"ok": False, "error": "sync disabled"}

        self._stop_event.clear()
        self._thread = Thread(target=self._interval_loop, daemon=True, name="sync-interval")
        self._thread.start()

        catchup_result = self.run_startup_catchup()

        return {
            "ok": True,
            "interval_seconds": self.config.interval_seconds,
            "startup_catchup": catchup_result,
        }

    def stop_interval(self) -> dict[str, Any]:
        """Stop periodic sync."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self.status.state = SyncState.IDLE
        return {"ok": True}

    def _interval_loop(self) -> None:
        """Background sync loop."""
        while not self._stop_event.is_set():
            if self.has_dirty or self._should_sync():
                try:
                    self._do_sync(catchup=False)
                except Exception as exc:
                    logger.error(f"sync_ops: interval sync failed: {exc}")
                    self.status.last_error = str(exc)
                    self.status.items_failed += 1
            self._stop_event.wait(self.config.interval_seconds)

    def _should_sync(self) -> bool:
        """Check if enough time has passed since last sync."""
        if not self.status.last_sync_at:
            return True
        try:
            last = datetime.fromisoformat(self.status.last_sync_at)
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            return elapsed >= self.config.interval_seconds
        except Exception:
            return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize sync status."""
        return {
            "state": self.status.state.value,
            "last_sync_at": self.status.last_sync_at,
            "last_sync_duration_ms": self.status.last_sync_duration_ms,
            "last_error": self.status.last_error,
            "items_synced": self.status.items_synced,
            "items_failed": self.status.items_failed,
            "total_syncs": self.status.total_syncs,
            "dirty_sources": list(self._dirty_sources),
            "interval_running": self._thread is not None and self._thread.is_alive(),
            "config": {
                "interval_seconds": self.config.interval_seconds,
                "startup_catchup": self.config.startup_catchup,
                "catchup_window_minutes": self.config.catchup_window_minutes,
                "enabled": self.config.enabled,
            },
        }


# ── Singleton ──────────────────────────────────────────────────────────────

_sync_manager: SyncManager | None = None


def create_sync_manager(config: SyncIntervalConfig | None = None) -> SyncManager:
    """Get or create the singleton sync manager."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager(config=config)
    return _sync_manager


def sync_interval_status() -> dict[str, Any]:
    """Get current sync interval status."""
    mgr = create_sync_manager()
    return mgr.to_dict()


def sync_startup_catchup(sync_fn: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Run startup catchup — sync missed changes."""
    mgr = create_sync_manager()
    if sync_fn:
        mgr.set_sync_fn(sync_fn)
    return mgr.run_startup_catchup()
