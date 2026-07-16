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
    """Record a telemetry event. Backward compatible: record_event(kind, success, detail)."""
    if isinstance(agent_id, bool) or isinstance(agent_id, int):
        success = bool(agent_id)
        if isinstance(tool_name, dict) and detail is None:
            detail = tool_name
            tool_name = None
        agent_id = "lucas"
    if isinstance(tool_name, dict) and detail is None:
        detail = tool_name
        tool_name = None
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

class TelemetryRegistry:
    """In-memory metrics registry with Prometheus text export (test/dev helper)."""
    def __init__(self):
        self.counters = Counter()
        self.observations: dict[str, list[float]] = defaultdict(list)
    def _metric(self, name: str) -> str:
        return "super_memory_" + str(name).replace('.', '_').replace('-', '_')
    def inc(self, name: str, value: int = 1):
        self.counters[name] += value
    def observe_ms(self, name: str, value: float):
        self.observations[name].append(float(value))
    def prometheus_text(self) -> str:
        lines=[]
        for k,v in sorted(self.counters.items()):
            lines.append(f"{self._metric(k)} {v}")
        for k, vals in sorted(self.observations.items()):
            if not vals: continue
            metric=self._metric(k)
            lines.append(f"{metric}_count {len(vals)}")
            lines.append(f"{metric}_avg {sum(vals)/len(vals):.3f}")
        return "\n".join(lines) + ("\n" if lines else "")

def telemetry_history(kind: str | None = None, limit: int = 100, config_path=None):
    store = _store(config_path)
    with store.connect() as conn:
        if kind:
            rows = conn.execute("SELECT * FROM telemetry_events WHERE kind=? ORDER BY created_at DESC LIMIT ?", (kind, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM telemetry_events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    events=[]
    for r in rows:
        d=dict(r)
        try: d['detail']=json.loads(d.pop('detail_json') or '{}')
        except Exception: d['detail']={}
        events.append(d)
    return {'ok': True, 'events': events}

def operational_slo(days: int = 1, limit: int = 10000, config_path=None):
    """Return the bounded operational SLO view over local telemetry/storage."""
    from pathlib import Path
    from .operational_slo import snapshot
    cfg = load_config(config_path)
    return snapshot(
        Path(cfg.workspace_root) / cfg.sqlite_path,
        vector_path=Path(cfg.workspace_root) / "data" / "vectors.sqlite3",
        window_hours=max(1, min(int(days), 30)) * 24,
        limit=limit,
    )
