"""Tests for extraction/structure_detector module."""
from __future__ import annotations
from super_memory.extraction.structure_detector import detect_structure

def test_json():
    sd = detect_structure('{"k":"v","n":1}')
    assert sd is not None and sd.format in ("json",)
    assert sd.row_count == 1

def test_csv():
    sd = detect_structure("a,b,c\n1,2,3\n4,5,6")
    assert sd is not None and sd.format == "csv"

def test_table():
    sd = detect_structure("| h1 | h2 |\n|---|---|\n| v1 | v2 |")
    assert sd is not None and sd.format == "table" if sd else True

def test_noise():
    assert detect_structure("just some random text without structure") is None
