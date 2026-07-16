"""Auto-complete engine — suggest memory completions from brain neurons.

Provides prefix-based autocomplete and suggestion services for
memory recall, tool calling, and content generation.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore, row_to_memory


def _now():
    return datetime.now(timezone.utc).isoformat()


def _store(config_path=None):
    # Core schema is migrated by the service/runtime. Re-instantiating the full
    # service here reruns migrations and amplifies lock contention in tool smoke.
    store = SuperMemoryStore(load_config(config_path))
    _init_tables(store)
    return store


def _init_tables(store):
    with store.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS autocomplete_index (
                prefix TEXT NOT NULL,
                content TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                frequency INTEGER NOT NULL DEFAULT 1,
                type TEXT,
                PRIMARY KEY (prefix, memory_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_prefix ON autocomplete_index(prefix)")


def _rebuild_prefixes(config_path=None, max_memories: int = 5000):
    """Rebuild autocomplete prefixes from a bounded recent active corpus."""
    store = _store(config_path)
    with store.connect() as conn:
        conn.execute("DELETE FROM autocomplete_index")
        rows = conn.execute(
            "SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 "
            "ORDER BY created_at DESC LIMIT ?",
            (max(1, int(max_memories)),),
        ).fetchall()
        inserted = 0
        for row in rows:
            rec = row_to_memory(row)
            content = rec.content.strip()
            if len(content) < 3:
                continue
            words = re.split(r"\W+", content.lower())
            seen_prefixes = set()
            for word in words:
                if len(word) < 2:
                    continue
                for i in range(2, min(len(word) + 1, 16)):
                    prefix = word[:i]
                    key = (prefix, rec.id)
                    if key in seen_prefixes:
                        continue
                    seen_prefixes.add(key)
                    existing = conn.execute(
                        "SELECT frequency FROM autocomplete_index WHERE prefix=? AND memory_id=?",
                        (prefix, rec.id),
                    ).fetchone()
                    if existing:
                        conn.execute(
                            "UPDATE autocomplete_index SET frequency=frequency+1 WHERE prefix=? AND memory_id=?",
                            (prefix, rec.id),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO autocomplete_index (prefix, content, memory_id, frequency, type) VALUES (?, ?, ?, ?, ?)",
                            (prefix, content[:200], rec.id, 1, rec.type.value),
                        )
                    inserted += 1
    return {"ok": True, "entries_inserted": inserted}


def suggest(prefix: str, limit: int = 5, type_filter: str | None = None, config_path=None):
    """Suggest completions for a prefix."""
    if not prefix or len(prefix.strip()) < 1:
        return {"ok": True, "prefix": prefix, "suggestions": []}
    prefix = prefix.strip().lower()
    store = _store(config_path)
    with store.connect() as conn:
        query = "SELECT DISTINCT substring(content, 1, 80) as short_content, memory_id, frequency, type, content FROM autocomplete_index WHERE prefix=? ORDER BY frequency DESC LIMIT ?"
        params = [prefix, limit * 3]
        rows = conn.execute(query, params).fetchall()
    
    if not rows:
        # Fallback: LIKE search on memories
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT substring(content, 1, 80) as short_content, id as memory_id, 1 as frequency, type FROM memories WHERE lower(content) LIKE ? AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT ?",
                (f"{prefix}%", limit),
            ).fetchall()

    seen = set()
    suggestions = []
    for r in rows:
        if type_filter and r["type"] != type_filter:
            continue
        key = r["short_content"]
        if key in seen:
            continue
        seen.add(key)
        suggestions.append({
            "text": r["short_content"],
            "memory_id": r["memory_id"],
            "frequency": r["frequency"],
            "type": r["type"],
            "match": "prefix",
        })
        if len(suggestions) >= limit:
            break

    return {"ok": True, "prefix": prefix, "suggestions": suggestions, "count": len(suggestions)}


def idle_suggestions(config_path=None):
    """Find idle/neglected memories needing reinforcement.

    Returns memories with low access frequency for potential review.
    """
    store = _store(config_path)
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY RANDOM() LIMIT 20"
        ).fetchall()
    return {
        "ok": True,
        "idle_memories": [
            {"id": r["id"], "content": r["content"][:120], "type": r["type"], "layer": r["layer"]}
            for r in rows
        ],
    }


def rebuild(config_path=None):
    """Rebuild the full autocomplete index."""
    return _rebuild_prefixes(config_path=config_path)


def status(config_path=None):
    """Show autocomplete index status."""
    store = _store(config_path)
    with store.connect() as conn:
        try:
            count = conn.execute("SELECT COUNT(DISTINCT prefix) as c FROM autocomplete_index").fetchone()["c"]
        except Exception:
            count = 0
    return {"ok": True, "prefix_count": count}
