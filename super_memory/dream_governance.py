"""Shared governance for machine-generated dream and self-improvement proposals.

Generators may read evidence and create deterministic pending proposals, but
only an explicit resolver may apply a proposal. Dry runs never create the
queue schema or write queue rows.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

MAX_CONTENT_CHARS = 4_000
MAX_SOURCE_IDS = 64
MAX_EVIDENCE_ITEMS = 64
MAX_PROPOSALS_PER_RUN = 50
DEFAULT_APPLICATION_LEASE_SECONDS = 120
TERMINAL_STATES = frozenset({"approved", "rejected"})
GENERATED_AGENTS = frozenset({"dream-engine", "self-improvement-engine"})
GENERATED_SOURCE_PREFIXES = ("super-memory.dream", "self-improvement", "self_improvement")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8", errors="replace")).hexdigest()


def _bounded(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-safe, size-bounded evidence value."""
    if depth >= 4:
        return str(value)[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:2_000]
    if isinstance(value, dict):
        return {
            str(k)[:100]: _bounded(v, depth=depth + 1)
            for k, v in list(sorted(value.items(), key=lambda item: str(item[0])))[:MAX_EVIDENCE_ITEMS]
        }
    if isinstance(value, (list, tuple, set)):
        return [_bounded(v, depth=depth + 1) for v in list(value)[:MAX_EVIDENCE_ITEMS]]
    return str(value)[:2_000]


def normalize_source_ids(source_ids: Iterable[Any] | None) -> list[str]:
    return sorted({str(source_id)[:200] for source_id in (source_ids or []) if source_id})[:MAX_SOURCE_IDS]


def deterministic_run_key(namespace: str, *, inputs: Any, source_ids: Iterable[Any] | None = None) -> str:
    """Build a stable run/idempotency key without timestamps or process state."""
    digest = _digest({"inputs": _bounded(inputs), "source_ids": normalize_source_ids(source_ids)})
    return f"run:{namespace}:{digest[:32]}"


def build_proposal(
    *,
    kind: str,
    content: str,
    source_ids: Iterable[Any] | None = None,
    evidence: Any = None,
    action: Any = None,
    run_key: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic, bounded pending proposal."""
    clean_content = " ".join((content or "").split())[:MAX_CONTENT_CHARS]
    clean_sources = normalize_source_ids(source_ids)
    clean_evidence = _bounded(evidence or {})
    clean_action = _bounded(action or {})
    content_hash = hashlib.sha256(clean_content.encode("utf-8", errors="replace")).hexdigest()
    identity = {
        "kind": str(kind)[:100],
        "content_hash": content_hash,
        "source_ids": clean_sources,
        "action": clean_action,
    }
    proposal_id = f"proposal:{str(kind)[:32]}:{_digest(identity)[:32]}"
    return {
        "id": proposal_id,
        "kind": str(kind)[:100],
        "run_key": run_key or deterministic_run_key(str(kind), inputs=identity, source_ids=clean_sources),
        "content": clean_content,
        "content_hash": content_hash,
        "source_ids": clean_sources,
        "evidence": clean_evidence,
        "action": clean_action,
        "status": "pending",
    }

@contextmanager
def readonly_connection(store: Any):
    """Open an existing SQLite database without creating or mutating it.

    ``SuperMemoryStore.connect()`` creates the parent directory/database and
    enables WAL. Generators use this helper for evidence reads so a dry run on
    a fresh workspace is a true filesystem no-op. Lightweight compatibility
    stores without a ``path`` attribute retain their supplied connection API.
    """
    path = getattr(store, "path", None)
    if path is None:
        with store.connect() as conn:
            yield conn
        return
    db_path = Path(path)
    if not db_path.is_file():
        yield None
        return
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        yield conn
    finally:
        conn.close()


def ensure_schema(store: Any) -> None:
    """Create the additive governance queue schema. Never call from dry-run."""
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_proposals (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                run_key TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_ids_json TEXT NOT NULL DEFAULT '[]',
                evidence_json TEXT NOT NULL DEFAULT '{}',
                action_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                resolution_note TEXT,
                canonical_memory_id TEXT,
                application_token TEXT,
                application_lease_until TEXT,
                application_attempts INTEGER NOT NULL DEFAULT 0,
                application_error TEXT
            )
            """
        )
        existing = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(generated_proposals)").fetchall()
        }
        additions = {
            "application_token": (
                "ALTER TABLE generated_proposals ADD COLUMN application_token TEXT"
            ),
            "application_lease_until": (
                "ALTER TABLE generated_proposals ADD COLUMN application_lease_until TEXT"
            ),
            "application_attempts": (
                "ALTER TABLE generated_proposals "
                "ADD COLUMN application_attempts INTEGER NOT NULL DEFAULT 0"
            ),
            "application_error": (
                "ALTER TABLE generated_proposals ADD COLUMN application_error TEXT"
            ),
        }
        for name, statement in additions.items():
            if name not in existing:
                conn.execute(statement)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_generated_proposals_status "
            "ON generated_proposals(status, kind)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_generated_proposals_hash "
            "ON generated_proposals(kind, content_hash)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_generated_proposals_application_lease "
            "ON generated_proposals(status, application_lease_until)"
        )


def _table_exists(conn: Any) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generated_proposals'"
    ).fetchone() is not None


def _row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        result = dict(row)
    else:
        columns = (
            "id", "kind", "run_key", "content", "content_hash", "source_ids_json",
            "evidence_json", "action_json", "status", "created_at", "resolved_at",
            "resolution_note", "canonical_memory_id",
        )
        result = dict(zip(columns, row))
    for raw, clean, fallback in (
        ("source_ids_json", "source_ids", []),
        ("evidence_json", "evidence", {}),
        ("action_json", "action", {}),
    ):
        try:
            result[clean] = json.loads(result.get(raw) or json.dumps(fallback))
        except (TypeError, ValueError):
            result[clean] = fallback
        result.pop(raw, None)
    return result


def get_proposal(store: Any, proposal_id: str) -> dict[str, Any] | None:
    with readonly_connection(store) as conn:
        if conn is None or not _table_exists(conn):
            return None
        row = conn.execute("SELECT * FROM generated_proposals WHERE id=?", (proposal_id,)).fetchone()
    return _row_dict(row) if row else None


def canonical_content_exists(store: Any, content_hash: str) -> str | None:
    """Return an active canonical memory id matching a content hash, if any."""
    try:
        with readonly_connection(store) as conn:
            if conn is None:
                return None
            row = conn.execute(
                "SELECT id FROM memories WHERE content_hash=? "
                "AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1 "
                "ORDER BY CASE WHEN layer='workspace_markdown' THEN 0 ELSE 1 END LIMIT 1",
                (content_hash,),
            ).fetchone()
        if not row:
            return None
        return str(row["id"] if hasattr(row, "keys") else row[0])
    except Exception:
        return None


def enqueue_proposal(store: Any, proposal: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    """Deduplicate then enqueue a proposal; dry-run performs reads only."""
    existing = get_proposal(store, proposal["id"])
    if existing:
        return {"ok": True, "created": False, "deduplicated": True, "proposal": existing}
    if dry_run:
        preview = dict(proposal)
        preview["would_enqueue"] = True
        return {"ok": True, "created": False, "deduplicated": False, "proposal": preview}

    ensure_schema(store)
    with store.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO generated_proposals "
            "(id, kind, run_key, content, content_hash, source_ids_json, evidence_json, action_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                proposal["id"], proposal["kind"], proposal["run_key"], proposal["content"],
                proposal["content_hash"], _stable_json(proposal["source_ids"]),
                _stable_json(proposal["evidence"]), _stable_json(proposal["action"]), _now(),
            ),
        )
    stored = get_proposal(store, proposal["id"])
    return {"ok": True, "created": True, "deduplicated": False, "proposal": stored or proposal}


def list_proposals(store: Any, *, kind: str | None = None, status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 500))
    with readonly_connection(store) as conn:
        if conn is None or not _table_exists(conn):
            return []
        if kind is None:
            rows = conn.execute(
                "SELECT * FROM generated_proposals WHERE status=? ORDER BY created_at DESC, id LIMIT ?",
                (status, bounded_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM generated_proposals WHERE status=? AND kind=? ORDER BY created_at DESC, id LIMIT ?",
                (status, kind, bounded_limit),
            ).fetchall()
    return [_row_dict(row) for row in rows]


def _terminal_resolution(proposal_id: str, proposal: dict[str, Any], decision: str) -> dict[str, Any]:
    current = str(proposal.get("status") or "")
    same = current == decision
    return {
        "ok": same,
        "id": proposal_id,
        "status": current,
        "idempotent": same,
        "no_op": same,
        "error": None if same else "conflicting_terminal_state",
        "canonical_memory_id": proposal.get("canonical_memory_id"),
    }


def resolve_proposal(
    store: Any,
    proposal_id: str,
    *,
    decision: str,
    apply: Callable[[dict[str, Any]], str | None] | None = None,
    note: str | None = None,
    lease_seconds: int = DEFAULT_APPLICATION_LEASE_SECONDS,
) -> dict[str, Any]:
    """Resolve one proposal with an owned, recoverable application lease.

    Approval claims ``pending -> applying`` before invoking the executor. Only
    the holder token can finalize or release that claim. A process crash may
    cause the executor to be retried after lease expiry, so executors must use
    deterministic identifiers; the built-in dream executor does. This gives
    exactly-once canonical effects without pretending an external side effect
    can share SQLite's transaction.
    """
    if decision not in TERMINAL_STATES:
        return {"ok": False, "error": "invalid_decision", "decision": decision}
    if decision == "approved" and apply is None:
        return {"ok": False, "error": "approval_executor_required", "id": proposal_id}

    ensure_schema(store)
    proposal = get_proposal(store, proposal_id)
    if proposal is None:
        return {"ok": False, "error": "not_found", "id": proposal_id}
    current = str(proposal.get("status") or "")
    if current in TERMINAL_STATES:
        return _terminal_resolution(proposal_id, proposal, decision)

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    bounded_note = (note or "")[:1_000]

    if decision == "rejected":
        with store.connect() as conn:
            cur = conn.execute(
                "UPDATE generated_proposals SET status='rejected', resolved_at=?, "
                "resolution_note=?, application_token=NULL, "
                "application_lease_until=NULL WHERE id=? AND status='pending'",
                (now, bounded_note, proposal_id),
            )
        if cur.rowcount:
            return {
                "ok": True,
                "id": proposal_id,
                "status": "rejected",
                "canonical_memory_id": None,
                "idempotent": False,
            }
        replay = get_proposal(store, proposal_id)
        if replay and replay.get("status") in TERMINAL_STATES:
            return _terminal_resolution(proposal_id, replay, decision)
        return {
            "ok": False,
            "error": "resolution_in_flight",
            "id": proposal_id,
            "status": replay and replay.get("status"),
        }

    token = secrets.token_hex(16)
    lease_until = (
        now_dt + timedelta(seconds=max(0, int(lease_seconds)))
    ).isoformat()
    with store.connect() as conn:
        claimed = conn.execute(
            """
            UPDATE generated_proposals
            SET status='applying', application_token=?, application_lease_until=?,
                application_attempts=application_attempts+1, application_error=NULL
            WHERE id=?
              AND (status='pending' OR
                   (status='applying' AND
                    (application_lease_until IS NULL OR application_lease_until<=?)))
            """,
            (token, lease_until, proposal_id, now),
        ).rowcount
    if not claimed:
        replay = get_proposal(store, proposal_id)
        if replay and replay.get("status") in TERMINAL_STATES:
            return _terminal_resolution(proposal_id, replay, decision)
        return {
            "ok": False,
            "error": "application_in_flight",
            "id": proposal_id,
            "status": replay and replay.get("status"),
            "lease_until": replay and replay.get("application_lease_until"),
        }

    owned = get_proposal(store, proposal_id) or proposal
    canonical_memory_id: str | None = None
    try:
        canonical_memory_id = apply(owned) if apply is not None else None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:2_000]
        with store.connect() as conn:
            released = conn.execute(
                """
                UPDATE generated_proposals
                SET status='pending', application_token=NULL,
                    application_lease_until=NULL, application_error=?
                WHERE id=? AND status='applying' AND application_token=?
                """,
                (error, proposal_id, token),
            ).rowcount
        return {
            "ok": False,
            "error": f"apply_failed:{error}",
            "id": proposal_id,
            "status": "pending" if released else "ownership_lost",
        }

    with store.connect() as conn:
        finalized = conn.execute(
            """
            UPDATE generated_proposals
            SET status='approved', resolved_at=?, resolution_note=?,
                canonical_memory_id=?, application_token=NULL,
                application_lease_until=NULL, application_error=NULL
            WHERE id=? AND status='applying' AND application_token=?
            """,
            (now, bounded_note, canonical_memory_id, proposal_id, token),
        ).rowcount
    if not finalized:
        replay = get_proposal(store, proposal_id)
        if replay and replay.get("status") == "approved":
            return _terminal_resolution(proposal_id, replay, decision)
        return {
            "ok": False,
            "error": "application_ownership_lost",
            "id": proposal_id,
            "status": replay and replay.get("status"),
            "canonical_memory_id": replay and replay.get("canonical_memory_id"),
        }
    return {
        "ok": True,
        "id": proposal_id,
        "status": "approved",
        "canonical_memory_id": canonical_memory_id,
        "idempotent": False,
    }

def is_generated_record(*, agent_id: str | None, source: str | None, metadata: dict[str, Any] | None = None) -> bool:
    """Guard against feeding generated output back into generation."""
    if (agent_id or "") in GENERATED_AGENTS:
        return True
    lowered_source = (source or "").lower()
    if any(lowered_source.startswith(prefix) for prefix in GENERATED_SOURCE_PREFIXES):
        return True
    meta = metadata or {}
    return bool(meta.get("generated_by") or meta.get("governance_proposal_id") or meta.get("self_improvement_generated"))
