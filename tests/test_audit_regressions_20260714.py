"""Regression tests for the 2026-07-14 deep-debug audit fixes.

Covers 6 verified, live-path bugs:
1. bridge.forget() soft-delete SQL-injection escaping
2. spreading_activation._fetch_neighbors .get()-on-sqlite3.Row crash
3. pipeline_integration run_spreading_activation config->cfg NameError
4. embeddings_registry SQLiteVecAdapter false-availability (lexical hash)
5. vector._cosine_similarity dimension-mismatch fabrication
6. vector.embed_text char-split + averaging corruption
"""
from __future__ import annotations

import sqlite3

import pytest


# ── #2: spreading_activation _fetch_neighbors survives sqlite3.Row ──────────

def _build_graph_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row  # this is what broke .get() in production
    conn.executescript(
        """
        CREATE TABLE cognitive_neurons (id TEXT PRIMARY KEY, content TEXT, kind TEXT, source_memory_id TEXT);
        CREATE TABLE cognitive_synapses (
            source_neuron_id TEXT, target_neuron_id TEXT, synapse_type TEXT, weight REAL
        );
        INSERT INTO cognitive_neurons VALUES ('n1', 'anchor', 'memory', 'm1');
        INSERT INTO cognitive_neurons VALUES ('n2', 'neighbor', 'memory', 'm2');
        INSERT INTO cognitive_synapses VALUES ('n1', 'n2', 'structural', 0.9);
        """
    )
    conn.commit()
    return conn


def test_fetch_neighbors_does_not_crash_on_row_factory():
    from super_memory.spreading_activation import SpreadingActivation

    conn = _build_graph_db()
    sa = SpreadingActivation(conn, config=None)
    neighbors = sa._fetch_neighbors("n1")
    # Before the fix this returned [] (AttributeError swallowed by bare except).
    assert neighbors, "spreading activation collapsed to anchor-only (Row.get crash)"
    ids = {n["id"] for n, _ in neighbors}
    assert "n2" in ids


# ── #3: run_spreading_activation no longer NameErrors on 'config' ───────────

def test_run_spreading_activation_uses_cfg_not_config():
    import inspect

    from super_memory import pipeline_integration as pi

    src = inspect.getsource(pi.run_spreading_activation)
    assert "SpreadingActivation(conn, config)" not in src, "NameError bug still present"
    assert "SpreadingActivation(conn, cfg)" in src


# ── #4: SQLiteVecAdapter must not claim availability without text embedding ──

def test_sqlitevec_adapter_availability_requires_text_embedding():
    from super_memory.embeddings_registry import SQLiteVecAdapter

    adapter = SQLiteVecAdapter()
    try:
        from sqlite_vec.experimental import vector_from_text  # noqa: F401
        has_text_embed = True
    except Exception:
        has_text_embed = False
    # is_available() must track real text-embedding capability, not just import.
    assert adapter.is_available() == has_text_embed


def test_sqlitevec_default_dim_matches_768():
    import inspect

    from super_memory.embeddings_registry import SQLiteVecAdapter

    src = inspect.getsource(SQLiteVecAdapter.embed)
    assert "dim = dimensions or 384" not in src, "stale 384 default (mismatch vs vector.py 768)"
    assert "dim = dimensions or 768" in src


# ── #5: cosine similarity refuses mismatched dimensions ─────────────────────

def test_cosine_similarity_refuses_dimension_mismatch():
    from super_memory.vector import _cosine_similarity

    # Different lengths must NOT be zero-padded into a fabricated score.
    assert _cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0
    # Same-length identical vectors still score ~1.0.
    assert _cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


# ── #6: embed_text no longer char-splits + averages ────────────────────────

def test_embed_text_does_not_char_split_and_average():
    import inspect

    from super_memory import vector

    src = inspect.getsource(vector.embed_text)
    assert "input_text[i:i+2000]" not in src, "char-based chunk split still present"
    assert "Average the chunk embeddings" not in src


# ── #1: forget() soft-delete escapes the memory_id ─────────────────────────

def test_forget_soft_delete_escapes_memory_id():
    import inspect

    from super_memory import bridge

    src = inspect.getsource(bridge.forget)
    # The soft-delete branch must escape memory_id before interpolation.
    assert "WHERE id = '{memory_id}'" not in src, "raw memory_id interpolation (SQL-injection) still present"
    assert 'esc_id = memory_id.replace("\'", "\'\'")' in src
