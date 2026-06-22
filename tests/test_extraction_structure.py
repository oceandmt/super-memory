"""Tests for extraction/structure_detector module."""
from __future__ import annotations
from super_memory.extraction.structure_detector import detect_structure

def test_json():
    sd = detect_structure('{"name": "test", "version": 1}')
    assert sd.format == "json"
    assert len(sd.fields) == 2

def test_json_array():
    sd = detect_structure('[{"a": 1}, {"a": 2}]')
    assert sd.format == "json_array"

def test_key_value():
    sd = detect_structure("key1 = value1\nkey2 = value2\nkey3 = value3")
    assert sd.format == "key_value"

def test_csv():
    sd = detect_structure("name,age,city\nAlice,30,NYC\nBob,25,SF")
    assert sd.format == "csv"

def test_empty():
    assert detect_structure("") is None
    assert detect_structure("a") is None
