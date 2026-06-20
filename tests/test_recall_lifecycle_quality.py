from pathlib import Path
import os

from super_memory import bridge
from super_memory.config import load_config
from super_memory.lifecycle import review
from super_memory.models import MemoryRecord, MemoryScope, MemoryType
from super_memory.service import SuperMemoryService


def _with_workspace(tmp_path: Path):
    old = os.environ.get("SUPER_MEMORY_WORKSPACE_ROOT")
    os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = str(tmp_path)
    return old


def _restore_workspace(old: str | None):
    if old is None:
        os.environ.pop("SUPER_MEMORY_WORKSPACE_ROOT", None)
    else:
        os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = old


def test_recall_arbitrate_falls_back_for_long_multi_term_query(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        bridge.durable_pack(qualify=True, debug=False, dedupe=True)
        result = bridge.recall_arbitrate(
            "Super Memory durable pack OpenClaw agent role baseline recall policy raw transcripts",
            limit=5,
        )
        assert result["answer_context"]
        assert result["winner_policy"] != "none"
        assert result["confidence"] > 0
        assert result["fallback_terms"]
    finally:
        _restore_workspace(old)


def test_lifecycle_review_filters_soft_deleted_duplicates(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        cfg = load_config()
        svc = SuperMemoryService(cfg)
        rec1 = MemoryRecord(
            content="duplicate lifecycle scanner should keep active only",
            type=MemoryType.FACT,
            scope=MemoryScope.SHARED,
            source="test.lifecycle",
        )
        rec2 = rec1.model_copy(deep=True)
        rec2.id = "soft-delete-copy"
        svc.save(rec1)
        svc.save(rec2)
        with svc.store.connect() as conn:
            conn.execute(
                "UPDATE memories SET metadata_json = json_set(metadata_json, '$.soft_deleted', 1) WHERE id = ?",
                (rec2.id,),
            )
            conn.commit()
        report = review(limit=100)
        duplicate_ids = {i for group in report["duplicates"] for i in group["ids"]}
        assert rec2.id not in duplicate_ids
    finally:
        _restore_workspace(old)
