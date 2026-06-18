from __future__ import annotations

from pathlib import Path
from typing import Any

from .capture_hook import CaptureHook
from .config import load_config
from .migrations import run_migrations
from .session_archive import SessionArchive
from .session_timeline import SessionTimelineTools


def session_start_context(session_id: str, agent_id: str, query: str = "", config_path: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    run_migrations(cfg)
    timeline = SessionTimelineTools(cfg)
    events = timeline.session_timeline(session_id, limit=20)
    search = timeline.session_search(query or agent_id, limit=10) if query else {"count": 0, "events": []}
    return {"ok": True, "session_id": session_id, "agent_id": agent_id, "timeline": events, "search": search}


def post_turn_capture(
    user_message: str,
    assistant_message: str,
    session_id: str,
    agent_id: str,
    peer_id: str = "boss",
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    run_migrations(cfg)
    hook = CaptureHook(cfg)
    return hook.capture_turn(user_message, assistant_message, session_id, agent_id, peer_id)


def session_end_summary(session_id: str, config_path: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    run_migrations(cfg)
    archive = SessionArchive(cfg)
    return archive.create_session_summary(session_id)
