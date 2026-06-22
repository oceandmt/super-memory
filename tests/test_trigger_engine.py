"""Tests for trigger_engine module."""
from __future__ import annotations
from super_memory.trigger_engine import check_triggers

def test_decision_trigger():
    trig = check_triggers("We decided to use PostgreSQL for production")
    names = [t.trigger_name for t in trig]
    assert "decision_made" in names

def test_incident_trigger():
    trig = check_triggers("Critical outage in production due to memory leak")
    names = [t.trigger_name for t in trig]
    assert "critical_incident" in names

def test_empty():
    assert check_triggers("") == []
    assert check_triggers(None) == []

def test_no_match():
    assert check_triggers("normal conversation about weather") == []

def test_lesson_trigger():
    trig = check_triggers("Key takeaway: always use connection pooling")
    names = [t.trigger_name for t in trig]
    assert "lesson_learned" in names
