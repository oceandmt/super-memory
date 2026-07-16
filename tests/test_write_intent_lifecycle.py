from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from super_memory.write_contract import (
    claim_write_intent,
    ensure_schema,
    mark_write_intent_failed,
    mark_write_intent_saved,
    register_memory,
)


def _record(key: str | None = "evt-1", memory_id: str = "memory-1"):
    metadata = {"idempotency_key": key} if key else {}
    return SimpleNamespace(
        id=memory_id,
        content="canonical write intent payload",
        source="test",
        metadata=metadata,
        agent_id="agent-a",
        session_id="session-a",
        project="project-a",
    )


def _conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_claim_is_atomic_and_saved_replays(tmp_path):
    path = tmp_path / "intent.sqlite3"
    first = _conn(path)
    second = _conn(path)
    ensure_schema(first)
    first.commit()

    claim = claim_write_intent(first, _record(), lease_seconds=60)
    first.commit()
    assert claim["claimed"] is True

    duplicate = claim_write_intent(second, _record(), lease_seconds=60)
    second.commit()
    assert duplicate["claimed"] is False
    assert duplicate["reason"] == "in_flight"

    assert mark_write_intent_saved(first, claim, "memory-1") is True
    first.commit()
    replay = claim_write_intent(second, _record(), lease_seconds=60)
    assert replay == {
        "claimed": False,
        "tracked": True,
        "reason": "saved_replay",
        "idempotency_key": "evt-1",
        "memory_id": "memory-1",
        "attempts": 1,
    }
    first.close()
    second.close()


def test_failed_claim_is_recoverable_and_stale_owner_cannot_complete(tmp_path):
    conn = _conn(tmp_path / "recover.sqlite3")
    first = claim_write_intent(conn, _record(), lease_seconds=60)
    assert mark_write_intent_failed(conn, first, "temporary failure") is True
    recovered = claim_write_intent(conn, _record(), lease_seconds=60)
    assert recovered["claimed"] is True
    assert recovered["reason"] == "recovered"
    assert recovered["attempts"] == 2
    assert mark_write_intent_saved(conn, first, "wrong-owner") is False
    assert mark_write_intent_saved(conn, recovered, "memory-1") is True


def test_expired_pending_claim_can_be_recovered(tmp_path):
    conn = _conn(tmp_path / "expired.sqlite3")
    first = claim_write_intent(conn, _record(), lease_seconds=0)
    recovered = claim_write_intent(conn, _record(), lease_seconds=60)
    assert first["claimed"] is True
    assert recovered["claimed"] is True
    assert recovered["reason"] == "recovered"


def test_register_memory_cannot_finalize_an_owned_pending_claim(tmp_path):
    conn = _conn(tmp_path / "register.sqlite3")
    record = _record()
    claim = claim_write_intent(conn, record)
    assert claim["claimed"] is True

    # Fingerprint/outbox registration is not proof of claim ownership.  The
    # service must complete the intent with the token returned by claim().
    register_memory(conn, record, "workspace_markdown", enqueue_embed=False)
    row = conn.execute(
        "SELECT status, memory_id, claim_token FROM memory_write_intents WHERE idempotency_key=?",
        ("evt-1",),
    ).fetchone()
    assert tuple(row) == ("pending", None, claim["claim_token"])
    assert mark_write_intent_saved(conn, claim, "memory-1") is True


def test_register_memory_records_legacy_unclaimed_saved_write(tmp_path):
    conn = _conn(tmp_path / "legacy-register.sqlite3")
    record = _record()
    register_memory(conn, record, "workspace_markdown", enqueue_embed=False)
    row = conn.execute(
        "SELECT status, memory_id, claim_token FROM memory_write_intents WHERE idempotency_key=?",
        ("evt-1",),
    ).fetchone()
    assert tuple(row) == ("saved", "memory-1", None)


def test_unkeyed_write_is_allowed_without_intent_row(tmp_path):
    conn = _conn(tmp_path / "unkeyed.sqlite3")
    claim = claim_write_intent(conn, _record(key=None))
    assert claim["claimed"] is True
    assert claim["tracked"] is False
    assert conn.execute("SELECT COUNT(*) FROM memory_write_intents").fetchone()[0] == 0


def test_schema_upgrades_legacy_intent_table(tmp_path):
    conn = _conn(tmp_path / "legacy.sqlite3")
    conn.execute(
        "CREATE TABLE memory_write_intents (id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, "
        "normalized_hash TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    ensure_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_write_intents)")}
    assert {"memory_id", "claim_token", "lease_until", "attempts", "updated_at"} <= columns
