from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .fingerprint import build_fingerprint
from .migrations import ensure_schema


def make_source_event_key(
    metadata: dict[str, Any] | None,
    content_hash: str,
    *,
    source: str | None = None,
) -> str | None:
    meta = metadata or {}
    explicit = meta.get("idempotency_key") or meta.get("source_event_key")
    if explicit:
        return str(explicit)
    message_id = meta.get("message_id") or meta.get("event_id") or meta.get("source_event_id")
    if message_id:
        src = source or meta.get("source") or meta.get("source_adapter") or "openclaw"
        chat_id = meta.get("chat_id") or meta.get("conversation_label") or meta.get("channel") or ""
        sender_id = meta.get("sender_id") or meta.get("sender") or meta.get("username") or ""
        return hashlib.sha256(f"{src}:{chat_id}:{message_id}:{sender_id}:{content_hash}".encode()).hexdigest()
    return None


def claim_write_intent(conn: Any, record: Any, *, lease_seconds: int = 120) -> dict[str, Any]:
    """Atomically reserve a source event before its canonical write.

    Calls without a stable source event key remain untracked and are allowed;
    content-level dedup still applies to them.  A live ``pending`` claim fails
    closed so concurrent retries cannot both write.  Failed or expired claims
    can be recovered by a new owner.
    """
    ensure_schema(conn)
    metadata = getattr(record, "metadata", {}) or {}
    content = getattr(record, "content", "") or ""
    source = getattr(record, "source", None) or metadata.get("source_adapter") or "direct"
    fingerprint = build_fingerprint(content)
    key = make_source_event_key(metadata, fingerprint.normalized_hash, source=source)
    if not key:
        return {
            "claimed": True,
            "tracked": False,
            "reason": "no_source_event_key",
            "normalized_hash": fingerprint.normalized_hash,
        }

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    lease_until = (now_dt + timedelta(seconds=max(0, lease_seconds))).isoformat()
    claim_token = secrets.token_hex(16)
    intent_id = hashlib.sha256(key.encode()).hexdigest()
    event_id = metadata.get("message_id") or metadata.get("event_id") or metadata.get("source_event_id")
    values = (
        intent_id,
        key,
        source,
        event_id,
        getattr(record, "agent_id", None),
        getattr(record, "session_id", None),
        getattr(record, "project", None),
        fingerprint.normalized_hash,
        fingerprint.simhash,
        claim_token,
        lease_until,
        now,
        now,
    )
    inserted = conn.execute(
        """
        INSERT OR IGNORE INTO memory_write_intents
        (id, idempotency_key, source_adapter, source_event_id, agent_id,
         session_id, project, normalized_hash, simhash, status, claim_token,
         lease_until, attempts, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 1, ?, ?)
        """,
        values,
    ).rowcount
    if inserted:
        return {
            "claimed": True,
            "tracked": True,
            "reason": "new",
            "intent_id": intent_id,
            "idempotency_key": key,
            "claim_token": claim_token,
            "lease_until": lease_until,
            "attempts": 1,
            "normalized_hash": fingerprint.normalized_hash,
        }

    row = conn.execute(
        """
        SELECT status, memory_id, lease_until, attempts
        FROM memory_write_intents WHERE idempotency_key=?
        """,
        (key,),
    ).fetchone()
    if row is None:  # Defensive: a concurrent rollback/deletion may have won.
        return {"claimed": False, "tracked": True, "reason": "claim_race", "idempotency_key": key}
    status, memory_id, existing_lease, attempts = row
    if status == "saved":
        return {
            "claimed": False,
            "tracked": True,
            "reason": "saved_replay",
            "idempotency_key": key,
            "memory_id": memory_id,
            "attempts": attempts,
        }

    reclaimed = conn.execute(
        """
        UPDATE memory_write_intents
        SET status='pending', claim_token=?, lease_until=?, attempts=attempts+1,
            updated_at=?, completed_at=NULL, error=NULL
        WHERE idempotency_key=?
          AND (status='failed' OR (status='pending' AND (lease_until IS NULL OR lease_until<=?)))
        """,
        (claim_token, lease_until, now, key, now),
    ).rowcount
    if reclaimed:
        return {
            "claimed": True,
            "tracked": True,
            "reason": "recovered",
            "intent_id": intent_id,
            "idempotency_key": key,
            "claim_token": claim_token,
            "lease_until": lease_until,
            "attempts": int(attempts or 0) + 1,
            "normalized_hash": fingerprint.normalized_hash,
        }
    return {
        "claimed": False,
        "tracked": True,
        "reason": "in_flight",
        "idempotency_key": key,
        "memory_id": memory_id,
        "lease_until": existing_lease,
        "attempts": attempts,
    }


def mark_write_intent_saved(conn: Any, claim: dict[str, Any], memory_id: str) -> bool:
    """Complete an owned claim; stale owners cannot complete a newer lease."""
    if not claim.get("tracked"):
        return True
    now = datetime.now(timezone.utc).isoformat()
    return bool(
        conn.execute(
            """
            UPDATE memory_write_intents
            SET status='saved', memory_id=?, completed_at=?, updated_at=?,
                claim_token=NULL, lease_until=NULL, error=NULL
            WHERE idempotency_key=? AND status='pending' AND claim_token=?
            """,
            (memory_id, now, now, claim.get("idempotency_key"), claim.get("claim_token")),
        ).rowcount
    )


def mark_write_intent_failed(conn: Any, claim: dict[str, Any], error: str) -> bool:
    """Release an owned claim for retry while retaining bounded diagnostics."""
    if not claim.get("tracked"):
        return True
    now = datetime.now(timezone.utc).isoformat()
    return bool(
        conn.execute(
            """
            UPDATE memory_write_intents
            SET status='failed', error=?, completed_at=?, updated_at=?,
                claim_token=NULL, lease_until=NULL
            WHERE idempotency_key=? AND status='pending' AND claim_token=?
            """,
            (str(error)[:2000], now, now, claim.get("idempotency_key"), claim.get("claim_token")),
        ).rowcount
    )
