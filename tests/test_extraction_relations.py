"""Tests for extraction/relations module."""
from __future__ import annotations
from super_memory.extraction.relations import extract_relations, RelationType

def test_causal():
    r = extract_relations("Bug caused by race condition in cache layer that leads to data loss")
    types = [x.relation_type for x in r]
    assert RelationType.CAUSAL in types

def test_comparative():
    r = extract_relations("PostgreSQL is better than MySQL for analytics workloads")
    types = [x.relation_type for x in r]
    assert RelationType.COMPARATIVE in types

def test_sequential():
    r = extract_relations("First configure DNS then deploy the cluster")
    types = [x.relation_type for x in r]
    assert RelationType.SEQUENTIAL in types

def test_empty():
    assert extract_relations("") == []
    assert extract_relations(None) == []

def test_caps_20():
    r = extract_relations("A caused B. " * 30)
    assert len(r) <= 20
