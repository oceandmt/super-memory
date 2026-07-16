from pathlib import Path

from super_memory import bridge
from super_memory.config import load_config
from super_memory.layer_parity import audit_layer_parity, repair_layer_parity
from super_memory.models import MemoryLayer
from super_memory.storage import SuperMemoryStore


def _cfg(tmp_path: Path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n")
    return str(cfg)


def test_layer_parity_audit_and_repair_backfills_missing_projection(tmp_path: Path):
    cp = _cfg(tmp_path)
    saved = bridge.remember({"content": "Layer parity test memory", "type": "fact", "scope": "project", "project": "super-memory"}, config_path=cp)
    memory_id = saved["record"]["id"]
    cfg = load_config(cp)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        conn.execute("DELETE FROM memories WHERE id=? AND layer=?", (memory_id, MemoryLayer.HONCHO.value))
        conn.commit()

    audit = audit_layer_parity(config_path=cp, limit=10)
    assert audit["has_drift"] is True
    assert any(item["memory_id"] == memory_id for item in audit["missing_by_layer"]["honcho"])

    dry = repair_layer_parity(config_path=cp, limit=10, dry_run=True)
    assert dry["changed"] == 0
    assert any(item["memory_id"] == memory_id and item["layer"] == "honcho" for item in dry["repair_plan"])

    applied = repair_layer_parity(config_path=cp, limit=10, dry_run=False)
    assert applied["ok"] is True
    assert applied["changed"] >= 1
    assert applied["post_audit"]["has_drift"] is False
