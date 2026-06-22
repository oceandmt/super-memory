"""Tests for safety.firewall module."""
from __future__ import annotations
from super_memory.safety.firewall import check_content, sanitize_explicit_content, strip_nm_context_noise

def test_short_content_blocked():
    r = check_content("hi")
    assert r.blocked
    assert "too short" in r.reason

def test_oversized_blocked():
    r = check_content("x" * 20000)
    assert r.blocked

def test_normal_passes():
    r = check_content("This is a normal memory about deploying kubernetes")
    assert not r.blocked

def test_threat_blocked():
    r = check_content("DROP TABLE users; DROP ALL accounts in the production database immediately")
    assert r.blocked
    assert "threat" in r.reason


def test_threat_script():
    r = check_content("<script>alert(document.cookie)</script> This is a cross-site scripting attack payload")
    assert r.blocked

def test_sanitize_explicit():
    assert "Hello world" in sanitize_explicit_content("<ctrl123>Hello world</user>")

def test_sanitize_noop():
    assert sanitize_explicit_content("clean text") == "clean text"
