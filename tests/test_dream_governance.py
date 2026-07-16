"""Focused contract tests for governed dream/self-improvement generation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path

from super_memory.dream_governance import (
    MAX_CONTENT_CHARS,
    MAX_SOURCE_IDS,
    build_proposal,
    deterministic_run_key,
    enqueue_proposal,
    get_proposal,
    is_generated_record,
    list_proposals,
    resolve_proposal,
)
from super_memory.models import SuperMemoryConfig
from super_memory.storage import SuperMemoryStore


def _store(tmp_path: Path) -> SuperMemoryStore:
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/test.sqlite3")
    return SuperMemoryStore(cfg)


def _init_memories(store: SuperMemoryStore) -> None:
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT NOT NULL,
                layer TEXT NOT NULL DEFAULT 'mempalace',
                content TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'context',
                scope TEXT NOT NULL DEFAULT 'session',
                agent_id TEXT,
                session_id TEXT,
                project TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                source TEXT,
                trust_score REAL,
                leiter_box INTEGER NOT NULL DEFAULT 0,
                next_review TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                content_hash TEXT,
                PRIMARY KEY (id, layer)
            )
            """
        )


def _insert_memory(
    store: SuperMemoryStore,
    *,
    memory_id: str,
    content: str,
    agent_id: str = "lucas",
    source: str = "human",
    metadata: dict | None = None,
    session_id: str = "s1",
    memory_type: str = "context",
) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO memories "
            "(id, layer, content, type, scope, agent_id, session_id, source, created_at, metadata_json, content_hash) "
            "VALUES (?, 'mempalace', ?, ?, 'session', ?, ?, ?, datetime('now'), ?, ?)",
            (
                memory_id,
                content,
                memory_type,
                agent_id,
                session_id,
                source,
                json.dumps(metadata or {}),
                hashlib.sha256(content.encode()).hexdigest(),
            ),
        )


def test_deterministic_identity_provenance_and_bounds() -> None:
    inputs_a = {"threshold": 0.4, "options": ["x", "y"]}
    inputs_b = {"options": ["x", "y"], "threshold": 0.4}
    key_a = deterministic_run_key("dream", inputs=inputs_a, source_ids=["b", "a", "a"])
    key_b = deterministic_run_key("dream", inputs=inputs_b, source_ids=["a", "b"])
    assert key_a == key_b

    proposal_a = build_proposal(
        kind="dream_insight",
        content="  repeated   insight  " + "z" * 10_000,
        source_ids=[f"source-{index}" for index in reversed(range(100))],
        evidence={f"key-{index}": "v" * 3_000 for index in range(100)},
        action={"type": "create_memory"},
        run_key=key_a,
    )
    proposal_b = build_proposal(
        kind="dream_insight",
        content="repeated insight " + "z" * 10_000,
        source_ids=[f"source-{index}" for index in range(100)],
        evidence={},
        action={"type": "create_memory"},
        run_key=key_a,
    )
    assert proposal_a["id"] == proposal_b["id"]
    assert proposal_a["run_key"] == key_a
    assert proposal_a["status"] == "pending"
    assert len(proposal_a["content"]) <= MAX_CONTENT_CHARS
    assert len(proposal_a["source_ids"]) == MAX_SOURCE_IDS
    assert proposal_a["source_ids"] == sorted(proposal_a["source_ids"])
    assert len(proposal_a["evidence"]) <= 64
    assert max(map(len, proposal_a["evidence"].values())) <= 2_000


def test_dry_run_is_no_write_even_when_database_is_absent(tmp_path: Path, monkeypatch) -> None:
    import super_memory.dream as legacy_dream
    import super_memory.self_improvement.orchestrator as orchestrator

    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/absent.sqlite3")
    db_path = tmp_path / "data" / "absent.sqlite3"
    monkeypatch.setattr(legacy_dream, "load_config", lambda config_path=None: cfg)
    monkeypatch.setattr(orchestrator, "load_config", lambda config_path=None: cfg)

    dream_report = legacy_dream.dream_full_cycle(limit=10, dry_run=True)
    improve_report = orchestrator.run_self_improvement_cycle(
        dry_run=True,
        release_evidence={
            "gate": "recall-release",
            "ok": False,
            "benchmark": {
                "results": [{"name": "case-a", "ok": False, "query": "alpha"}],
            },
        },
    )

    assert dream_report["dry_run"] is True
    assert improve_report["proposal_count"] == 1
    assert improve_report["proposals"][0]["would_enqueue"] is True
    assert improve_report["report_written"] is False
    assert not db_path.exists()
    assert not (tmp_path / "data").exists()
    assert list(tmp_path.rglob("*")) == []


def test_enqueue_deduplicates_before_write_and_keeps_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    proposal = build_proposal(
        kind="dream_insight",
        content="A governed insight",
        source_ids=["memory-b", "memory-a"],
        evidence={"cluster_size": 2},
        action={"type": "create_memory"},
    )
    first = enqueue_proposal(store, proposal, dry_run=False)
    second = enqueue_proposal(store, proposal, dry_run=False)

    assert first["created"] is True
    assert second["created"] is False
    assert second["deduplicated"] is True
    assert first["proposal"]["status"] == "pending"
    assert first["proposal"]["source_ids"] == ["memory-a", "memory-b"]
    assert len(list_proposals(store, kind="dream_insight")) == 1


def test_explicit_approval_and_rejection_are_terminal_and_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    approved = build_proposal(kind="dream_insight", content="approve me", source_ids=["m1"])
    rejected = build_proposal(kind="self_improvement_fix", content="reject me", source_ids=["release:1"])
    enqueue_proposal(store, approved, dry_run=False)
    enqueue_proposal(store, rejected, dry_run=False)

    applications: list[str] = []

    def apply_once(proposal: dict) -> str:
        applications.append(proposal["id"])
        return "canonical-1"

    first = resolve_proposal(store, approved["id"], decision="approved", apply=apply_once)
    replay = resolve_proposal(store, approved["id"], decision="approved", apply=apply_once)
    conflict = resolve_proposal(store, approved["id"], decision="rejected")
    rejected_first = resolve_proposal(store, rejected["id"], decision="rejected", note="unsafe")
    rejected_replay = resolve_proposal(store, rejected["id"], decision="rejected")

    assert first == {
        "ok": True,
        "id": approved["id"],
        "status": "approved",
        "canonical_memory_id": "canonical-1",
        "idempotent": False,
    }
    assert replay["ok"] is True and replay["idempotent"] is True and replay["no_op"] is True
    assert applications == [approved["id"]]
    assert conflict["ok"] is False and conflict["error"] == "conflicting_terminal_state"
    assert rejected_first["ok"] is True
    assert rejected_replay["ok"] is True and rejected_replay["idempotent"] is True
    assert get_proposal(store, rejected["id"])["resolution_note"] == "unsafe"


def test_self_improvement_consumes_release_evidence_and_only_proposes(tmp_path: Path, monkeypatch) -> None:
    import super_memory.self_improvement.orchestrator as orchestrator

    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/sm.sqlite3")
    monkeypatch.setattr(orchestrator, "load_config", lambda config_path=None: cfg)
    evidence = {
        "gate": "recall-release",
        "ok": False,
        "benchmark": {
            "total": 2,
            "passed": 1,
            "failed": 1,
            "results": [
                {"name": "failed-case", "ok": False, "query": "where is alpha?", "expected_contains": ["alpha"]},
                {"name": "passed-case", "ok": True},
            ],
        },
    }

    first = orchestrator.run_self_improvement_cycle(dry_run=False, release_evidence=evidence)
    second = orchestrator.run_self_improvement_cycle(dry_run=False, release_evidence=evidence)

    assert first["run_key"] == second["run_key"]
    assert first["proposals_queued"] == 1
    assert second["proposals_queued"] == 0
    assert second["deduplicated"] == 1
    proposal = first["proposals"][0]
    assert proposal["status"] == "pending"
    assert proposal["source_ids"] == ["release-case:failed-case"]
    assert proposal["action"]["auto_apply"] is False
    assert first["governance"]["canonical_memory_writes"] == 0
    with store_connection(cfg) as conn:
        assert conn.execute("SELECT COUNT(*) FROM generated_proposals").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='memories'").fetchone()[0] == 0


def store_connection(cfg: SuperMemoryConfig):
    """Return a context-manageable store connection for compact assertions."""
    return SuperMemoryStore(cfg).connect()


def test_self_improvement_filters_generated_inputs_and_bounds_output(tmp_path: Path, monkeypatch) -> None:
    import super_memory.self_improve as self_improve

    store = _store(tmp_path)
    _init_memories(store)
    _insert_memory(
        store,
        memory_id="human-lesson",
        content="We fixed the release blocker by validating the schema first.",
        source="operator",
    )
    _insert_memory(
        store,
        memory_id="generated-agent",
        content="We fixed a generated blocker and should amplify it.",
        agent_id="dream-engine",
        source="operator",
    )
    _insert_memory(
        store,
        memory_id="generated-source",
        content="We fixed another generated blocker.",
        source="super-memory.dream.approved",
    )
    _insert_memory(
        store,
        memory_id="generated-metadata",
        content="We learned a recursive machine lesson.",
        metadata={"generated_by": "dream_engine"},
    )
    cfg = store.config
    monkeypatch.setattr(self_improve, "load_config", lambda config_path=None: cfg)

    preview = self_improve.run_self_improve_cycle(dry_run=True, limit=10)
    live = self_improve.run_self_improve_cycle(dry_run=False, limit=10)

    assert preview["lessons_detected"] == 1
    assert live["lessons_detected"] == 1
    assert live["source_memories_consumed"] == 1
    assert live["proposals_queued"] == 1
    assert live["captured_count"] == 0
    proposal = live["proposals"][0]
    assert proposal["source_ids"] == ["human-lesson"]
    assert proposal["status"] == "pending"
    assert len(proposal["content"]) <= MAX_CONTENT_CHARS
    assert is_generated_record(agent_id="dream-engine", source=None, metadata={})
    assert is_generated_record(agent_id=None, source="self-improvement.generated", metadata={})
    assert is_generated_record(agent_id=None, source=None, metadata={"governance_proposal_id": "p"})
    assert not is_generated_record(agent_id="lucas", source="operator", metadata={})

def test_concurrent_approval_runs_one_executor(tmp_path: Path) -> None:
    store = _store(tmp_path)
    proposal = build_proposal(kind="dream_insight", content="concurrent", source_ids=["m1"])
    enqueue_proposal(store, proposal, dry_run=False)

    entered = threading.Event()
    release = threading.Event()
    applications: list[str] = []
    results: list[dict] = []

    def slow_apply(item: dict) -> str:
        applications.append(item["id"])
        entered.set()
        assert release.wait(timeout=5)
        return "canonical-concurrent"

    worker = threading.Thread(
        target=lambda: results.append(
            resolve_proposal(store, proposal["id"], decision="approved", apply=slow_apply)
        )
    )
    worker.start()
    assert entered.wait(timeout=5)
    loser = resolve_proposal(
        store, proposal["id"], decision="approved", apply=lambda _item: "must-not-run"
    )
    release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert loser["ok"] is False
    assert loser["error"] == "application_in_flight"
    assert applications == [proposal["id"]]
    assert results[0]["ok"] is True
    assert get_proposal(store, proposal["id"])["status"] == "approved"


def test_expired_application_lease_is_recoverable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    proposal = build_proposal(kind="dream_insight", content="recover", source_ids=["m1"])
    enqueue_proposal(store, proposal, dry_run=False)
    with store.connect() as conn:
        conn.execute(
            "UPDATE generated_proposals SET status='applying', application_token='dead', "
            "application_lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
            (proposal["id"],),
        )

    calls: list[str] = []
    result = resolve_proposal(
        store,
        proposal["id"],
        decision="approved",
        apply=lambda item: calls.append(item["id"]) or "canonical-recovered",
    )

    assert result["ok"] is True
    assert result["canonical_memory_id"] == "canonical-recovered"
    assert calls == [proposal["id"]]
    stored = get_proposal(store, proposal["id"])
    assert stored["status"] == "approved"
    assert stored["application_attempts"] == 1
    assert stored["application_token"] is None


def test_failed_application_releases_owned_claim_for_retry(tmp_path: Path) -> None:
    store = _store(tmp_path)
    proposal = build_proposal(kind="dream_insight", content="retry", source_ids=["m1"])
    enqueue_proposal(store, proposal, dry_run=False)

    failed = resolve_proposal(
        store,
        proposal["id"],
        decision="approved",
        apply=lambda _item: (_ for _ in ()).throw(RuntimeError("temporary")),
    )
    replay = resolve_proposal(
        store, proposal["id"], decision="approved", apply=lambda _item: "canonical-retry"
    )

    assert failed["ok"] is False and failed["status"] == "pending"
    assert replay["ok"] is True
    stored = get_proposal(store, proposal["id"])
    assert stored["status"] == "approved"
    assert stored["application_attempts"] == 2
    assert stored["application_error"] is None
