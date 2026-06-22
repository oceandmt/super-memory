"""Tests for brain_mode module."""
from __future__ import annotations
from super_memory.brain_mode import BrainMode, BrainModeConfig, SyncStrategy

def test_default_mode():
    bm = BrainModeConfig()
    assert bm.mode == BrainMode.LOCAL
    assert bm.sync_strategy == SyncStrategy.MANUAL

def test_custom_mode():
    bm = BrainModeConfig(mode=BrainMode.HYBRID, max_spread_hops=6)
    assert bm.mode == BrainMode.HYBRID
    assert bm.max_spread_hops == 6

def test_sync_strategy_enum():
    assert SyncStrategy.MANUAL.value == "manual"
    assert SyncStrategy.BIDIRECTIONAL.value == "bidirectional"

def test_diminishing_returns_defaults():
    bm = BrainModeConfig()
    assert bm.diminishing_returns_enabled
    assert bm.dim_returns_threshold == 0.15
    assert bm.dim_returns_min_neurons == 2
