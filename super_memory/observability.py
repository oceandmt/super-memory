from __future__ import annotations

import importlib.util
import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable

_HAS_STRUCTLOG = importlib.util.find_spec("structlog") is not None

if _HAS_STRUCTLOG:
    import structlog
    logger = structlog.get_logger("super-memory")
else:
    _fallback = logging.getLogger("super-memory")
    _fallback.setLevel(logging.INFO)
    if not _fallback.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter(
            '{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": %(message)s}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
        _fallback.addHandler(_h)
        _fallback.propagate = False
    logger = _fallback

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
    if _HAS_STRUCTLOG:
        logger.info("memory_op", **payload)
    else:
        logger.info(json.dumps(payload))


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


def prometheus_metrics() -> str:
    """Return in-process counters in Prometheus text exposition format."""
    lines: list[str] = []
    for name, value in sorted(_snapshot_counters().items()):
        metric = "super_memory_" + name.replace(".", "_").replace("-", "_")
        lines.append(f"# TYPE {metric} counter")
        lines.append(f"{metric} {value}")
    return "\n".join(lines) + ("\n" if lines else "")
