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
    content = "Heavy debug session repeatedly generated duplicate auto capture compression candidate for semantic audit."
    bridge.remember({"content": content, "type": "event", "scope": "session"}, config_path=cfg)
    bridge.remember({"content": content, "type": "event", "scope": "session"}, config_path=cfg)
    first = bridge.short_term_audit(config_path=cfg)
    assert first["candidates"]
    key = first["candidates"][0]["cluster_key"]
    bridge.short_term_mark_reviewed(key, "deferred", config_path=cfg)
    second = bridge.short_term_audit(config_path=cfg)
    assert all(c["cluster_key"] != key for c in second["candidates"])
    assert second["reviewed_suppressed"] >= 1


def test_maintenance_run_dry_run_covers_core_steps(tmp_path):
    cfg = _cfg(tmp_path)
    bridge.remember({"content": "semantic quality audit maintenance smoke", "type": "fact", "scope": "shared", "project": "super-memory"}, config_path=cfg)
    res = bridge.maintenance_run(dry_run=True, limit=100, config_path=cfg)
    assert res["ok"] is True
    assert res["semantic_index"]["ok"] is True
    assert res["short_term"]["dry_run"] is True
    assert res["semantic_quality"]["probes"] >= 1
