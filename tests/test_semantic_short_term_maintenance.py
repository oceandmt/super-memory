from super_memory import bridge


def _cfg(tmp_path):
    cfg = tmp_path / "sm.yaml"
    cfg.write_text(f"workspace_root: {tmp_path}\n", encoding="utf-8")
    return str(cfg)


def test_semantic_verify_boosts_durable_project_memories(tmp_path):
    cfg = _cfg(tmp_path)
    bridge.remember({
        "content": "OpenClaw exclusive memory slot contract uses Super Memory memory_search and memory_get adapters.",
        "type": "decision", "scope": "shared", "project": "super-memory",
        "tags": ["durable", "memory-slot"], "trust_score": 0.9,
    }, config_path=cfg)
    bridge.remember({"content": "unrelated transient lunch note", "type": "event"}, config_path=cfg)
    res = bridge.semantic_verify("OpenClaw memory slot contract", limit=3, config_path=cfg)
    assert res["ok"] is True
    best = next(r for r in res["results"] if r["type"] == "decision")
    assert best["score"] >= 0.7


def test_short_term_review_state_suppresses_repeated_candidates(tmp_path):
    cfg = _cfg(tmp_path)
    # Aligned to the canonical short_term contract (test_maintenance_semantic.py):
    # a promotion candidate is a >=4-event cluster of high-signal, long-form
    # content. A single 103-char event is deliberately noise, so the old
    # expectation (lone short event qualifying + a nonexistent
    # "reviewed_suppressed" field) tested a superseded API. We verify
    # suppression the canonical way: after marking the cluster reviewed it
    # drops out of the candidate list.
    from super_memory.config import load_config
    from super_memory.models import MemoryRecord, MemoryScope, MemoryType
    from super_memory.service import SuperMemoryService

    svc = SuperMemoryService(load_config(cfg))
    for _ in range(4):
        svc.save(MemoryRecord(
            content="triển khai semantic gateway qualify fix " + ("x" * 1200),
            type=MemoryType.EVENT, scope=MemoryScope.SESSION,
            session_id="real-session", metadata={"content_hash": "signal"},
        ))
    first = bridge.short_term_audit(config_path=cfg)
    assert first["candidates"]
    key = first["candidates"][0]["cluster_key"]
    bridge.short_term_mark_reviewed(key, "deferred", config_path=cfg)
    second = bridge.short_term_audit(config_path=cfg)
    assert all(c["cluster_key"] != key for c in second["candidates"])
    assert second["candidate_count"] == 0


def test_maintenance_run_dry_run_covers_core_steps(tmp_path):
    cfg = _cfg(tmp_path)
    bridge.remember({"content": "semantic quality audit maintenance smoke", "type": "fact", "scope": "shared", "project": "super-memory"}, config_path=cfg)
    res = bridge.maintenance_run(dry_run=True, limit=100, config_path=cfg)
    # Canonical maintenance_run contract is steps-based (see
    # test_maintenance_semantic.py::test_maintenance_dry_run_shape). The old
    # flat keys were never part of the shipped v2.0.0 API. Top-level "ok" is
    # intentionally NOT asserted: with vector features disabled/unconfigured
    # (this file's minimal _cfg), semantic_doctor legitimately reports a
    # non-ok diagnostic, which the canonical shape test also tolerates.
    assert res["dry_run"] is True
    assert "semantic_doctor" in res["steps"]
    assert "short_term_repair" in res["steps"]
    assert res["steps"]["short_term_repair"]["dry_run"] is True
