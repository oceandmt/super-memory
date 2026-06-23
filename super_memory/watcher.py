"""File watcher — monitor workspace files for changes and auto-index.

Matches OpenClaw memory-core watcher behaviour:
- Monitors .md files in workspace for changes
- Triggers re-index on file modification
- Respects ignore patterns
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore

logger = logging.getLogger(__name__)


# ── File hash tracking ─────────────────────────────────────────────────────


class FileWatcher:
    """Lightweight file watcher that tracks file modification hashes."""

    def __init__(self, config_path: str | None = None):
        self.cfg = load_config(config_path)
        self.store = SuperMemoryStore(self.cfg)
        self._file_hashes: dict[str, str] = {}
        self._watched_dirs: list[Path] = []
        self._exclude_patterns: list[str] = []
        self._running = False

    def add_watch(self, directory: str | Path) -> None:
        """Add a directory to watch."""
        path = Path(directory).resolve()
        if path.is_dir() and path not in self._watched_dirs:
            self._watched_dirs.append(path)
            logger.info(f"watcher: added watch {path}")

    def add_exclude(self, pattern: str) -> None:
        """Add a filename/glob exclude pattern."""
        self._exclude_patterns.append(str(pattern))

    def scan_once(self) -> list[dict[str, Any]]:
        """One-shot scan of all watched directories.

        Returns list of changed files with status.
        """
        changes: list[dict[str, Any]] = []
        for watch_dir in self._watched_dirs:
            for fpath in watch_dir.rglob("*.md"):
                if self._is_excluded(fpath):
                    continue
                status = self._check_file(fpath)
                if status:
                    changes.append(status)
        return changes

    def _is_excluded(self, path: Path) -> bool:
        for pattern in self._exclude_patterns:
            if pattern in str(path):
                return True
        return False

    def _check_file(self, path: Path) -> dict[str, Any] | None:
        path_str = str(path)
        try:
            content = path.read_bytes()
            current_hash = hashlib.sha256(content).hexdigest()
        except Exception:
            return None

        prev_hash = self._file_hashes.get(path_str)
        if prev_hash == current_hash:
            return None

        self._file_hashes[path_str] = current_hash
        if prev_hash is None:
            return {"path": path_str, "status": "added", "hash": current_hash}
        else:
            return {"path": path_str, "status": "modified", "hash": current_hash}

    def get_tracked_files(self) -> list[dict[str, Any]]:
        """List tracked files and their hashes."""
        return [
            {"path": p, "hash": h}
            for p, h in self._file_hashes.items()
        ]

    def clear(self) -> None:
        """Clear all tracked hashes."""
        self._file_hashes.clear()


# ── Convenience ────────────────────────────────────────────────────────────


def create_watcher(
    directories: list[str] | None = None,
    exclude: list[str] | None = None,
    config_path: str | None = None,
) -> FileWatcher:
    """Create and configure a FileWatcher."""
    watcher = FileWatcher(config_path=config_path)
    for d in directories or []:
        watcher.add_watch(d)
    for p in exclude or []:
        watcher.add_exclude(p)
    return watcher


def watcher_scan(
    directories: list[str] | None = None,
    exclude: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """One-shot scan using a temporary watcher."""
    watcher = create_watcher(directories, exclude, config_path)
    changes = watcher.scan_once()
    return {
        "ok": True,
        "changes": changes,
        "changed_count": len(changes),
    }


# ── Debounce / Settle (watch-pressure + watch-settle pattern) ────────────


class SettleQueue:
    """Settle queue with debounce timing (matches memory-core watch-settle).

    Records file events and can check if files have 'settled'
    (no more modifications happening) before processing them.
    """

    RECHECK_MS = 100  # Delay between settle rechecks

    def __init__(self):
        self._queue: dict[str, dict[str, float]] = {}  # path -> {size, mtime}

    def record_event(self, file_path: str) -> None:
        """Record a file change event."""
        try:
            stat = Path(file_path).stat()
            self._queue[file_path] = {
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        except OSError:
            pass

    def is_settled(self) -> bool:
        """Check if all queued files have settled (no changes since last record)."""
        if not self._queue:
            return True

        still_changing: dict[str, dict[str, float]] = {}
        for path_str, snapshot in self._queue.items():
            try:
                stat = Path(path_str).stat()
                current = {"size": stat.st_size, "mtime": stat.st_mtime}
                if current != snapshot:
                    still_changing[path_str] = current
            except OSError:
                pass

        if still_changing:
            self._queue = still_changing
            return False

        self._queue.clear()
        return True

    def settle(self, max_retries: int = 5) -> bool:
        """Wait for all queued files to settle, with retries.

        Returns True if settled, False if timeout.
        """
        for _ in range(max_retries):
            if self.is_settled():
                return True
            time.sleep(SettleQueue.RECHECK_MS / 1000.0)
        return self.is_settled()

    def pending_count(self) -> int:
        return len(self._queue)

    def clear(self) -> None:
        self._queue.clear()


# Singleton for persistent watcher state
_settle_queue: SettleQueue | None = None


def get_settle_queue() -> SettleQueue:
    global _settle_queue
    if _settle_queue is None:
        _settle_queue = SettleQueue()
    return _settle_queue


def watcher_settle_scan(
    directories: list[str] | None = None,
    exclude: list[str] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Debounced scan with settle detection.

    Records file changes, waits for settle, then scans.
    Prevents processing files that are still being written.
    """
    queue = get_settle_queue()
    watcher = create_watcher(directories, exclude, config_path)

    # Record current state
    for watch_dir in watcher._watched_dirs:
        for fpath in watch_dir.rglob("*.md"):
            if watcher._is_excluded(fpath):
                continue
            queue.record_event(str(fpath))

    # Wait for settle
    settled = queue.settle()

    # Now scan
    changes = watcher.scan_once()
    return {
        "ok": True,
        "changes": changes,
        "changed_count": len(changes),
        "settled": settled,
        "settle_pending": queue.pending_count(),
    }
