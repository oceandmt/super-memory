"""Focused regressions for recall visibility and arbitration quality.

Every storage test uses pytest's temporary directory.  Nothing in this suite
opens the configured/live Super Memory database.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from super_memory.migrations import run_migrations
from super_memory.models import SuperMemoryConfig
from super_memory.recall.arbitration_v4 import MIN_QUERY_EVIDENCE, arbitrate_v4, score
from super_memory.recall.evidence import RecallEvidence
from super_memory.retrieval_backends import (
    ChromaBackend,
    PGVectorBackend,
    QdrantBackend,
    RetrievalContext,
    SQLiteExactBackend,
    visibility_predicate,
)


def _config(tmp_path: Path) -> SuperMemoryConfig:
    config = SuperMemoryConfig(
        workspace_root=tmp_path,
        sqlite_path="data/recall-security.sqlite3",
    )
    run_migrations(config)
    return config


def _insert_memory(
    backend: SQLiteExactBackend,
    memory_id: str,
    *,
    scope: str,
    agent_id: str = "other",
    session_id: str | None = None,
    project: str | None = None,
    metadata: dict | None = None,
) -> None:
    with backend.store.connect() as conn:
        conn.execute(
            """
            INSERT INTO memories
                (id, layer, content, type, scope, agent_id, session_id,
                 project, tags_json, source, created_at, metadata_json)
            VALUES (?, 'workspace_markdown', ?, 'context', ?, ?, ?, ?,
                    '[]', 'test.recall-security',
                    '2026-07-14T00:00:00+00:00', ?)
            """,
            (
                memory_id,
                f"visibility needle {memory_id}",
                scope,
                agent_id,
                session_id,
                project,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()


def _ids(hits) -> set[str]:
    return {hit.memory.id for hit in hits}


@pytest.fixture
def scoped_backend(tmp_path: Path) -> SQLiteExactBackend:
    backend = SQLiteExactBackend(_config(tmp_path))
    rows = (
        ("shared", "shared", "other", None, None),
        ("cross", "cross-agent", "other", None, None),
        ("project-match", "project", "other", None, "project-a"),
        ("project-other", "project", "other", None, "project-b"),
        ("local-own", "agent-local", "lucas", None, None),
        ("local-other", "agent-local", "alex", None, None),
        ("session-own", "session", "lucas", "session-a", None),
        ("session-other-session", "session", "lucas", "session-b", None),
        ("session-other-agent", "session", "alex", "session-a", None),
    )
    for memory_id, scope, agent_id, session_id, project in rows:
        _insert_memory(
            backend,
            memory_id,
            scope=scope,
            agent_id=agent_id,
            session_id=session_id,
            project=project,
        )
    return backend


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, {"shared", "cross"}),
        ({"agent_id": "lucas"}, {"shared", "cross", "local-own"}),
        (
            {"agent_id": "lucas", "session_id": "session-a"},
            {"shared", "cross", "local-own", "session-own"},
        ),
        (
            {"project": "project-a"},
            {"shared", "cross", "project-match"},
        ),
        (
            {
                "agent_id": "lucas",
                "session_id": "session-a",
                "project": "project-a",
            },
            {"shared", "cross", "project-match", "local-own", "session-own"},
        ),
        (
            {
                "agent_id": "lucas",
                "session_id": "session-a",
                "project": "project-a",
                "scope": "session",
            },
            {"session-own"},
        ),
    ],
)
def test_sqlite_visibility_scope_matrix(scoped_backend, kwargs, expected):
    assert _ids(scoped_backend.search("visibility needle", limit=50, **kwargs)) == expected


def test_visibility_predicate_supports_alias_and_bound_scope():
    sql, params = visibility_predicate(
        RetrievalContext(
            agent_id="lucas",
            session_id="session-a",
            project="project-a",
            scope="session",
        ),
        alias="m",
    )
    assert "m.metadata_json" in sql
    assert "m.agent_id" in sql
    assert "m.session_id" in sql
    assert "m.project" in sql
    assert "m.scope = ?" in sql
    assert params == ["project-a", "lucas", "lucas", "session-a", "session"]


def test_soft_deleted_false_and_zero_are_alive(tmp_path: Path):
    backend = SQLiteExactBackend(_config(tmp_path))
    variants = {
        "missing": {},
        "false": {"soft_deleted": False},
        "zero": {"soft_deleted": 0},
        "true": {"soft_deleted": True},
        "one": {"soft_deleted": 1},
        "string-false": {"soft_deleted": "false"},
    }
    for memory_id, metadata in variants.items():
        _insert_memory(
            backend,
            memory_id,
            scope="shared",
            metadata=metadata,
        )

    assert _ids(backend.search("visibility needle", limit=50)) == {
        "missing",
        "false",
        "zero",
    }


class _FakeCollection:
    def __init__(self, memory_ids: list[str]):
        self.memory_ids = memory_ids

    def query(self, *, query_texts, n_results):
        ids = self.memory_ids[:n_results]
        return {"ids": [ids], "distances": [[0.1] * len(ids)]}


def test_vector_hydration_uses_the_same_visibility_predicate(scoped_backend):
    # Construct without importing/initializing optional chromadb.
    backend = object.__new__(ChromaBackend)
    backend.collection = _FakeCollection(
        [
            "session-other-agent",
            "project-other",
            "local-other",
            "session-own",
            "project-match",
            "local-own",
            "shared",
        ]
    )
    backend.fallback = scoped_backend

    hits = backend.search(
        "visibility needle",
        limit=20,
        agent_id="lucas",
        session_id="session-a",
        project="project-a",
    )
    assert _ids(hits) == {"session-own", "project-match", "local-own", "shared"}
    assert {hit.backend for hit in hits} == {"chroma"}


@pytest.mark.parametrize("backend_type", [ChromaBackend, QdrantBackend, PGVectorBackend])
def test_all_vector_hydrators_invoke_mandatory_visibility_helper(backend_type):
    source = inspect.getsource(backend_type.search)
    assert "_visible_memory_row" in source
    assert "SELECT * FROM memories WHERE id = ?" not in source


def test_score_preserves_legacy_float_return_contract():
    evidence = RecallEvidence(
        id="canonical-score",
        memory_id="canonical-score",
        channel="vector",
        content="postgres migration",
        metadata={"upstream_score": 0.7},
    )
    result = score("postgres migration", evidence)
    assert isinstance(result, float)
    assert result == evidence.score
    assert "query_evidence=1.00" in evidence.why_selected


def test_arbitration_rejects_zero_query_evidence():
    result = arbitrate_v4(
        "postgres migration",
        {
            "workspace_markdown": [
                {
                    "id": "unrelated",
                    "content": "team lunch menu",
                    "quality_score": 1.0,
                    "trust_score": 1.0,
                    "score": 0.0,
                }
            ]
        },
    )
    assert result["answer_context"] == []
    assert result["confidence"] == 0.0
    assert result["winner_policy"] == "none"
    assert result["excluded_memories"] == [
        {
            "id": "unrelated",
            "memory_id": "unrelated",
            "channel": "workspace_markdown",
            "reason": "insufficient_query_evidence",
            "query_evidence": 0.0,
            "minimum": MIN_QUERY_EVIDENCE,
        }
    ]


def test_upstream_channel_score_is_preserved_as_query_evidence():
    result = arbitrate_v4(
        "postgres migration",
        {
            "vector": [
                {
                    "memory_id": "semantic-hit",
                    "content": "wording with no lexical match",
                    "score": 0.73,
                }
            ]
        },
    )
    selected = result["answer_context"][0]
    assert selected["id"] == "semantic-hit"
    assert selected["memory_id"] == "semantic-hit"
    assert selected["metadata"]["upstream_score"] == pytest.approx(0.73)
    assert "upstream_score=0.73" in selected["why_selected"]


def test_multi_channel_wrapper_ids_deduplicate_by_canonical_identity():
    result = arbitrate_v4(
        "postgres migration",
        {
            "vector": [
                {
                    "id": "vector-wrapper-99",
                    "memory_id": "canonical-42",
                    "content": "postgres migration decision",
                    "score": 0.91,
                    "source": "vector-index",
                }
            ],
            "graph": [
                {
                    "id": "fiber-wrapper-17",
                    "content": "postgres migration decision",
                    "score": 0.61,
                    "metadata": {"source_memory_id": "canonical-42"},
                }
            ],
        },
    )
    assert len(result["answer_context"]) == 1
    selected = result["answer_context"][0]
    assert selected["id"] == "canonical-42"
    assert selected["memory_id"] == "canonical-42"
    assert selected["channel"] == "vector"
    assert any(
        item["reason"] == "duplicate_canonical_memory" and item["memory_id"] == "canonical-42"
        for item in result["excluded_memories"]
    )


def test_content_fallback_identity_is_stable_across_calls():
    channels = {"recent_context": [{"content": "postgres migration decision"}]}
    first = arbitrate_v4("postgres migration", channels)["answer_context"][0]
    second = arbitrate_v4("postgres migration", channels)["answer_context"][0]
    assert first["id"] == second["id"]
    assert first["memory_id"] == second["memory_id"]
    assert first["id"].startswith("content:")
