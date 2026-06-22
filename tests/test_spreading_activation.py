"""Tests for spreading_activation module."""
from __future__ import annotations
from super_memory.spreading_activation import (
    should_stop_spreading, ActivationTrace, ActivationResult,
)

def test_stop_due_to_low_new_neurons():
    trace = ActivationTrace()
    trace.new_neurons_per_hop = {1: 1, 2: 10}
    stop, reason = should_stop_spreading(trace, 2, min_new_neurons=2)
    assert stop
    assert "only 1 neurons" in reason

def test_stop_due_to_gain_ratio():
    trace = ActivationTrace()
    trace.new_neurons_per_hop = {1: 100, 2: 10, 3: 0}
    stop, reason = should_stop_spreading(trace, 3, threshold=0.15, min_new_neurons=2)
    assert stop
    assert "gain ratio" in reason

def test_healthy_spread_no_stop():
    trace = ActivationTrace()
    trace.new_neurons_per_hop = {1: 5, 2: 3}
    stop, _ = should_stop_spreading(trace, 2, threshold=0.15, min_new_neurons=2)
    assert not stop

def test_grace_hops_no_stop():
    trace = ActivationTrace()
    trace.new_neurons_per_hop = {0: 1}
    stop, _ = should_stop_spreading(trace, 0, grace_hops=2, min_new_neurons=2)
    assert not stop

def test_activation_trace_defaults():
    t = ActivationTrace()
    assert t.total_neurons_activated == 0
    assert not t.stopped_early
