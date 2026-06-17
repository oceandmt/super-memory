from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable

import structlog

logger = structlog.get_logger("super-memory")

# ── Counter registry (in-process, resets on restart) ──────────────────────────
_counters: dict[str, int] = {}


def _inc(name: str, delta: int = 1) -> None:
    _counters[name] = _counters.get(name, 0) + delta


def _snapshot_counters() -> dict[str, int]:
    return dict(_counters)


# ── Public helpers ────────────────────────────────────────────────────────────

def log_op(
    operation: str,
    latency_ms: float,
    *,
    ok: bool = True,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a structured operation log entry."""
    _inc(operation)
    _inc(f"{operation}.{'ok' if ok else 'fail'}")
    payload: dict[str, Any] = {
        "op": operation,
        "latency_ms": round(latency_ms, 3),
        "ok": ok,
    }
    if extra:
        payload.update(extra)
    logger.info("memory_op", **payload)


@contextmanager
def traced(operation: str, *, extra: Callable[[], dict[str, Any]] | None = None):
    """Context manager that logs the start, end, and latency of an operation."""
    start = time.perf_counter()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        elapsed = (time.perf_counter() - start) * 1_000
        ex = extra() if extra else {}
        log_op(operation, elapsed, ok=ok, extra=ex)


def metrics() -> dict[str, Any]:
    """Return a lightweight metrics snapshot."""
    return {
        "counters": _snapshot_counters(),
    }
