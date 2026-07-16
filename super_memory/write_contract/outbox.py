from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .fingerprint import build_fingerprint
from .idempotency import make_source_event_key
from .migrations import ensure_schema


def _job_id(memory_id: str, layer: str, job_type: str) -> str:
    return hashlib.sha256(f"{memory_id}:{layer}:{job_type}".encode()).hexdigest()


def register_memory(conn, record: Any, layer: str, *, enqueue_embed: bool = True) -> dict[str, Any]:
    """Register fingerprint + outbox jobs for an already-saved memory row.

    Safe to call repeatedly; uses INSERT OR IGNORE/REPLACE semantics.
    """
    ensure_schema(conn)
    metadata = getattr(record, "metadata", {}) or {}
    content = getattr(record, "content", "") or ""
    source = getattr(record, "source", None) or metadata.get("source_adapter") or "direct"
    fp0 = build_fingerprint(content)
    source_event_key = make_source_event_key(metadata, fp0.normalized_hash, source=source)
    fp = build_fingerprint(content, source_event_key=source_event_key)
    mid = getattr(record, "id")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO memory_fingerprints
        (memory_id, layer, normalized_hash, simhash, content_hash, source_event_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM memory_fingerprints WHERE memory_id=? AND layer=?), ?))
        """,
        (mid, layer, fp.normalized_hash, fp.simhash, fp.raw_hash, source_event_key, mid, layer, now),
    )
    if source_event_key and layer == "workspace_markdown":
        conn.execute(
            """
            INSERT INTO memory_write_intents
            (id, idempotency_key, source_adapter, source_event_id, agent_id,
             session_id, project, normalized_hash, simhash, status, memory_id,
             created_at, completed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'saved', ?, ?, ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET
              status='saved', memory_id=excluded.memory_id,
              completed_at=excluded.completed_at, updated_at=excluded.updated_at,
              claim_token=NULL, lease_until=NULL, error=NULL
            WHERE memory_write_intents.status != 'pending'
            """,
            (hashlib.sha256(source_event_key.encode()).hexdigest(), source_event_key, source,
             metadata.get("message_id") or metadata.get("event_id") or metadata.get("source_event_id"),
             getattr(record, "agent_id", None), getattr(record, "session_id", None), getattr(record, "project", None),
             fp.normalized_hash, fp.simhash, mid, now, now, now),
        )
    if enqueue_embed:
        for job_type in ("embed",):
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_jobs
                (id, memory_id, layer, job_type, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (_job_id(mid, layer, job_type), mid, layer, job_type, now, now),
            )
    return {"normalized_hash": fp.normalized_hash, "source_event_key": source_event_key, "simhash": fp.simhash}


def find_duplicate(conn, content: str, metadata: dict[str, Any] | None = None, *, source: str | None = None) -> dict[str, Any]:
    ensure_schema(conn)
    fp0 = build_fingerprint(content)
    source_event_key = make_source_event_key(metadata or {}, fp0.normalized_hash, source=source)
    fp = build_fingerprint(content, source_event_key=source_event_key)
    if source_event_key:
        row = conn.execute(
            "SELECT memory_id FROM memory_fingerprints WHERE source_event_key=? AND layer='workspace_markdown' LIMIT 1",
            (source_event_key,),
        ).fetchone()
        if row:
            return {"skipped": True, "matched_id": row["memory_id"], "reason": "source_event_replay"}
    row = conn.execute(
        "SELECT memory_id FROM memory_fingerprints WHERE normalized_hash=? AND layer='workspace_markdown' LIMIT 1",
        (fp.normalized_hash,),
    ).fetchone()
    if row:
        return {"skipped": True, "matched_id": row["memory_id"], "reason": "normalized_hash_duplicate"}
    return {"skipped": False, "normalized_hash": fp.normalized_hash, "source_event_key": source_event_key}


def job_status(conn) -> dict[str, Any]:
    ensure_schema(conn)
    rows = conn.execute("SELECT job_type, status, COUNT(*) c FROM memory_jobs GROUP BY job_type, status").fetchall()
    return {f"{r['job_type']}:{r['status']}": r['c'] for r in rows}
