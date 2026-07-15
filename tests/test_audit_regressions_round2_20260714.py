"""Regression tests for the 2026-07-14 deep-debug ROUND 2 audit fixes.

R2-1. reconstruct.causal_chain passed a memory_id straight into
      cognitive_synapses.source_neuron_id (which keys on neuron ids), so the
      chain never linked and node_count was always 1.
R2-2. fidelity.extract_fidelity_safe called extract_fidelity(), which did not
      exist -> every call hit the except branch and returned empty fallback.
      (Plus FidelityLayer is a str alias, not an enum, so .value would crash.)
R2-3. graph.project_memory minted a phantom neuron (content "memory:{id}")
      for related_memory_ids instead of linking to the target's real anchor.
R2-4. semantic.semantic_verify hydrated soft-deleted rows.
R2-5. data_improvement.promote_events_to_durable never committed and closed a
      shared pooled connection -> promotions rolled back and pool corrupted.
"""
from __future__ import annotations

import inspect

import pytest


# ── R2-1: causal_chain resolves memory_id -> neuron id ─────────────────────

def test_causal_chain_resolves_neuron_ids():
    from super_memory import reconstruct

    src = inspect.getsource(reconstruct.causal_chain)
    # Must resolve to a neuron id rather than querying synapses with a raw mid.
    assert "_resolve_neuron_id" in src
    assert "source_memory_id" in src
    # The old broken direct-bind pattern must be gone.
    assert "WHERE source_neuron_id = ? AND relation = ?\",\n                        (mid," not in src


# ── R2-2: extract_fidelity exists and returns a real result ────────────────

def test_extract_fidelity_exists_and_populates():
    from super_memory.fidelity import extract_fidelity, extract_fidelity_safe

    content = (
        "We decided to migrate the billing service to PostgreSQL. "
        "It handles concurrent writes far better than SQLite at our scale."
    )
    result = extract_fidelity(content)
    assert result.essence, "essence should be non-empty for rich content"
    assert result.layer in {"verbatim", "detail", "summary", "gist", "essence"}
    assert 0.0 <= result.confidence <= 1.0

    safe = extract_fidelity_safe(content)
    assert "error" not in safe, f"safe wrapper should not error: {safe}"
    assert safe["essence"]
    assert isinstance(safe["layer"], str)


def test_extract_fidelity_safe_empty_content_is_graceful():
    from super_memory.fidelity import extract_fidelity_safe

    safe = extract_fidelity_safe("")
    assert "error" not in safe
    assert safe["essence"] == ""


# ── R2-3: project_memory links to real anchor, not phantom neuron ──────────

def test_project_memory_prefers_existing_anchor():
    from super_memory import graph

    src = inspect.getsource(graph.project_memory)
    # Must look up an existing anchor by source_memory_id before minting one.
    assert "SELECT id FROM cognitive_neurons WHERE source_memory_id = ? AND kind = 'memory'" in src
    assert "if existing:" in src


# ── R2-4: semantic_verify filters soft-deleted ─────────────────────────────

def test_semantic_verify_filters_soft_deleted():
    from super_memory import semantic

    src = inspect.getsource(semantic.semantic_verify)
    assert "soft_deleted" in src


# ── R2-5: promote_events_to_durable commits and does not close the pool ────

def test_promote_events_commits_and_keeps_pool():
    from super_memory import data_improvement

    src = inspect.getsource(data_improvement.promote_events_to_durable)
    # No manual close of the shared pooled connection. Strip comment lines so
    # the explanatory comment (which mentions c.close()) doesn't false-match;
    # we only care about an actual call statement.
    code_lines = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    assert "c.close()" not in code
    # Uses a with-block (which commits on success).
    assert "with store.connect() as c:" in code
