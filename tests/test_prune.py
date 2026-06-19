"""Tests for retention policy prune and dedup_check."""

import json
import sqlite3

from super_memory.cleanup import _prune_candidate_ids, prune, cleanup
from super_memory.service import SuperMemoryService
from super_memory.config import load_config
from super_memory.models import MemoryRecord, MemoryType, MemoryScope


def test_sync_turn_skips_empty_content(tmp_path):
    """sync_turn must return [] when both user_message and assistant_message are empty."""
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    svc = SuperMemoryService(cfg)

    from super_memory.hooks import TurnContext
    for ctx in [
        TurnContext(agent_id="lucas"),
        TurnContext(agent_id="lucas", user_message="", assistant_message=""),
    ]:
        results = svc.sync_turn(ctx)
        assert results == [], f"Expected empty results for empty turn, got {results}"


def test_sync_turn_saves_nonempty(tmp_path):
    """sync_turn must save non-empty turns normally."""
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    svc = SuperMemoryService(cfg)

    from super_memory.hooks import TurnContext
    ctx = TurnContext(
        agent_id="lucas",
        session_id="test-session",
        user_message="hello",
        assistant_message="world",
    )
    results = svc.sync_turn(ctx)
    assert len(results) == 4, f"Expected 4 layer results, got {len(results)}"
    assert all(r.ok for r in results), f"All results should succeed: {[r.message for r in results if not r.ok]}"


def test_dedup_check_skips_identical_content(tmp_path):
    """remember() must skip identical content via dedup_check."""
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    svc = SuperMemoryService(cfg)

    record = MemoryRecord(content="exact duplicate test", type=MemoryType.FACT)
    first = svc.save(record)
    assert all(r.ok for r in first), f"First save failed: {[r.message for r in first if not r.ok]}"

    # Second save of identical content should be dedup'd
    dup = MemoryRecord(content="exact duplicate test", type=MemoryType.FACT)
    dedup = svc.dedup_check(dup)
    assert dedup["skipped"] is True, f"Expected dedup to skip, got {dedup}"


def test_dedup_check_allows_different_content(tmp_path):
    """remember() must NOT skip different content."""
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    svc = SuperMemoryService(cfg)

    record = MemoryRecord(content="first unique content", type=MemoryType.FACT)
    first = svc.save(record)
    assert all(r.ok for r in first)

    # Different content should not be dedup'd
    other = MemoryRecord(content="completely different content", type=MemoryType.FACT)
    dedup = svc.dedup_check(other)
    assert dedup["skipped"] is False, f"Expected no dedup, got {dedup}"


def test_prune_empty_openclaw_turn_dry_run(tmp_path):
    """prune dry_run must report empty openclaw.turn events without deleting."""
    cfg_path = tmp_path / "super-memory.yaml"
    db_path = tmp_path / "data"
    db_path.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    svc = SuperMemoryService(cfg)
    cleanup(config_path=str(cfg_path))  # ensure schema

    # Insert some empty openclaw.turn events directly
    record_empty = MemoryRecord(
        content="",
        type=MemoryType.EVENT,
        source="openclaw.turn",
        tags=["turn", "openclaw"],
    )
    svc.save(record_empty)
    record_empty2 = MemoryRecord(
        content="",
        type=MemoryType.EVENT,
        source="openclaw.turn",
        tags=["turn", "openclaw"],
    )
    svc.save(record_empty2)

    # Insert real content to make sure it's not caught
    record_real = MemoryRecord(content="real content", type=MemoryType.FACT)
    svc.save(record_real)

    report = prune(config_path=str(cfg_path), dry_run=True)
    assert report["ok"]
    assert report["result"]["candidate_ids"] >= 2, f"Expected >=2 candidates, got {report['result']['candidate_ids']}"
    assert report["result"]["dry_run"] is True
    assert report["result"]["pruned"] is None  # dry_run doesn't prune

    # Verify nothing was actually deleted
    status = svc.store.connect()
    count = status.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert count >= 12  # 2 empty * 4 layers + 1 real * 4 layers + schema+test mems


def test_prune_empty_openclaw_turn_with_prefix(tmp_path):
    """prune with source_prefix filter must delete matching + empty turns."""
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    svc = SuperMemoryService(cfg)
    cleanup(config_path=str(cfg_path))

    # Empty openclaw.turn
    svc.save(MemoryRecord(content="", type=MemoryType.EVENT, source="openclaw.turn"))
    # Test contract memory
    svc.save(MemoryRecord(content="Phase 8 contract memory test", type=MemoryType.FACT, source="test.my_contract"))
    # Keep real data
    svc.save(MemoryRecord(content="keep this real content", type=MemoryType.FACT))

    with svc.store.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    report = prune(
        config_path=str(cfg_path),
        dry_run=False,
        source_prefixes=["test."],
    )
    assert report["ok"]
    assert report["result"]["pruned"] is not None
    assert report["result"]["pruned"]["ids"] > 0

    with svc.store.connect() as conn:
        after = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert after < before

    # Real content must survive
    with svc.store.connect() as conn:
        kept = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE content LIKE '%keep this real%'"
        ).fetchone()[0]
    assert kept > 0, "Real content should survive prune"


def test_prune_max_days(tmp_path):
    """prune with max_days filter must skip fresh memories."""
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    svc = SuperMemoryService(cfg)
    cleanup(config_path=str(cfg_path))

    # Fresh memory (created now)
    svc.save(MemoryRecord(content="brand new memory", type=MemoryType.FACT))

    report = prune(
        config_path=str(cfg_path),
        dry_run=True,
        max_days=1,  # Only older than 1 day
    )
    assert report["ok"]
    assert report["result"]["candidate_ids"] == 0, (
        f"Expected 0 old candidates, got {report['result']['candidate_ids']}"
    )
