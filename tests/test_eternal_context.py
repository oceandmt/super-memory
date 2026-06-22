"""Tests for eternal_context module."""
from __future__ import annotations
from unittest.mock import MagicMock
from super_memory.eternal_context import EternalContext

def test_initial_counter():
    ec = EternalContext(MagicMock())
    assert ec._message_count == 0
    assert ec.increment_message_count() == 1
    assert ec._message_count == 1

def test_get_injection_quiet():
    store = MagicMock()
    store.connect().__enter__().execute().fetchall.return_value = []
    ec = EternalContext(store)
    ctx = ec.get_injection(level=1)
    assert "[Eternal Context]" in ctx
