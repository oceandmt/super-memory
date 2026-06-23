"""Recall Feedback Loop — learn from recall outcomes.

Records every recall event with query, selected IDs, and whether the result
was used, corrected, or contradicted. Feeds back into:
- quality/lifecycle reinforcement
- failed recall → training case generation
- type/trust updates
- benchmark regression cases

Borrowed from:
- Neural Memory: reinforcement through retrieval logging
- Honcho: conclusion derivation from outcome patterns
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from ..config import load_config
from ..storage import SuperMemoryStore

logger = logging.getLogger("super-memory.recall.feedback")


# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class RecallEvent:
    """A single recall event record."""
    id: str
    query: str
    selected_memory_ids: list[str]
    timestamp: str
    shown_to_user: bool = True
    used_in_answer: bool = False
    corrected_by_user: bool = False
    contradicted: bool = False
    missed_expected: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = "recall_v3"  # which recall pipeline produced this


@dataclass
class FeedbackOutcome:
    """Outcome feedback for a single recall event."""
    recall_event_id: str
    memory_id: str
    outcome: str  # "used", "ignored", "corrected", "contradicted", "missed"
    confidence: float = 1.0
    timestamp: str = ""
    notes: str = ""


# ── Tables ───────────────────────────────────────────────────────────────────

def _ensure_tables(store: SuperMemoryStore) -> None:
    with store.connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS recall_events (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                selected_memory_ids TEXT NOT NULL DEFAULT '[]',
                timestamp TEXT NOT NULL,
                shown_to_user INTEGER NOT NULL DEFAULT 1,
                used_in_answer INTEGER NOT NULL DEFAULT 0,
                corrected_by_user INTEGER NOT NULL DEFAULT 0,
                contradicted INTEGER NOT NULL DEFAULT 0,
                missed_expected TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'recall_v3',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_recall_events_query ON recall_events(query);
            CREATE INDEX IF NOT EXISTS idx_recall_events_timestamp ON recall_events(timestamp);

            CREATE TABLE IF NOT EXISTS recall_feedback (
                id TEXT PRIMARY KEY,
                recall_event_id TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                notes TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_recall_feedback_event ON recall_feedback(recall_event_id);
            CREATE INDEX IF NOT EXISTS idx_recall_feedback_memory ON recall_feedback(memory_id);
            CREATE INDEX IF NOT EXISTS idx_recall_feedback_outcome ON recall_feedback(outcome);
        """)


# ── Record ───────────────────────────────────────────────────────────────────

def record_recall_event(
    query: str,
    selected_memory_ids: list[str],
    *,
    shown_to_user: bool = True,
    source: str = "recall_v3",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Record a recall event (who was returned for a query)."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    event = RecallEvent(
        id=str(uuid.uuid4()),
        query=query,
        selected_memory_ids=selected_memory_ids,
        timestamp=datetime.now(timezone.utc).isoformat(),
        shown_to_user=shown_to_user,
        source=source,
    )

    with store.connect() as conn:
        conn.execute(
            "INSERT INTO recall_events (id, query, selected_memory_ids, timestamp, shown_to_user, source) VALUES (?, ?, ?, ?, ?, ?)",
            (event.id, event.query, json.dumps(event.selected_memory_ids), event.timestamp, 1 if event.shown_to_user else 0, event.source),
        )
        conn.commit()

    return {"ok": True, "event_id": event.id, "event": asdict(event)}


def record_feedback(
    recall_event_id: str,
    memory_id: str,
    outcome: str,
    *,
    confidence: float = 1.0,
    notes: str = "",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Record outcome feedback for a specific memory in a recall event.

    Outcome values: "used", "ignored", "corrected", "contradicted", "missed"
    """
    if outcome not in ("used", "ignored", "corrected", "contradicted", "missed"):
        return {"ok": False, "error": f"invalid outcome: {outcome}"}

    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    feedback = FeedbackOutcome(
        recall_event_id=recall_event_id,
        memory_id=memory_id,
        outcome=outcome,
        confidence=confidence,
        timestamp=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )

    with store.connect() as conn:
        conn.execute(
            "INSERT INTO recall_feedback (id, recall_event_id, memory_id, outcome, confidence, timestamp, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), feedback.recall_event_id, feedback.memory_id, feedback.outcome, feedback.confidence, feedback.timestamp, feedback.notes),
        )

        # Update recall event outcome flags
        if outcome == "corrected":
            conn.execute("UPDATE recall_events SET corrected_by_user=1 WHERE id=?", (recall_event_id,))
        elif outcome == "contradicted":
            conn.execute("UPDATE recall_events SET contradicted=1 WHERE id=?", (recall_event_id,))
        elif outcome == "used":
            conn.execute("UPDATE recall_events SET used_in_answer=1 WHERE id=?", (recall_event_id,))

        conn.commit()

    return {"ok": True, "feedback": asdict(feedback)}


def record_correction(
    query: str,
    memory_id: str,
    wrong_answer: str = "",
    expected_answer: str = "",
    notes: str = "",
    config_path: str | None = None,
) -> dict[str, Any]:
    """Convenience: record a correction (failed recall → training case)."""
    # Create recall event
    event = record_recall_event(
        query=query,
        selected_memory_ids=[memory_id] if memory_id else [],
        shown_to_user=True,
        source="recall_feedback",
        config_path=config_path,
    )
    if not event.get("ok"):
        return event

    # Record correction feedback
    fb = record_feedback(
        recall_event_id=event["event_id"],
        memory_id=memory_id,
        outcome="corrected",
        notes=notes,
        config_path=config_path,
    )

    # Save training case
    from ..self_training import capture_failed_recall
    case = capture_failed_recall(
        query=query,
        wrong_answer=wrong_answer,
        expected_answer=expected_answer,
        notes=notes,
        config_path=config_path,
    )

    return {
        "ok": True,
        "event_id": event["event_id"],
        "feedback": fb,
        "training_case": case,
    }


# ── Stats ────────────────────────────────────────────────────────────────────

def feedback_stats(config_path: str | None = None) -> dict[str, Any]:
    """Get recall feedback statistics."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    with store.connect() as conn:
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM recall_events").fetchone()["c"]
            used = conn.execute("SELECT COUNT(*) as c FROM recall_events WHERE used_in_answer=1").fetchone()["c"]
            corrected = conn.execute("SELECT COUNT(*) as c FROM recall_events WHERE corrected_by_user=1").fetchone()["c"]
            contradicted = conn.execute("SELECT COUNT(*) as c FROM recall_events WHERE contradicted=1").fetchone()["c"]
            fb_total = conn.execute("SELECT COUNT(*) as c FROM recall_feedback").fetchone()["c"]
            fb_by_outcome = conn.execute("SELECT outcome, COUNT(*) as c FROM recall_feedback GROUP BY outcome").fetchall()
        except Exception:
            return {"ok": True, "message": "no feedback data yet", "total_events": 0, "total_feedback": 0}

    return {
        "ok": True,
        "total_events": total,
        "used_in_answer": used,
        "corrected": corrected,
        "contradicted": contradicted,
        "success_rate": round(used / max(total, 1) * 100, 1),
        "correction_rate": round(corrected / max(total, 1) * 100, 1),
        "total_feedback": fb_total,
        "feedback_by_outcome": {r["outcome"]: r["c"] for r in fb_by_outcome},
    }


# ── Training Case Generation ─────────────────────────────────────────────────

def generate_training_cases(min_corrections: int = 3, config_path: str | None = None) -> dict[str, Any]:
    """Generate benchmark training cases from corrected recall events."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recall_events WHERE corrected_by_user=1 ORDER BY timestamp DESC LIMIT 50"
        ).fetchall()

    cases = []
    for row in rows:
        try:
            selected = json.loads(row["selected_memory_ids"]) if row["selected_memory_ids"] else []
        except (json.JSONDecodeError, TypeError):
            selected = []
        case = {
            "query": row["query"],
            "expected_memory_ids": selected,
            "source": "recall_feedback",
            "timestamp": row["timestamp"],
            "notes": row["notes"],
        }
        cases.append(case)

    # Save to recall_cases directory
    from pathlib import Path
    root = Path(cfg.workspace_root) / "projects" / "super-memory-github" / "tests" / "recall_cases"
    root.mkdir(parents=True, exist_ok=True)

    saved = []
    for case in cases:
        fname = f"auto-feedback-{case['timestamp'][:19].replace(':', '-')}.json"
        fpath = root / fname
        fpath.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        saved.append(str(fpath))

    return {
        "ok": True,
        "cases_generated": len(cases),
        "saved_to": saved,
    }
