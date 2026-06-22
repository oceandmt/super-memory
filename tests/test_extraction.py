"""Tests for extraction modules."""
from __future__ import annotations
from super_memory.extraction.relations import extract_relations, RelationType
from super_memory.extraction.structure_detector import detect_structure

def test_causal_relation():
    rels = extract_relations("The bug was caused by a race condition in cache")
    types = [r.relation_type for r in rels]
    assert RelationType.CAUSAL in types

def test_sequential_relation():
    rels = extract_relations("First configure DNS, then deploy the cluster")
    types = [r.relation_type for r in rels]
    assert RelationType.SEQUENTIAL in types

def test_comparative_relation():
    rels = extract_relations("PostgreSQL is better than MySQL for analytics")
    types = [r.relation_type for r in rels]
    assert RelationType.COMPARATIVE in types

def test_empty_text():
    assert extract_relations("") == []
    assert extract_relations(None) == []

def test_short_text():
    assert len(extract_relations("hi")) == 0

def test_structure_json():
    sd = detect_structure('{"name": "test", "version": 1}')
    assert sd is not None
    assert sd.format == "json"

def test_structure_key_value():
    sd = detect_structure("key1 = value1\nkey2 = value2\nkey3 = value3")
    assert sd is not None
    assert sd.format == "key_value"

def test_structure_empty():
    assert detect_structure("") is None
    assert detect_structure("a,b") is None
