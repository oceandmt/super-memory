"""Tests for reflex_arc — always-on pinned neurons."""
from __future__ import annotations

import pytest
from super_memory.reflex_arc import ReflexManager, ReflexConfig, get_reflex_manager


class TestReflexManager:
    def test_pin_and_count(self):
        rm = ReflexManager()
        rm.pin("n1", "Critical rule")
        assert rm.count() == 1

    def test_unpin(self):
        rm = ReflexManager()
        rm.pin("n1", "test")
        assert rm.unpin("n1") is True
        assert rm.count() == 0

    def test_unpin_nonexistent(self):
        rm = ReflexManager()
        assert rm.unpin("nope") is False

    def test_is_reflex(self):
        rm = ReflexManager()
        rm.pin("n1", "test")
        assert rm.is_reflex("n1") is True
        assert rm.is_reflex("n2") is False

    def test_get_all_reflexes(self):
        rm = ReflexManager()
        rm.pin("n1", "Rule 1")
        rm.pin("n2", "Rule 2")
        reflexes = rm.get_all_reflexes()
        assert len(reflexes) == 2
        assert all(r["reflex"] for r in reflexes)

    def test_get_reflex_content(self):
        rm = ReflexManager()
        rm.pin("n1", "My important rule")
        assert rm.get_reflex_content("n1") == "My important rule"
        assert rm.get_reflex_content("nope") == ""

    def test_clear(self):
        rm = ReflexManager()
        rm.pin("n1", "test")
        rm.pin("n2", "test")
        rm.clear()
        assert rm.count() == 0

    def test_save_load_state(self):
        rm = ReflexManager()
        rm.pin("n1", "test content")
        state = rm.save_state()
        rm2 = ReflexManager()
        rm2.load_state(state)
        assert rm2.count() == 1
        assert rm2.is_reflex("n1")

    def test_disabled_config(self):
        cfg = ReflexConfig(enabled=False)
        rm = ReflexManager(config=cfg)
        assert rm.config.enabled is False


class TestSingleton:
    def test_get_reflex_manager(self):
        rm1 = get_reflex_manager()
        rm2 = get_reflex_manager()
        assert rm1 is rm2
