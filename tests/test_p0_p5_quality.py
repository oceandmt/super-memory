from __future__ import annotations

import os
from pathlib import Path

import pytest

from super_memory.claim_extractor import ClaimExtractor
from super_memory.config import load_config
from super_memory.db import validate_agent_scope, validate_session_scope, validate_status
from super_memory.hybrid_recall import HybridRecall
from super_memory.migrations import run_migrations
from super_memory.models import SuperMemoryConfig
from super_memory.session_archive import SessionArchive, _tfidf_score, _tokenize


@pytest.fixture()
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SuperMemoryConfig:
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    return SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/test.sqlite3")


def test_migrations_create_core_tables(cfg):
    res = run_migrations(cfg)
    assert res["ok"] is True
    arch = SessionArchive(cfg)
    with arch._conn() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"memories", "honcho_events", "graph_edges", "honcho_conclusions", "session_archives"} <= tables


def test_migrations_create_indexes(cfg):
    run_migrations(cfg)
    arch = SessionArchive(cfg)
    with arch._conn() as conn:
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_memories_agent_created" in indexes
    assert "idx_honcho_events_session_created" in indexes
    assert "idx_graph_source" in indexes


def test_validators_accept_known_values():
    assert validate_status("open") == "open"
    assert validate_agent_scope("agent:lucas") == ("agent", "lucas")
    assert validate_session_scope("session:abc") == ("session", "abc")


@pytest.mark.parametrize("value", ["bad;drop", "agent:", "x"])
def test_agent_scope_rejects_invalid(value):
    with pytest.raises(ValueError):
        validate_agent_scope(value)


@pytest.mark.parametrize("value", ["bad;drop", "session:", "x"])
def test_session_scope_rejects_invalid(value):
    with pytest.raises(ValueError):
        validate_session_scope(value)


def test_claim_extractor_filters_pronoun_subjects(cfg):
    ext = ClaimExtractor(cfg)
    claims = ext._extract("It is broken. Lucas prefers markdown memory.", "lucas", "m1")
    assert all(c["subject"].lower() != "it" for c in claims)
    assert any(c["predicate"] == "prefers" for c in claims)


def test_claim_extractor_deduplicates(cfg):
    ext = ClaimExtractor(cfg)
    text = "Lucas prefers markdown memory. Lucas prefers markdown memory."
    claims = ext._extract(text, "lucas", "m1")
    assert len(claims) == 1


def test_claim_extractor_detects_negative(cfg):
    ext = ClaimExtractor(cfg)
    claims = ext._extract("Lucas rejects unsafe SQL.", "lucas", "m1")
    assert claims and claims[0]["polarity"] == "negative"


def test_claim_extractor_decision_pattern(cfg):
    ext = ClaimExtractor(cfg)
    claims = ext._extract("Decision: use schema.sql as single source of truth.", "lucas", "m1")
    assert claims and claims[0]["subject"] == "memory"


def test_tokenize_basic():
    assert _tokenize("Hello, Boss. AI") == ["hello", "boss", "ai"]


def test_tfidf_scores_distinctive_sentence():
    corpus = ["common memory storage", "common memory graph", "unique schema migration"]
    assert _tfidf_score("unique schema migration", corpus) > 0


def seed_session(archive: SessionArchive, session_id="s1"):
    archive.ensure_tables()
    with archive._conn() as conn:
        conn.execute("INSERT INTO honcho_events(id,workspace,session_id,observer_peer_id,content,source) VALUES('e1','openclaw',?,'lucas','Decision: use schema.sql for migrations.','test')", (session_id,))
        conn.execute("INSERT INTO honcho_events(id,workspace,session_id,observer_peer_id,content,source) VALUES('e2','openclaw',?,'lucas','Implemented DBMixin and pagination.','test')", (session_id,))
        conn.execute("INSERT INTO honcho_events(id,workspace,session_id,observer_peer_id,content,source) VALUES('e3','openclaw',?,'lucas','Blocker: missing graph_edges table was fixed.','test')", (session_id,))


def test_session_summary_uses_semantic_picker(cfg):
    archive = SessionArchive(cfg)
    seed_session(archive)
    res = archive.create_session_summary("s1")
    assert res["ok"] is True
    assert "schema" in res["summary"] or "schema.sql" in res["summary"]
    assert res["event_count"] == 3


def test_list_session_summaries_pagination(cfg):
    archive = SessionArchive(cfg)
    seed_session(archive, "s1")
    archive.create_session_summary("s1")
    res = archive.list_session_summaries(limit=1, offset=0)
    assert res["count"] == 1
    assert res["limit"] == 1
    assert res["offset"] == 0


def test_search_session_archives_pagination(cfg):
    archive = SessionArchive(cfg)
    seed_session(archive, "s1")
    archive.create_session_summary("s1")
    res = archive.search_session_archives("schema", limit=1, offset=0)
    assert res["count"] == 1
    assert res["limit"] == 1


def test_hybrid_recall_truncates_to_budget(cfg):
    recall = HybridRecall(cfg)
    rows = [{"content": "x" * 1000, "id": "1"}]
    out = recall._truncate(rows, max_tokens=10)
    assert len(out[0]["content"]) <= 35


def test_hybrid_recall_rejects_bad_layer(cfg):
    recall = HybridRecall(cfg)
    with pytest.raises(ValueError):
        recall.cross_scope_recall("x", source_layers=["bad"])


def test_hybrid_recall_search_memories(cfg):
    recall = HybridRecall(cfg)
    run_migrations(cfg)
    with recall._conn() as conn:
        conn.execute("INSERT INTO memories(id,content,agent_id,session_id) VALUES('m1','Boss prefers markdown memory','lucas','s1')")
    res = recall.cross_scope_recall("markdown", agent_scope="agent:lucas", session_scope="session:s1", source_layers=["markdown"])
    assert res["count"] == 1


def test_agent_belief_report_limit_offset(cfg):
    ext = ClaimExtractor(cfg)
    ext.ensure_tables()
    with ext._conn() as conn:
        conn.execute("INSERT INTO cross_agent_claims(id,subject,predicate,object,agent_id) VALUES('c1','Lucas','prefers','markdown','lucas')")
    res = ext.agent_belief_report("lucas", limit=1, offset=0)
    assert res["count"] == 1
    assert res["limit"] == 1


def test_find_contradictions_offset_arg(cfg):
    ext = ClaimExtractor(cfg)
    ext.ensure_tables()
    res = ext.find_contradictions("memory", limit=1, offset=0)
    assert res["ok"] is True


def test_load_config_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    cfg = load_config()
    assert Path(cfg.workspace_root) == tmp_path
