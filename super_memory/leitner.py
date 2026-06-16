"""Leitner 5-box spaced repetition system for memory lifecycle.

Box 0: new/unreviewed → review daily
Box 1: reviewed once → review 3 days
Box 2: reviewed twice → review 7 days
Box 3: reviewed 3x → review 30 days
Box 4: mastered → review 90 days
Box -1: failed → reset to box 0

Uses memories.leiter_box + memories.next_review for state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .config import load_config
from .service import SuperMemoryService
from .storage import SuperMemoryStore

BOX_INTERVALS: dict[int, int] = {
    0: 1,
    1: 3,
    2: 7,
    3: 30,
    4: 90,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_review(box: int, reviewed_at: datetime | None = None) -> str:
    days = BOX_INTERVALS.get(box, 1)
    anchor = reviewed_at or datetime.now(timezone.utc)
    return (anchor + timedelta(days=days)).isoformat()


def _store(config_path: str | None = None) -> SuperMemoryStore:
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    return SuperMemoryStore(cfg)


def _ensure_columns(store: SuperMemoryStore) -> None:
    """Safe add leiter_box + next_review if schema hadn't been migrated yet."""
    with store.connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
        if "leiter_box" not in cols:
            conn.execute("ALTER TABLE memories ADD COLUMN leiter_box INTEGER NOT NULL DEFAULT 0")
        if "next_review" not in cols:
            conn.execute("ALTER TABLE memories ADD COLUMN next_review TEXT")
        conn.commit()


def queue(config_path: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Return memories due for review (next_review <= now)."""
    store = _store(config_path)
    _ensure_columns(store)
    now = _now()
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, layer, content, type, leiter_box, next_review, created_at "
            "FROM memories WHERE next_review IS NOT NULL AND next_review <= ? "
            "ORDER BY leiter_box ASC LIMIT ?",
            (now, limit),
        ).fetchall()
    due = []
    for r in rows:
        due.append({
            "id": r["id"],
            "layer": r["layer"],
            "content": r["content"][:200],
            "type": r["type"],
            "box": r["leiter_box"],
            "next_review": r["next_review"],
            "overdue_by": _overdue_seconds(r["next_review"]),
        })
    return {"ok": True, "due_count": len(due), "items": due}


def mark(fiber_id: str, success: bool, config_path: str | None = None) -> dict[str, Any]:
    """Record a review result. On success: box++. On failure: reset to box 0."""
    store = _store(config_path)
    _ensure_columns(store)
    with store.connect() as conn:
        row = conn.execute(
            "SELECT leiter_box FROM memories WHERE id = ?", (fiber_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": f"memory not found: {fiber_id}"}
        old_box = row["leiter_box"] or 0
        new_box = old_box + 1 if success else 0
        new_box = min(new_box, 4)
        next_rev = _next_review(new_box)
        conn.execute(
            "UPDATE memories SET leiter_box = ?, next_review = ? WHERE id = ?",
            (new_box, next_rev, fiber_id),
        )
        conn.commit()
    return {
        "ok": True,
        "memory_id": fiber_id,
        "success": success,
        "old_box": old_box,
        "new_box": new_box,
        "next_review": next_rev,
    }


def schedule(fiber_id: str, box: int, config_path: str | None = None) -> dict[str, Any]:
    """Manually set a memory's Leitner box."""
    store = _store(config_path)
    _ensure_columns(store)
    box = max(0, min(4, box))
    next_rev = _next_review(box)
    with store.connect() as conn:
        conn.execute(
            "UPDATE memories SET leiter_box = ?, next_review = ? WHERE id = ?",
            (box, next_rev, fiber_id),
        )
        conn.commit()
    return {
        "ok": True,
        "memory_id": fiber_id,
        "box": box,
        "next_review": next_rev,
    }


def stats(config_path: str | None = None) -> dict[str, Any]:
    """Leitner box distribution + review stats."""
    store = _store(config_path)
    _ensure_columns(store)
    now = _now()
    with store.connect() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        box_dist = {
            str(r["leiter_box"] or 0): r["c"]
            for r in conn.execute(
                "SELECT leiter_box, COUNT(*) as c FROM memories GROUP BY leiter_box"
            ).fetchall()
        }
        due = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE next_review IS NOT NULL AND next_review <= ?",
            (now,),
        ).fetchone()["c"]
    return {
        "ok": True,
        "total_memories": total,
        "box_distribution": box_dist,
        "due_for_review": due,
        "intervals_days": BOX_INTERVALS,
    }


def auto_seed(config_path: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Auto-assign Leitner boxes to unassigned memories (box=0, review today)."""
    store = _store(config_path)
    _ensure_columns(store)
    _next = _next_review(0)
    with store.connect() as conn:
        seeded = conn.execute(
            "UPDATE memories SET leiter_box = 0, next_review = ? "
            "WHERE (leiter_box IS NULL OR leiter_box = 0) AND next_review IS NULL LIMIT ?",
            (_next, limit),
        ).rowcount
        conn.commit()
    return {"ok": True, "seeded": seeded, "next_review": _next}


def _overdue_seconds(next_review: str | None) -> float | None:
    if not next_review:
        return None
    try:
        dt = datetime.fromisoformat(next_review.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None
