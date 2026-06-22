"""Tests for priming — session-aware recall weight modulation."""
from __future__ import annotations

import pytest
from super_memory.priming import PrimingTracker, SessionPriming, PrimingConfig


class TestPrimingTracker:
    def test_singleton(self):
        from super_memory.priming import get_priming_tracker
        t1 = get_priming_tracker()
        t2 = get_priming_tracker()
        assert t1 is t2

    def test_record_and_boost(self):
        pt = PrimingTracker()
        pt.record_access("s1", "n1", "python code", "deploy")
        boost = pt.get_priming_boost("s1", "n1")
        assert boost > 1.0, f"expected >1.0 for primed, got {boost}"

    def test_unprimed_no_boost(self):
        pt = PrimingTracker()
        pt.record_access("s1", "n1", "python code", "deploy")
        boost = pt.get_priming_boost("s1", "n2")
        assert boost == 1.0, f"expected 1.0 for unprimed, got {boost}"

    def test_multiple_accesses_higher_boost(self):
        pt = PrimingTracker()
        pt.record_access("s1", "n1", "python", "query1")
        pt.record_access("s1", "n1", "python", "query2")
        pt.record_access("s1", "n1", "python", "query3")
        boost = pt.get_priming_boost("s1", "n1")
        assert boost > 1.0

    def test_disabled_no_boost(self):
        cfg = PrimingConfig(enabled=False)
        pt = PrimingTracker(cfg)
        pt.record_access("s1", "n1", "python", "q")
        boost = pt.get_priming_boost("s1", "n1")
        assert boost == 1.0

    def test_get_primed_ids(self):
        pt = PrimingTracker()
        pt.record_access("s1", "n1", "a", "q")
        pt.record_access("s1", "n2", "b", "q")
        ids = pt.get_primed_neuron_ids("s1")
        assert "n1" in ids
        assert "n2" in ids

    def test_get_all_boosts(self):
        pt = PrimingTracker()
        pt.record_access("s1", "n1", "a", "q")
        boosts = pt.get_all_boosts("s1")
        assert "n1" in boosts
        assert boosts["n1"] > 1.0

    def test_reset_session(self):
        pt = PrimingTracker()
        pt.record_access("s1", "n1", "a", "q")
        pt.reset_session("s1")
        boost = pt.get_priming_boost("s1", "n1")
        assert boost == 1.0

    def test_save_load_state(self):
        pt = PrimingTracker()
        pt.record_access("s1", "n1", "python code", "deploy")
        state = pt.save_state()
        pt2 = PrimingTracker()
        pt2.load_state(state)
        assert pt2.get_priming_boost("s1", "n1") > 1.0


class TestSessionPriming:
    def test_is_stale(self):
        import time
        sp = SessionPriming(session_id="s1")
        sp.last_access = time.time() - 3600  # 1 hour ago
        assert sp.is_stale(timeout_min=30)

    def test_is_not_stale(self):
        import time
        sp = SessionPriming(session_id="s1")
        sp.last_access = time.time() - 60  # 1 min ago
        assert not sp.is_stale(timeout_min=30)
