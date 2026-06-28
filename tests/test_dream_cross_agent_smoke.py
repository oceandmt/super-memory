def test_dream_full_cycle_dry_run_smoke():
    from super_memory.dream import dream_full_cycle
    r = dream_full_cycle(limit=10, dry_run=True)
    assert isinstance(r, dict)
    assert r.get("ok", True) is True
    assert r.get("dry_run") is True


def test_cross_agent_summary_smoke():
    from super_memory.cross_agent import CrossAgentTools
    r = CrossAgentTools().cross_agent_summary(agent_id="lucas", days=30)
    assert isinstance(r, dict)
    assert r.get("ok") is True
