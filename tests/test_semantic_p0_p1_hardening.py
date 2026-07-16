from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from super_memory import bridge
from super_memory.config import load_config
from super_memory.models import SuperMemoryConfig
from super_memory.storage import SuperMemoryStore
from super_memory.migrations import run_migrations

ROOT = Path(__file__).resolve().parents[1]
RELEASE_HELPER = ROOT / "scripts" / "super_memory_release_gate.py"


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    run_migrations(SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/test.sqlite3"))
    return cfg


def test_agent_local_recall_and_show_require_matching_access_context(tmp_path: Path):
    cfg = _config(tmp_path)
    rec = bridge.remember({
        "content": "Fact: private alpha retrieval secret",
        "type": "fact",
        "scope": "agent-local",
        "agent_id": "agent-a",
        "tags": ["private-alpha"],
    }, config_path=str(cfg))["record"]

    hidden = bridge.recall("private alpha retrieval secret", limit=5, config_path=str(cfg))
    assert hidden["status"] in {"no_hit", "degraded"}
    assert rec["id"] not in json.dumps(hidden)
    assert bridge.show(rec["id"], config_path=str(cfg))["ok"] is False

    visible = bridge.recall("private alpha retrieval secret", limit=5, config_path=str(cfg), agent_id="agent-a")
    assert visible["status"] in {"ok", "degraded"}
    assert rec["id"] in json.dumps(visible)
    assert bridge.show(rec["id"], config_path=str(cfg), agent_id="agent-a")["ok"] is True


def test_recall_status_distinguishes_no_hit_and_disabled_vector(tmp_path: Path):
    cfg = _config(tmp_path)
    result = bridge.recall("query with no matching memory at all", limit=3, config_path=str(cfg))
    assert result["status"] in {"no_hit", "degraded"}
    assert "vector" in result["channel_status"]
    assert result["channel_status"]["vector"]["status"] == "disabled"
    assert result["channel_status"]["workspace_markdown"]["status"] == "no_hit"


def test_caller_id_is_external_and_does_not_overwrite_canonical(tmp_path: Path):
    cfg = _config(tmp_path)
    first = bridge.remember({"id": "client-id-1", "content": "Fact: first canonical content", "type": "fact", "scope": "shared"}, config_path=str(cfg))["record"]
    second = bridge.remember({"id": "client-id-1", "content": "Fact: second canonical content", "type": "fact", "scope": "shared"}, config_path=str(cfg))["record"]
    assert first["id"] != "client-id-1"
    assert second["id"] != "client-id-1"
    assert first["id"] != second["id"]
    assert first["metadata"]["external_id"] == "client-id-1"
    assert second["metadata"]["external_id"] == "client-id-1"


def test_get_memory_defaults_to_active_canonical_rows(tmp_path: Path):
    cfg = _config(tmp_path)
    rec = bridge.remember({"content": "Fact: tombstone should be hidden", "type": "fact", "scope": "shared"}, config_path=str(cfg))["record"]
    store = SuperMemoryStore(load_config(str(cfg)))
    with store.connect() as conn:
        conn.execute("UPDATE memories SET metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.soft_deleted',1) WHERE id=?", (rec["id"],))
        conn.commit()
    assert store.get_memory(rec["id"]) is None
    assert store.get_memory(rec["id"], include_deleted=True) is not None


def test_evidence_requires_provenance_and_is_idempotent(tmp_path: Path):
    cfg = _config(tmp_path)
    hyp = bridge.hypothesis_create("Evidence provenance must be real", config_path=str(cfg))
    from super_memory import reasoning
    rejected = reasoning.evidence_add(hyp["hypothesis_id"], "unsupported evidence", config_path=str(cfg))
    assert rejected["ok"] is False
    ev1 = bridge.evidence_add(hyp["hypothesis_id"], "supported evidence", config_path=str(cfg), source_id="doc:1", source_type="test", source_hash="abc", source_revision="r1", source_trust=0.8)
    ev2 = bridge.evidence_add(hyp["hypothesis_id"], "supported evidence", config_path=str(cfg), source_id="doc:1", source_type="test", source_hash="abc", source_revision="r1", source_trust=0.8)
    assert ev1["ok"] is True and ev1["canonical_promoted"] is False
    assert ev2["deduplicated"] is True
    assert ev2["confidence"] == ev1["confidence"]


def test_hypothesis_does_not_auto_promote_canonical_memory(tmp_path: Path):
    cfg = _config(tmp_path)
    hyp = bridge.hypothesis_create("Speculative content stays hypothesis", config_path=str(cfg))
    assert hyp["canonical_promoted"] is False
    recalled = bridge.recall("Speculative content stays hypothesis", config_path=str(cfg))
    assert not recalled.get("selected")


def test_rollback_manifest_source_and_backup_root_are_trusted(tmp_path: Path):
    cfg = _config(tmp_path)
    backup = tmp_path / "backups" / "release.sqlite3"
    manifest = tmp_path / "backups" / "rollback.json"
    created = subprocess.run([sys.executable, str(RELEASE_HELPER), "backup", "--config", str(cfg), "--output", str(backup), "--manifest", str(manifest), "--rollback-command", "guarded"], cwd=ROOT, text=True, capture_output=True)
    assert created.returncode == 0, created.stdout + created.stderr

    payload = json.loads(manifest.read_text())
    payload["database"]["source"] = str(tmp_path / "other.sqlite3")
    tampered = tmp_path / "backups" / "tampered-source.json"
    tampered.write_text(json.dumps(payload))
    checked = subprocess.run([sys.executable, str(RELEASE_HELPER), "verify-backup", "--config", str(cfg), "--manifest", str(tampered)], cwd=ROOT, text=True, capture_output=True)
    assert checked.returncode != 0
    assert json.loads(checked.stdout)["error"] == "manifest_source_mismatch"

    payload = json.loads(manifest.read_text())
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(backup.read_bytes())
    payload["database"]["backup"] = str(outside)
    tampered2 = tmp_path / "backups" / "tampered-backup.json"
    tampered2.write_text(json.dumps(payload))
    checked2 = subprocess.run([sys.executable, str(RELEASE_HELPER), "verify-backup", "--manifest", str(tampered2)], cwd=ROOT, text=True, capture_output=True)
    assert checked2.returncode != 0
    assert json.loads(checked2.stdout)["error"] == "backup_outside_manifest_root"
