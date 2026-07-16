"""Regression tests for the thread-local SQLite connection lifecycle."""

from __future__ import annotations

import gc
import os
import queue
import sqlite3
import threading
import time
from pathlib import Path

import pytest

import super_memory.storage as storage
from super_memory.models import SuperMemoryConfig
from super_memory.storage import (
    SuperMemoryStore,
    close_all_connections,
    close_current_thread_connections,
    connection_cache_size,
)
from super_memory.storage_base import SQLiteCoreStorage


@pytest.fixture(autouse=True)
def clean_connection_cache():
    close_all_connections()
    yield
    close_all_connections()


def _store(tmp_path: Path, name: str = "lifecycle.sqlite3") -> SuperMemoryStore:
    config = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path=f"data/{name}")
    return SuperMemoryStore(config)


def _fd_count() -> int:
    proc_fds = Path("/proc/self/fd")
    if not proc_fds.is_dir():
        pytest.skip("file-descriptor regression requires /proc/self/fd")
    return len(list(proc_fds.iterdir()))


def test_short_lived_threads_release_cached_connections_and_fds(tmp_path: Path):
    store = _store(tmp_path)
    # Create the file and WAL configuration before concurrent readers start.
    store.connect().execute("SELECT 1").fetchone()
    store.close()

    baseline_cache = connection_cache_size()
    baseline_fds = _fd_count()
    thread_count = 24
    connected = threading.Barrier(thread_count + 1)
    release = threading.Barrier(thread_count + 1)
    errors: queue.Queue[BaseException] = queue.Queue()

    def worker() -> None:
        try:
            conn = store.connect()
            assert conn.execute("SELECT 1").fetchone()[0] == 1
            connected.wait(timeout=10)
            release.wait(timeout=10)
        except BaseException as exc:  # surfaced in the parent thread below
            errors.put(exc)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    connected.wait(timeout=10)

    assert connection_cache_size() == baseline_cache + thread_count
    assert _fd_count() >= baseline_fds + thread_count

    release.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    if not errors.empty():
        raise errors.get()

    # CPython releases thread-local values at thread exit.  The bounded retry
    # also makes the assertion portable to runtimes with deferred collection.
    for _ in range(20):
        gc.collect()
        if connection_cache_size() == baseline_cache and _fd_count() <= baseline_fds + 3:
            break
        time.sleep(0.01)

    assert connection_cache_size() == baseline_cache
    assert _fd_count() <= baseline_fds + 3


def test_explicit_current_store_and_all_close_hooks(tmp_path: Path):
    first = _store(tmp_path, "first.sqlite3")
    second = _store(tmp_path, "second.sqlite3")
    first_conn = first.connect()
    second_conn = second.connect()
    assert connection_cache_size() == 2

    first.close()
    assert connection_cache_size() == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        first_conn.execute("SELECT 1")
    assert second_conn.execute("SELECT 1").fetchone()[0] == 1

    # The backend close contract delegates to the current-store hook.
    SQLiteCoreStorage(second).close()
    assert connection_cache_size() == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        second_conn.execute("SELECT 1")

    first.connect()
    second.connect()
    close_current_thread_connections(first.path)
    assert connection_cache_size() == 1

    worker_ready = threading.Event()
    worker_release = threading.Event()
    worker_conn: queue.Queue[sqlite3.Connection] = queue.Queue()

    def worker() -> None:
        worker_conn.put(first.connect())
        worker_ready.set()
        worker_release.wait(timeout=10)

    thread = threading.Thread(target=worker)
    thread.start()
    assert worker_ready.wait(timeout=10)
    remote_conn = worker_conn.get(timeout=1)
    assert connection_cache_size() == 2

    # Shutdown must also close handles owned by other live threads.
    close_all_connections()
    assert connection_cache_size() == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        remote_conn.execute("SELECT 1")

    worker_release.set()
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_pid_change_discards_inherited_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = _store(tmp_path)
    inherited = store.connect()
    assert connection_cache_size() == 1

    # Simulate the PID mismatch observed on first storage access after fork.
    monkeypatch.setattr(storage, "_connection_pid", os.getpid() - 1)
    replacement = store.connect()

    assert replacement is not inherited
    assert replacement.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        inherited.execute("SELECT 1")
    assert connection_cache_size() == 1
