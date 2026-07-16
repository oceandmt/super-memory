from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from super_memory.canonical_contract import (
    CANONICAL_CONTRACT_VERSION,
    canonical_revision,
    content_hash,
)
from super_memory.migrations import run_migrations
from super_memory.models import SuperMemoryConfig
from super_memory.semantic import semantic_index
from super_memory.projections.manifest import (
    audit_projection_drift,
    backfill_projection_manifest,
    register_projection,
    repair_projection_drift,
)
from super_memory.vector import (
    LEGACY_VECTOR_COMPATIBILITY,
    VECTOR_AUTHORITY,
    VectorStore,
    audit_vector_authority,
    reconcile_vector_authority,
)


def _config(
    tmp_path: Path,
    *,
    dimension: int = 3,
    model: str = "contract-model-a",
) -> SuperMemoryConfig:
    return SuperMemoryConfig(
        workspace_root=tmp_path,
        sqlite_path="data/super-memory.sqlite3",
        embedding_provider="ollama",
        embedding_model=model,
        embedding_dimension=dimension,
    )


def _config_file(tmp_path: Path, cfg: SuperMemoryConfig) -> str:
    path = tmp_path / "super-memory.yaml"
    path.write_text(
        "\n".join(
            (
                f"workspace_root: {tmp_path}",
                f"sqlite_path: {cfg.sqlite_path}",
                f"embedding_provider: {cfg.embedding_provider}",
                f"embedding_model: {cfg.embedding_model}",
                f"embedding_dimension: {cfg.embedding_dimension}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return str(path)


def _insert_memory(cfg: SuperMemoryConfig, memory_id: str, content: str) -> None:
    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO memories
               (id,layer,content,type,scope,tags_json,metadata_json)
               VALUES (?,'workspace_markdown',?,'context','project','[]','{}')""",
            (memory_id, content),
        )


def _metadata_row(cfg: SuperMemoryConfig, memory_id: str) -> sqlite3.Row | None:
    path = Path(cfg.workspace_root) / "data" / "vectors.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM embedding_metadata WHERE memory_id=?", (memory_id,)
        ).fetchone()


def test_canonical_contract_is_content_derived_and_unambiguous() -> None:
    first = canonical_revision("m:1", "alpha", "workspace_markdown")
    same = canonical_revision("m:1", "alpha", "workspace_markdown")
    changed = canonical_revision("m:1", "beta", "workspace_markdown")
    other_layer = canonical_revision("m:1", "alpha", "honcho")

    assert first == same
    assert first.canonical_id != other_layer.canonical_id
    assert first.source_hash == content_hash("alpha")
    assert first.source_revision == f"sha256:{first.source_hash}"
    assert first.source_revision != changed.source_revision
    assert first.contract_version == CANONICAL_CONTRACT_VERSION


def test_projection_dry_run_is_pure_and_backfill_is_idempotent(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE memories (
                id TEXT NOT NULL,
                layer TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (id, layer)
            );
            INSERT INTO memories(id,layer,content,metadata_json)
            VALUES ('m1','workspace_markdown','alpha','{}');
            """
        )
    config_path = _config_file(tmp_path, cfg)

    audit = audit_projection_drift(config_path=config_path)
    planned = backfill_projection_manifest(config_path=config_path)
    repair = repair_projection_drift(config_path=config_path)

    assert audit["schema_missing"] is True
    assert audit["counts"]["missing"] == 1
    assert planned["dry_run"] is True
    assert planned["changed"] == 0
    assert repair["dry_run"] is True
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='projection_manifest'"
        ).fetchone() is None

    applied = backfill_projection_manifest(config_path=config_path, dry_run=False)
    repeated = backfill_projection_manifest(config_path=config_path, dry_run=False)
    assert applied["changed"] == 1
    assert repeated["changed"] == 0


def test_projection_manifest_tracks_revision_and_repairs_status(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    run_migrations(cfg)
    _insert_memory(cfg, "m1", "canonical alpha")
    config_path = _config_file(tmp_path, cfg)

    registered = register_projection(
        "m1",
        "graph",
        source_content="forged caller content",
        projection_content="node payload",
        adapter_name="graph-adapter",
        adapter_version="2",
        config_path=config_path,
    )
    expected = canonical_revision("m1", "canonical alpha")
    assert registered["source_revision"] == expected.source_revision

    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM projection_manifest WHERE projection_id=?",
            (registered["projection_id"],),
        ).fetchone()
        assert row is not None
        assert row["canonical_id"] == expected.canonical_id
        assert row["source_hash"] == expected.source_hash
        assert row["source_revision"] == expected.source_revision
        assert row["adapter_name"] == "graph-adapter"
        assert row["adapter_version"] == "2"
        assert row["status"] == "active"
        # A forged/cached hash cannot hide actual canonical content changes.
        conn.execute(
            "UPDATE memories SET content=?,content_hash=? WHERE id=? AND layer=?",
            ("canonical beta", expected.source_hash, "m1", "workspace_markdown"),
        )

    audit = audit_projection_drift(config_path=config_path)
    assert audit["counts"]["stale"] == 1
    assert audit["stale"][0]["desired_status_reason"] == "source_hash_mismatch"

    dry_run = repair_projection_drift(config_path=config_path)
    assert dry_run["changed"] == 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT status FROM projection_manifest WHERE projection_id=?",
            (registered["projection_id"],),
        ).fetchone()[0] == "active"

    applied = repair_projection_drift(config_path=config_path, dry_run=False)
    repeated = repair_projection_drift(config_path=config_path, dry_run=False)
    assert applied["changed"] == 1
    assert repeated["changed"] == 0

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM memories WHERE id='m1' AND layer='workspace_markdown'"
        )
    orphan_audit = audit_projection_drift(config_path=config_path)
    assert orphan_audit["counts"]["orphans"] == 1
    assert orphan_audit["orphans"][0]["desired_status_reason"] == "canonical_missing_or_deleted"


def test_migration_uses_manifest_contract_and_converges(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    first = run_migrations(cfg)
    second = run_migrations(cfg)
    assert first["ok"] is True
    assert second["ok"] is True
    assert second["change_count"] == 0

    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(projection_manifest)")
        }
    assert {
        "canonical_id",
        "canonical_layer",
        "source_hash",
        "source_revision",
        "adapter_name",
        "adapter_version",
        "contract_version",
        "status",
        "status_reason",
        "last_verified_at",
    } <= columns


def test_vector_metadata_is_required_and_stale_revision_is_rejected(tmp_path: Path) -> None:
    pytest.importorskip("sqlite_vec")
    cfg = _config(tmp_path)
    run_migrations(cfg)
    _insert_memory(cfg, "m1", "canonical alpha")

    store = VectorStore(cfg)
    assert store.available is True
    assert store.add_embedding("m1", [1.0, 0.0, 0.0]) is True
    assert [item[0] for item in store.search_similar([1.0, 0.0, 0.0])] == ["m1"]

    metadata = _metadata_row(cfg, "m1")
    expected = canonical_revision("m1", "canonical alpha")
    assert metadata is not None
    assert metadata["canonical_id"] == expected.canonical_id
    assert metadata["source_revision"] == expected.source_revision
    assert metadata["provider"] == "ollama"
    assert metadata["model"] == "contract-model-a"
    assert metadata["dimensions"] == 3
    assert metadata["status"] == "active"

    canonical_db = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(canonical_db) as conn:
        conn.execute(
            "UPDATE memories SET content='canonical beta' "
            "WHERE id='m1' AND layer='workspace_markdown'"
        )

    assert store.search_similar([1.0, 0.0, 0.0]) == []
    audit = audit_vector_authority(cfg)
    assert audit["counts"]["stale"] == 1
    assert audit["stale"][0]["reason"] == "source_hash_mismatch"

    dry_run = reconcile_vector_authority(cfg)
    assert dry_run["dry_run"] is True
    assert dry_run["changed"] == 0
    assert _metadata_row(cfg, "m1")["status"] == "active"

    applied = reconcile_vector_authority(cfg, dry_run=False)
    repeated = reconcile_vector_authority(cfg, dry_run=False)
    assert applied["changed"] == 1
    assert repeated["changed"] == 0
    assert _metadata_row(cfg, "m1")["status"] == "stale"

    # A verified write of the current revision is the only promotion path.
    assert store.add_embedding("m1", [0.0, 1.0, 0.0]) is True
    assert [item[0] for item in store.search_similar([0.0, 1.0, 0.0])] == ["m1"]

    different_model = _config(tmp_path, model="contract-model-b")
    assert VectorStore(different_model).search_similar([0.0, 1.0, 0.0]) == []
    model_audit = audit_vector_authority(different_model)
    assert model_audit["stale"][0]["reason"] == "model_mismatch"
    assert store.search_similar([1.0, 0.0]) == []


def test_semantic_index_writes_verified_authority_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("sqlite_vec")
    cfg = _config(tmp_path)
    run_migrations(cfg)
    _insert_memory(cfg, "semantic-1", "canonical alpha")
    config_path = _config_file(tmp_path, cfg)

    monkeypatch.setattr(
        "super_memory.semantic._ollama_embed_batch",
        lambda texts, _cfg: [[1.0, 0.0, 0.0] for _ in texts],
    )
    first = semantic_index(config_path=config_path)

    assert first["ok"] is True
    assert first["indexed"] == 1
    metadata = _metadata_row(cfg, "semantic-1")
    assert metadata is not None
    assert metadata["status"] == "active"
    assert metadata["source_revision"] == canonical_revision(
        "semantic-1", "canonical alpha"
    ).source_revision
    assert VectorStore(cfg).search_similar([1.0, 0.0, 0.0]) == [
        ("semantic-1", pytest.approx(1.0))
    ]

    canonical_db = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(canonical_db) as conn:
        conn.execute(
            "UPDATE memories SET content='canonical beta' "
            "WHERE id='semantic-1' AND layer='workspace_markdown'"
        )
    monkeypatch.setattr(
        "super_memory.semantic._ollama_embed_batch",
        lambda texts, _cfg: [[0.0, 1.0, 0.0] for _ in texts],
    )
    rebuilt = semantic_index(config_path=config_path, rebuild=True)

    assert rebuilt["ok"] is True
    refreshed = _metadata_row(cfg, "semantic-1")
    assert refreshed is not None
    assert refreshed["status"] == "active"
    assert refreshed["source_revision"] == canonical_revision(
        "semantic-1", "canonical beta"
    ).source_revision
    assert [item[0] for item in VectorStore(cfg).search_similar([0.0, 1.0, 0.0])] == [
        "semantic-1"
    ]


def test_legacy_vector_and_memory_vectors_cache_are_non_authoritative(tmp_path: Path) -> None:
    sqlite_vec = pytest.importorskip("sqlite_vec")
    cfg = _config(tmp_path)
    run_migrations(cfg)
    _insert_memory(cfg, "legacy", "canonical legacy")

    canonical_db = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(canonical_db) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO memory_vectors
               (memory_id,layer,vector,provider,dimensions)
               VALUES (?,?,?,?,?)""",
            ("legacy", "workspace_markdown", json.dumps([1.0, 0.0, 0.0]), "legacy", 3),
        )

    vector_db = Path(cfg.workspace_root) / "data" / "vectors.sqlite3"
    with sqlite3.connect(vector_db) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.execute(
            "CREATE VIRTUAL TABLE embeddings USING vec0("
            "memory_id TEXT PRIMARY KEY, embedding FLOAT[3])"
        )
        conn.execute(
            "INSERT INTO embeddings(memory_id,embedding) VALUES (?,?)",
            ("legacy", json.dumps([1.0, 0.0, 0.0])),
        )

    audit = audit_vector_authority(cfg)
    assert audit["authority"] == VECTOR_AUTHORITY
    assert audit["compatibility"] == LEGACY_VECTOR_COMPATIBILITY
    assert audit["counts"]["legacy_unverified"] == 1
    assert audit["legacy_unverified"][0]["reason"] == "unverified_legacy_vector"
    assert audit["legacy_memory_vectors"] == {
        "present": True,
        "rows": 1,
        "authoritative": False,
    }
    with sqlite3.connect(vector_db) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='embedding_metadata'"
        ).fetchone() is None
        assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1

    # Runtime initialization adds only the sidecar schema; it does not bless or
    # delete a legacy payload, so recall still fails closed.
    store = VectorStore(cfg)
    assert store.search_similar([1.0, 0.0, 0.0]) == []
    with sqlite3.connect(vector_db) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM embedding_metadata").fetchone()[0] == 0
