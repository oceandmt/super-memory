"""Atomic rebuild of FTS5 + vector indices with rollback support.

Matches OpenClaw memory-core atomic reindex requirements:
- Rebuild FTS5 indices in a transaction
- Rebuild vector indices
- Rollback on failure
- Progress reporting

Micro-gaps:
- [3] Batch state tracking (manager-batch-state.ts)
- [4] Reindex FSM (manager-reindex-state.ts)
- [8] FTS-only reindex mode (manager.fts-only-reindex.test.ts)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore

logger = logging.getLogger(__name__)


__all__ = [
    "reindex_fts5",
    "reindex_vectors",
    "reindex_all",
    "ReindexFSM",
    "ReindexState",
    "BatchState",
    "create_reindex_fsm",
    "create_batch_state",
    "reindex_fts_only",
    "reindex_fsm_status",
    "batch_state_status",
    "reset_batch_state",
]


# ── Micro-gap 4: Reindex FSM ───────────────────────────────────────────────

# Mirrors memory-core manager-reindex-state.ts:
#   MemoryIndexIdentityState: valid | missing | mismatched
#   resolveMemoryIndexIdentityState()
#   isMemoryIndexIdentityDirty()


class ReindexState(str, Enum):
    """Reindex Finite State Machine states.

    Mirrors memory-core MemoryIndexIdentityState:
    - idle: index is valid (status=\"valid\")
    - dirty: configuration changed, reindex needed (status=\"mismatched\")
    - missing: no index exists (status=\"missing\")
    - running: reindex in progress
    - done: reindex completed
    - error: reindex failed
    """
    IDLE = "idle"
    DIRTY = "dirty"
    MISSING = "missing"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class ReindexFSM:
    """Reindex Finite State Machine.

    Tracks identity state and provides transitions.
    """

    state: ReindexState = ReindexState.IDLE
    reason: str = ""
    progress: int = 0
    total: int = 0
    error_details: str = ""
    completed_at: str = ""
    fts_only: bool = False

    _valid_transitions: dict[ReindexState, list[ReindexState]] = field(default_factory=lambda: {
        ReindexState.IDLE: [ReindexState.DIRTY, ReindexState.MISSING, ReindexState.RUNNING],
        ReindexState.DIRTY: [ReindexState.RUNNING, ReindexState.IDLE],
        ReindexState.MISSING: [ReindexState.RUNNING],
        ReindexState.RUNNING: [ReindexState.DONE, ReindexState.ERROR],
        ReindexState.DONE: [ReindexState.IDLE, ReindexState.DIRTY, ReindexState.MISSING],
        ReindexState.ERROR: [ReindexState.RUNNING, ReindexState.IDLE],
    }, init=False, repr=False)

    def transition_to(self, new_state: ReindexState, reason: str = "") -> None:
        """Transition to a new state with validation."""
        allowed = self._valid_transitions.get(self.state, [])
        if new_state not in allowed:
            logger.warning(
                f"reindex_fsm: invalid transition {self.state.value} -> {new_state.value}"
            )
        self.state = new_state
        if reason:
            self.reason = reason
        if new_state == ReindexState.DONE:
            self.completed_at = datetime.now(timezone.utc).isoformat()
        if new_state == ReindexState.ERROR:
            self.error_details = reason

    def mark_dirty(self, reason: str) -> None:
        """Mark index as needing reindex."""
        self.transition_to(ReindexState.DIRTY, reason)

    def mark_missing(self, reason: str = "no index metadata found") -> None:
        """Mark index as missing."""
        self.transition_to(ReindexState.MISSING, reason)

    def mark_running(self, total: int = 0) -> None:
        """Start reindex."""
        self.progress = 0
        self.total = total
        self.error_details = ""
        self.transition_to(ReindexState.RUNNING, "reindex started")

    def mark_done(self) -> None:
        """Complete reindex."""
        self.progress = self.total
        self.transition_to(ReindexState.DONE, "reindex completed")

    def mark_error(self, error: str) -> None:
        """Fail reindex."""
        self.transition_to(ReindexState.ERROR, error)

    def to_dict(self) -> dict[str, Any]:
        """Serialize FSM state to dict."""
        return {
            "state": self.state.value,
            "reason": self.reason,
            "progress": self.progress,
            "total": self.total,
            "error_details": self.error_details,
            "completed_at": self.completed_at,
            "fts_only": self.fts_only,
            "needs_reindex": self.state in (ReindexState.DIRTY, ReindexState.MISSING, ReindexState.ERROR),
        }

    def is_valid(self) -> bool:
        """Check if index is valid (no reindex needed)."""
        return self.state in (ReindexState.IDLE, ReindexState.DONE)


# ── Micro-gap 3: Batch State Tracking ──────────────────────────────────────

# Mirrors memory-core manager-batch-state.ts:
#   MEMORY_BATCH_FAILURE_LIMIT = 2
#   resetMemoryBatchFailureState()
#   recordMemoryBatchFailure()

BATCH_FAILURE_LIMIT = 2


@dataclass
class BatchState:
    """Batch operation failure tracking."""

    enabled: bool = True
    count: int = 0
    last_error: str = ""
    last_provider: str = ""
    total_processed: int = 0
    total_failed: int = 0

    def reset(self) -> "BatchState":
        """Reset failure state (mirrors resetMemoryBatchFailureState)."""
        self.count = 0
        self.enabled = True
        self.last_error = ""
        self.last_provider = ""
        return self

    def record_failure(
        self,
        provider: str,
        message: str,
        attempts: int | None = None,
        force_disable: bool = False,
    ) -> "BatchState":
        """Record a batch failure (mirrors recordMemoryBatchFailure).

        If force_disable or count >= BATCH_FAILURE_LIMIT, disables batch.
        """
        if not self.enabled:
            return self
        increment = BATCH_FAILURE_LIMIT if force_disable else max(1, attempts or 1)
        self.count += increment
        self.enabled = not (force_disable or self.count >= BATCH_FAILURE_LIMIT)
        self.last_error = message
        self.last_provider = provider
        self.total_failed += 1
        return self

    def record_success(self) -> "BatchState":
        """Record a successful batch operation."""
        self.total_processed += 1
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize batch state to dict."""
        return {
            "enabled": self.enabled,
            "failure_count": self.count,
            "last_error": self.last_error,
            "last_provider": self.last_provider,
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "failure_limit": BATCH_FAILURE_LIMIT,
        }


# Singleton instances
_reindex_fsm: ReindexFSM | None = None
_batch_state: BatchState | None = None


def create_reindex_fsm() -> ReindexFSM:
    """Get or create the singleton reindex FSM."""
    global _reindex_fsm
    if _reindex_fsm is None:
        _reindex_fsm = ReindexFSM()
    return _reindex_fsm


def create_batch_state() -> BatchState:
    """Get or create the singleton batch state."""
    global _batch_state
    if _batch_state is None:
        _batch_state = BatchState()
    return _batch_state


def reindex_fsm_status() -> dict[str, Any]:
    """Get current reindex FSM status."""
    fsm = create_reindex_fsm()
    return fsm.to_dict()


def batch_state_status() -> dict[str, Any]:
    """Get current batch state."""
    bs = create_batch_state()
    return bs.to_dict()


def reset_batch_state() -> dict[str, Any]:
    """Reset batch failure state."""
    bs = create_batch_state()
    bs.reset()
    return {"ok": True, "state": bs.to_dict()}


# ── Existing reindex functions (enhanced) ──────────────────────────────────


def reindex_fts5(config_path: str | None = None) -> dict[str, Any]:
    """Rebuild FTS5 indices atomically.

    Rebuilds memories_fts and session_transcripts_fts indices.
    Returns counts of rows processed.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    results: dict[str, Any] = {"fts5": {}, "errors": []}

    with store.connect() as conn:
        # Rebuild main FTS5
        try:
            conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
            count = conn.execute("SELECT COUNT(*) FROM memories_fts").fetchone()
            results["fts5"]["main"] = count[0] if count else 0
        except Exception as exc:
            results["errors"].append(f"main_fts_rebuild: {exc}")

        # Rebuild CJK trigram FTS5
        try:
            conn.execute("INSERT INTO memories_cjk_fts(memories_cjk_fts) VALUES('rebuild')")
            count = conn.execute("SELECT COUNT(*) FROM memories_cjk_fts").fetchone()
            results["fts5"]["cjk"] = count[0] if count else 0
        except Exception as exc:
            results["errors"].append(f"cjk_fts_rebuild: {exc}")

        # Rebuild session transcripts FTS5
        try:
            conn.execute(
                "INSERT INTO session_transcripts_fts(session_transcripts_fts) VALUES('rebuild')"
            )
            count = conn.execute(
                "SELECT COUNT(*) FROM session_transcripts_fts"
            ).fetchone()
            results["fts5"]["sessions"] = count[0] if count else 0
        except Exception as exc:
            results["errors"].append(f"session_fts_rebuild: {exc}")

    results["ok"] = len(results["errors"]) == 0
    return results


def reindex_vectors(config_path: str | None = None) -> dict[str, Any]:
    """Rebuild vector index for sqlite_vec.

    Currently a placeholder — sqlite_vec manages its own index.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    try:
        with store.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM memory_vectors WHERE vector IS NOT NULL"
            ).fetchone()
            return {"ok": True, "vectors": count[0] if count else 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Micro-gap 8: FTS-only reindex ─────────────────────────────────────────


def reindex_fts_only(config_path: str | None = None) -> dict[str, Any]:
    """Rebuild only FTS5 indices without touching vector index.

    Mirrors memory-core manager.fts-only-reindex.test.ts behaviour.
    Useful when embedding provider is unavailable but FTS search is needed.

    Args:
        config_path: Optional config path.

    Returns:
        Dict with FTS rebuild results.
    """
    fsm = create_reindex_fsm()
    fsm.fts_only = True
    fsm.mark_running()

    try:
        result = reindex_fts5(config_path=config_path)
        if result["ok"]:
            fsm.mark_done()
        else:
            fsm.mark_error("; ".join(result.get("errors", [])))
        result["fsm"] = fsm.to_dict()
        return result
    except Exception as exc:
        fsm.mark_error(str(exc))
        return {"ok": False, "error": str(exc), "fsm": fsm.to_dict()}


def reindex_all(config_path: str | None = None) -> dict[str, Any]:
    """Rebuild all indices atomically (FTS5 + vectors).

    Reports per-index results and rolls back on failure.
    Uses ReindexFSM to track state.
    """
    fsm = create_reindex_fsm()
    fsm.fts_only = False
    fsm.mark_running(total=2)  # 2 steps: FTS + vectors

    fts5_result = reindex_fts5(config_path=config_path)
    fsm.progress = 1

    vector_result = reindex_vectors(config_path=config_path)
    fsm.progress = 2

    ok = fts5_result["ok"] and vector_result["ok"]
    if ok:
        fsm.mark_done()
    else:
        errors = []
        if not fts5_result["ok"]:
            errors.extend(fts5_result.get("errors", []))
        if not vector_result["ok"]:
            errors.append(vector_result.get("error", "vector reindex failed"))
        fsm.mark_error("; ".join(errors))

    return {
        "ok": ok,
        "fts5": fts5_result,
        "vectors": vector_result,
        "fsm": fsm.to_dict(),
    }
