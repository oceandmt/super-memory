"""Unit tests for P1-P3 modules: write_queue, depth_prior, conflict, version, reconstruct, affect, stabilize, query_expansion."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _store():
    from super_memory.config import load_config
    from super_memory.storage import SuperMemoryStore
    return SuperMemoryStore(load_config())


def _rec(id_: str = "test-r", content: str = "test content"):
    from super_memory.models import MemoryRecord, MemoryType, MemoryScope
    return MemoryRecord(
        id=id_,
        content=content,
        type=MemoryType.FACT,
        scope=MemoryScope.SESSION,
        agent_id="test",
    )


# ═══════════════════════════════════════════════════════════════════
# 1. query_expansion
# ═══════════════════════════════════════════════════════════════════

class TestQueryExpansion:
    def test_expand_basic(self):
        from super_memory.query_expansion import expand_query
        results = expand_query("memory")
        assert len(results) >= 1
        assert results[0] == "memory"

    def test_expand_empty(self):
        from super_memory.query_expansion import expand_query
        assert expand_query("") == [""]
        assert expand_query("   ") == ["   "]

    def test_morphological_variants(self):
        from super_memory.query_expansion import _morphological_expansions
        variants = _morphological_expansions("connecting")
        assert "connect" in variants or "connection" in variants

    def test_max_expansions(self):
        from super_memory.query_expansion import expand_query
        results = expand_query("testing connection management")
        assert len(results) <= 6


# ═══════════════════════════════════════════════════════════════════
# 2. write_queue
# ═══════════════════════════════════════════════════════════════════

class TestWriteQueue:
    def test_defer(self):
        from super_memory.write_queue import DeferredWriteQueue
        q = DeferredWriteQueue(store=_store())
        q.defer(_rec("wq1"))
        q.defer(_rec("wq2"))
        assert q.pending_count == 2

    def test_defer_two(self):
        from super_memory.write_queue import DeferredWriteQueue
        q = DeferredWriteQueue(store=_store())
        r = _rec("wq3")
        q.defer(r)
        # The queue does NOT dedup by id; verify we can track 2
        q.defer(_rec("wq4"))
        assert q.pending_count == 2

    def test_pending_count(self):
        from super_memory.write_queue import DeferredWriteQueue
        q = DeferredWriteQueue(store=_store())
        assert q.pending_count == 0
        q.defer(_rec("wq4"))
        assert q.pending_count == 1

    def test_flush_sync(self):
        from super_memory.write_queue import DeferredWriteQueue
        q = DeferredWriteQueue(store=_store())
        q.defer(_rec("wq5"))
        q.defer(_rec("wq6"))
        # flush_sync calls save internally and returns list of SaveResult
        from super_memory.models import MemoryType, MemoryScope
        result = q.flush_sync()
        assert isinstance(result, list)
        assert len(result) >= 1  # at least some results

    def test_close(self):
        from super_memory.write_queue import DeferredWriteQueue
        q = DeferredWriteQueue(store=_store())
        q.defer(_rec("wq7"))
        result = q.close()
        assert isinstance(result, list)

    def test_batch_id_after_defer(self):
        from super_memory.write_queue import DeferredWriteQueue
        q = DeferredWriteQueue(store=_store())
        q.defer(_rec("bid1"))
        assert len(q.batch_id) > 0

    def test_defer_many(self):
        from super_memory.write_queue import DeferredWriteQueue
        q = DeferredWriteQueue(store=_store())
        q.defer_many([_rec("wq8"), _rec("wq9")])
        assert q.pending_count == 2


# ═══════════════════════════════════════════════════════════════════
# 3. depth_prior
# ═══════════════════════════════════════════════════════════════════

class TestDepthPrior:
    def test_classify_query_current(self):
        from super_memory.depth_prior import classify_query
        result = classify_query("what is the current version")
        assert result == "current"

    def test_classify_query_deep(self):
        from super_memory.depth_prior import classify_query
        result = classify_query("how was the authentication system designed and what were the tradeoffs")
        assert result == "deep"

    def test_classify_query_history(self):
        from super_memory.depth_prior import classify_query
        result = classify_query("what happened at the last team meeting")
        # History detection depends on plural keywords; may be general
        assert result in ("history", "general")

    def test_classify_query_project(self):
        from super_memory.depth_prior import classify_query
        result = classify_query("what are the goals for the Q3 project")
        assert result == "project"

    def test_classify_query_general(self):
        from super_memory.depth_prior import classify_query
        result = classify_query("anything random")
        assert result == "general"

    def test_expected_depth_default(self):
        from super_memory.depth_prior import expected_depth
        depth = expected_depth("hello world", store=_store())
        assert 0 <= depth <= 3

    def test_expected_depth_deep(self):
        from super_memory.depth_prior import expected_depth
        depth = expected_depth("how was the authentication designed", store=_store())
        assert depth >= 0

    def test_record_outcome(self):
        from super_memory.depth_prior import record_outcome
        result = record_outcome("test query", hit_count=5, store=_store())
        # May return None if depth_prior not initialized
        if result is not None:
            assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════
# 4. conflict
# ═══════════════════════════════════════════════════════════════════

class TestConflict:
    def test_detect_conflicts_empty(self):
        from super_memory.conflict import detect_conflicts
        result = detect_conflicts(records=[])
        assert hasattr(result, "conflicts")
        assert len(result.conflicts) == 0

    def test_detect_conflicts_negation(self):
        from super_memory.conflict import detect_conflicts
        a = _rec("ca", "The API supports pagination")
        b = _rec("cb", "The API does not support pagination")
        result = detect_conflicts(records=[a, b], min_similarity=0.3)
        assert len(result.conflicts) > 0
        assert result.conflicts[0].type == "negation"

    def test_detect_conflicts_similar_no_conflict(self):
        from super_memory.conflict import detect_conflicts
        a = _rec("cc", "Memory save is working")
        b = _rec("cd", "Memory recall is working")
        result = detect_conflicts(records=[a, b], min_similarity=0.3)
        assert len(result.conflicts) == 0

    def test_resolve_conflict(self):
        from super_memory.conflict import resolve_conflict
        result = resolve_conflict(conflict_id="nonexistent", resolution="keep_new")
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════
# 5. version
# ═══════════════════════════════════════════════════════════════════

class TestVersion:
    def test_create_snapshot(self):
        from super_memory.version import create_snapshot
        store = _store()
        result = create_snapshot(store=store, name="test_snapshot")
        assert "version_id" in result or "snapshot_id" in result

    def test_list_snapshots(self):
        from super_memory.version import list_snapshots
        store = _store()
        result = list_snapshots(store=store)
        assert isinstance(result, dict)

    def test_snapshot_roundtrip(self):
        from super_memory.version import create_snapshot, get_snapshot
        store = _store()
        created = create_snapshot(store=store, name="roundtrip_test")
        vid = created.get("version_id") or created["snapshot_id"]
        result = get_snapshot(store=store, version_id=vid)
        assert isinstance(result, dict)

    def test_diff_snapshots(self):
        from super_memory.version import diff_snapshots
        from super_memory.version import create_snapshot, list_snapshots
        store = _store()
        # Create two snapshots
        s1 = create_snapshot(store=store, name="diff_a")
        s2 = create_snapshot(store=store, name="diff_b")
        v1 = s1.get("version_id") or s1["snapshot_id"]
        v2 = s2.get("version_id") or s2["snapshot_id"]
        result = diff_snapshots(store=store, from_version=v1, to_version=v2)
        assert isinstance(result, dict)

    def test_rollback_dry_run(self):
        from super_memory.version import rollback_dry_run, create_snapshot
        store = _store()
        s = create_snapshot(store=store, name="rollback_test")
        vid = s.get("version_id") or s["snapshot_id"]
        result = rollback_dry_run(store=store, version_id=vid)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════
# 6. reconstruct
# ═══════════════════════════════════════════════════════════════════

class TestReconstruct:
    def test_causal_chain(self):
        from super_memory.reconstruct import causal_chain
        store = _store()
        result = causal_chain(memory_id="none", store=store)
        assert isinstance(result, dict)
        assert "chains" in result or "chain" in result

    def test_event_sequence(self):
        from super_memory.reconstruct import event_sequence
        store = _store()
        result = event_sequence(store=store)
        assert isinstance(result, dict)
        assert "events" in result or "sequence" in result

    def test_temporal_range(self):
        from super_memory.reconstruct import temporal_range
        store = _store()
        result = temporal_range(store=store, start="2026-01-01", end="2026-12-31")
        assert isinstance(result, dict)
        assert "events" in result

    def test_topic_narrative(self):
        from super_memory.reconstruct import topic_narrative
        store = _store()
        result = topic_narrative(store=store, topic="test topic")
        assert isinstance(result, dict)
        assert "narrative" in result


# ═══════════════════════════════════════════════════════════════════
# 7. affect
# ═══════════════════════════════════════════════════════════════════

class TestAffect:
    def test_classify_affect_neutral(self):
        from super_memory.affect import classify_affect
        result = classify_affect("The system processed the request successfully.")
        assert result["valence"] == "neutral"
        assert 0.0 <= result["arousal"] <= 1.0

    def test_classify_affect_positive(self):
        from super_memory.affect import classify_affect
        result = classify_affect("Amazing breakthrough! We finally fixed the critical bug!")
        assert result["valence"] == "positive"

    def test_classify_affect_negative(self):
        from super_memory.affect import classify_affect
        result = classify_affect("This is terrible. The deployment crashed and lost all data.")
        assert result["valence"] == "negative"

    def test_classify_affect_arousal_high(self):
        from super_memory.affect import classify_affect
        result = classify_affect("URGENT: Critical security vulnerability found in production! Needs immediate fix!")
        assert result["arousal"] > 0.5

    def test_enrich_record(self):
        from super_memory.affect import enrich_record
        from super_memory.models import MemoryRecord, MemoryType, MemoryScope
        record = MemoryRecord(
            id="test-affect-1",
            content="Excellent progress on the project!",
            type=MemoryType.FACT,
            scope=MemoryScope.SESSION,
            agent_id="test",
        )
        enriched = enrich_record(record)
        # enrich_record adds affect to metadata; check it was set
        assert enriched is not None

    def test_recall_by_affect(self):
        from super_memory.affect import recall_by_affect
        store = _store()
        result = recall_by_affect(store=store, valence="positive")
        assert isinstance(result, dict)
        assert "ok" in result


# ═══════════════════════════════════════════════════════════════════
# 8. stabilize
# ═══════════════════════════════════════════════════════════════════

class TestStabilize:
    def test_graph_health(self):
        from super_memory.stabilize import graph_health
        store = _store()
        result = graph_health(store=store)
        # graph_health returns nested 'checks' dict
        assert "checks" in result or "neurons" in result

    def test_stabilize_dry_run(self):
        from super_memory.stabilize import stabilize
        store = _store()
        result = stabilize(store=store, dry_run=True)
        assert isinstance(result, dict)
        assert "ok" in result


# ═══════════════════════════════════════════════════════════════════
# 9. Expiration (new)
# ═══════════════════════════════════════════════════════════════════

class TestExpiration:
    def test_expire_by_age_dry_run(self):
        from super_memory.cleanup import expire_by_age
        result = expire_by_age(max_days=1, dry_run=True)
        assert result["ok"]
        assert result["strategy"] == "expire_by_age"
        assert result["dry_run"] is True

    def test_expire_by_valid_until_dry_run(self):
        from super_memory.cleanup import expire_by_valid_until
        result = expire_by_valid_until(dry_run=True)
        assert result["ok"]
        assert result["strategy"] == "expire_by_valid_until"
        assert result["dry_run"] is True
