"""Telemetry (P3) — usage tracking and analytics for Super Memory.

Tracks tool usage, recall patterns, save activity, and performance metrics.
Data is stored locally in SQLite; never sent externally.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from .config import load_config
from .service import SuperMemoryService
from .storage import SuperMemoryStore


def _now():
    return datetime.now(timezone.utc).isoformat()


def _store(config_path=None):
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    _init_tables(store)
    return store


def _init_tables(store):
    with store.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_events (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                agent_id TEXT,
                tool_name TEXT,
                duration_ms REAL,
                success INTEGER NOT NULL DEFAULT 1,
                detail_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_kind ON telemetry_events(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_tool ON telemetry_events(tool_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_agent ON telemetry_events(agent_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_daily (
                date TEXT PRIMARY KEY,
                tool_calls INTEGER NOT NULL DEFAULT 0,
                memories_saved INTEGER NOT NULL DEFAULT 0,
                recalls INTEGER NOT NULL DEFAULT 0,
                avg_duration_ms REAL NOT NULL DEFAULT 0,
                errors INTEGER NOT NULL DEFAULT 0,
                agents_active TEXT NOT NULL DEFAULT '[]',
                detail_json TEXT NOT NULL DEFAULT '{}'
            )
        """)


def record_event(kind, agent_id="lucas", tool_name=None, duration_ms=None, success=True, detail=None, config_path=None):
    """Record a telemetry event."""
    store = _store(config_path)
    event_id = f"tel:{kind}:{int(time.time() * 1000)}:{abs(hash(str(detail))) % 10**6}"
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO telemetry_events (id, kind, agent_id, tool_name, duration_ms, success, detail_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, kind, agent_id, tool_name, duration_ms, 1 if success else 0, json.dumps(detail or {}), _now()),
        )
    return {"ok": True, "event_id": event_id}


def record_save(agent_id="lucas", duration_ms=None, config_path=None):
    return record_event("save", agent_id=agent_id, tool_name="remember", duration_ms=duration_ms, config_path=config_path)


def record_recall(agent_id="lucas", duration_ms=None, config_path=None):
    return record_event("recall", agent_id=agent_id, tool_name="recall", duration_ms=duration_ms, config_path=config_path)


def record_error(agent_id="lucas", tool_name=None, detail=None, config_path=None):
    return record_event("error", agent_id=agent_id, tool_name=tool_name, success=False, detail=detail, config_path=config_path)


def record_tool_call(agent_id="lucas", tool_name=None, duration_ms=None, config_path=None):
    return record_event("tool_call", agent_id=agent_id, tool_name=tool_name, duration_ms=duration_ms, config_path=config_path)


def aggregate_daily(config_path=None):
    """Aggregate today's telemetry into daily rollup."""
    store = _store(config_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM telemetry_events WHERE created_at >= ?",
            (today,),
        ).fetchall()
    if not rows:
        return {"ok": True, "date": today, "events": 0}
    tool_calls = sum(1 for r in rows if r["kind"] == "tool_call")
    saves = sum(1 for r in rows if r["kind"] == "save")
    recalls = sum(1 for r in rows if r["kind"] == "recall")
    errors = sum(1 for r in rows if not r["success"])
    agents = set(r["agent_id"] for r in rows if r["agent_id"])
    durations = [r["duration_ms"] for r in rows if r["duration_ms"] is not None]
    avg_dur = sum(durations) / len(durations) if durations else 0
    detail = {
        "tool_calls": tool_calls, "saves": saves, "recalls": recalls,
        "errors": errors, "agents": sorted(agents),
    }
    with store.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO telemetry_daily (date, tool_calls, memories_saved, recalls, avg_duration_ms, errors, agents_active, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (today, tool_calls, saves, recalls, round(avg_dur, 2), errors, json.dumps(sorted(agents)), json.dumps(detail)),
        )
    return {"ok": True, "date": today, **detail, "avg_duration_ms": round(avg_dur, 2)}


def stats(days=7, config_path=None):
    """Get telemetry stats for recent days."""
    store = _store(config_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with store.connect() as conn:
        events = conn.execute(
            "SELECT * FROM telemetry_events WHERE created_at >= ? ORDER BY created_at DESC",
            (cutoff,),
        ).fetchall()
        daily = conn.execute(
            "SELECT * FROM telemetry_daily WHERE date >= ? ORDER BY date DESC",
            ((datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"),),
        ).fetchall()
    kind_counts = Counter(r["kind"] for r in events)
    tool_counts = Counter(r["tool_name"] for r in events if r["tool_name"])
    agent_counts = Counter(r["agent_id"] for r in events if r["agent_id"])
    errors = [r for r in events if not r["success"]]
    return {
        "ok": True,
        "days": days,
        "total_events": len(events),
        "by_kind": dict(kind_counts),
        "by_tool": dict(tool_counts.most_common(20)),
        "by_agent": dict(agent_counts),
        "errors_last_24h": len([e for e in events if not e["success"]]),
        "daily_rollups": [{"date": d["date"], "tool_calls": d["tool_calls"], "saves": d["memories_saved"], "recalls": d["recalls"], "errors": d["errors"]} for d in daily],
    }
