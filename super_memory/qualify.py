from __future__ import annotations

from pathlib import Path
from typing import Any

from . import bridge
from .capture_hook import CaptureHook
from .config import load_config
from .cross_agent import CrossAgentTools
from .handoff import HandoffTools
from .hybrid_recall import HybridRecall
from .session_archive import SessionArchive
from .session_timeline import SessionTimelineTools


def qualify_cross_agent(config_path: str | Path | None = None) -> dict[str, Any]:
    """Run an end-to-end cross-agent/cross-session qualification scenario.

    The scenario writes temporary Lucas/Alex memories, captures Honcho-style
    events, verifies cross-agent recall, session timeline/archive, handoff
    lifecycle, hybrid cross-scope recall, and core health contracts.
    """
    cfg = load_config(config_path)
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, details: Any = None) -> None:
        checks.append({"name": name, "ok": bool(ok), "details": details})

    suffix = "qualify-cross-agent"
    lucas_session = "qualify-lucas-session"
    alex_session = "qualify-alex-session"

    try:
        lucas = bridge.remember(
            {
                "content": "Lucas qualification memory: canonical markdown remains source of truth for cross-agent setup.",
                "type": "fact",
                "scope": "shared",
                "agent_id": "lucas",
                "session_id": lucas_session,
                "project": "super-memory",
                "tags": [suffix, "cross-agent"],
            },
            config_path=str(config_path) if config_path else None,
        )
        record("lucas_shared_remember", all(r.get("ok") for r in lucas.get("results", [])), lucas.get("record", {}).get("id"))
    except Exception as exc:  # pragma: no cover - defensive harness
        record("lucas_shared_remember", False, f"{type(exc).__name__}: {exc}")

    try:
        alex = bridge.remember(
            {
                "content": "Alex qualification memory: admin MCP profile exposes cross-session handoff tools.",
                "type": "context",
                "scope": "agent-local",
                "agent_id": "alex",
                "session_id": alex_session,
                "project": "super-memory",
                "tags": [suffix, "cross-session"],
            },
            config_path=str(config_path) if config_path else None,
        )
        record("alex_agent_local_remember", all(r.get("ok") for r in alex.get("results", [])), alex.get("record", {}).get("id"))
    except Exception as exc:  # pragma: no cover
        record("alex_agent_local_remember", False, f"{type(exc).__name__}: {exc}")

    try:
        capture = CaptureHook(cfg)
        capture.capture_turn(
            "Boss asks for cross-agent/session qualification",
            "Lucas runs qualifier harness",
            lucas_session,
            "lucas",
            "boss",
        )
        capture.capture_turn(
            "Boss asks Alex to verify handoff",
            "Alex verifies handoff bundle",
            alex_session,
            "alex",
            "boss",
        )
        record("capture_turns", True, {"sessions": [lucas_session, alex_session]})
    except Exception as exc:  # pragma: no cover
        record("capture_turns", False, f"{type(exc).__name__}: {exc}")

    try:
        ca = CrossAgentTools(cfg)
        agents = ca.list_agents().get("agents", [])
        alex_hits = ca.cross_agent_recall("admin MCP profile", "alex", 5).get("count", 0)
        record("cross_agent_recall", "alex" in agents and alex_hits > 0, {"agents": agents, "alex_hits": alex_hits})
    except Exception as exc:  # pragma: no cover
        record("cross_agent_recall", False, f"{type(exc).__name__}: {exc}")

    try:
        timeline = SessionTimelineTools(cfg)
        session_count = timeline.session_list().get("count", 0)
        lucas_events = timeline.session_timeline(lucas_session).get("count", 0)
        record("session_timeline", session_count > 0 and lucas_events > 0, {"sessions": session_count, "lucas_events": lucas_events})
    except Exception as exc:  # pragma: no cover
        record("session_timeline", False, f"{type(exc).__name__}: {exc}")

    try:
        archive = SessionArchive(cfg)
        summary = archive.create_session_summary(lucas_session)
        # Search using a term derived from captured turn content rather than
        # the qualifier keyword, which may not appear in the auto-generated
        # summary text.  Fall back through several candidates so the check is
        # robust even when fixture content evolves.
        search_count = 0
        for _term in ("Lucas", "qualifier", "qualification", "canonical"):
            search_count = archive.search_session_archives(_term).get("count", 0)
            if search_count > 0:
                break
        record("session_archive", bool(summary.get("ok")) and search_count > 0, {"search_count": search_count})
    except Exception as exc:  # pragma: no cover
        record("session_archive", False, f"{type(exc).__name__}: {exc}")

    try:
        handoff = HandoffTools(cfg)
        bundle = handoff.create_handoff(
            "lucas",
            "alex",
            "Qualification handoff",
            "Verify cross-agent/session memory setup",
            lucas_session,
            "qualification",
            5,
            {"source": "qualify_cross_agent"},
        )
        loaded = handoff.load_current_handoff("alex")
        completed = handoff.complete_handoff_with_outcome(
            bundle["bundle_id"],
            "Qualification handoff completed",
            ["qualify_cross_agent"],
            "passed",
        )
        record(
            "handoff_lifecycle",
            bool(bundle.get("ok")) and bool(loaded.get("ok")) and bool(completed.get("ok")),
            {"bundle_id": bundle.get("bundle_id")},
        )
    except Exception as exc:  # pragma: no cover
        record("handoff_lifecycle", False, f"{type(exc).__name__}: {exc}")

    try:
        hybrid = HybridRecall(cfg)
        result = hybrid.cross_scope_recall(
            "canonical markdown qualification",
            agent_scope="all",
            session_scope="all",
            source_layers=["markdown", "honcho", "mempalace", "graph"],
            limit=10,
        )
        record("hybrid_cross_scope_recall", result.get("count", 0) > 0, {"count": result.get("count", 0)})
    except Exception as exc:  # pragma: no cover
        record("hybrid_cross_scope_recall", False, f"{type(exc).__name__}: {exc}")

    try:
        payload = bridge.cross_layer_health(config_path=str(config_path) if config_path else None)
        critical_ok = (
            int(payload.get("sqlite_only_ids", 0)) == 0
            and int(payload.get("content_drift_count", 0)) == 0
        )
        record(
            "cross_layer_health",
            critical_ok,
            {
                "verdict": payload.get("verdict") or "checked",
                "sqlite_only_ids": payload.get("sqlite_only_ids"),
                "content_drift_count": payload.get("content_drift_count"),
                "orphan_projections_total": payload.get("orphan_projections_total"),
            },
        )
    except Exception as exc:  # pragma: no cover
        record("cross_layer_health", False, f"{type(exc).__name__}: {exc}")

    for name, fn in [
        ("memory_slot_contract", bridge.memory_slot_contract),
        ("mcp_contract_admin", lambda: bridge.mcp_contract(profile="admin")),
    ]:
        try:
            payload = fn()
            ok = bool(payload.get("ok", True)) and payload.get("verdict", "pass") != "fail"
            record(name, ok, payload.get("verdict") or payload.get("tool_count") or payload.get("status"))
        except Exception as exc:  # pragma: no cover
            record(name, False, f"{type(exc).__name__}: {exc}")

    hard_failures = [c for c in checks if not c["ok"] and c["name"] in {"lucas_shared_remember", "alex_agent_local_remember", "capture_turns", "cross_layer_health", "memory_slot_contract", "mcp_contract_admin"}]
    ok = not hard_failures
    verdict = "pass" if all(c["ok"] for c in checks) else ("warn" if ok else "fail")
    return {"ok": ok, "verdict": verdict, "checks": checks}
