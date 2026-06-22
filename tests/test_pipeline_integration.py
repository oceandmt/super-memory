"""Tests for pipeline_integration module."""
from __future__ import annotations
from super_memory.pipeline_integration import (
    run_safety_firewall, extract_relations, detect_structure,
    check_triggers, enrich_with_relations, annotate_freshness,
)

def test_firewall_normal():
    r = run_safety_firewall("This is a normal memory about deploying kubernetes")
    assert not r["blocked"]

def test_firewall_short():
    r = run_safety_firewall("hi")
    assert r["blocked"]

def test_relations():
    rels = extract_relations("The bug was caused by a race condition")
    assert len(rels) >= 1
    assert rels[0]["relation_type"] == "causal"

def test_structure_json():
    sd = detect_structure('{"k": "v"}')
    assert sd is not None
    assert sd["format"] == "json"

def test_triggers():
    trig = check_triggers("We decided to use PostgreSQL")
    assert any(t["trigger_name"] == "decision_made" for t in trig)

def test_enrich_with_relations():
    meta = enrich_with_relations({}, "The bug was caused by a race condition")
    assert "extracted_relations" in meta

def test_annotate_freshness():
    results = annotate_freshness([{"created_at": "2026-01-01T00:00:00+00:00"}])
    assert "_freshness" in results[0]
    assert "score" in results[0]["_freshness"]
