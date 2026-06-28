from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_health_cache (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_vectors (
          id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
          memory_id TEXT NOT NULL,
          layer TEXT NOT NULL,
          vector TEXT NOT NULL DEFAULT '[]',
          provider TEXT,
          dimensions INTEGER,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE(memory_id, layer)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_vectors_memory_layer ON memory_vectors(memory_id, layer);
        CREATE INDEX IF NOT EXISTS idx_memories_id_layer ON memories(id, layer);
        CREATE INDEX IF NOT EXISTS idx_memories_layer_created ON memories(layer, created_at);
        """
    )


def set_cache(key: str, value: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    now = datetime.now(timezone.utc).isoformat()
    with store.connect() as conn:
        ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO memory_health_cache(key,value_json,updated_at) VALUES(?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), now),
        )
    return {"ok": True, "key": key, "updated_at": now}


def get_cache(key: str, config_path: str | None = None) -> dict[str, Any] | None:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        ensure_schema(conn)
        row = conn.execute("SELECT value_json, updated_at FROM memory_health_cache WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row["value_json"] or "{}")
    except Exception:
        value = {}
    value["cached"] = True
    value["cache_updated_at"] = row["updated_at"]
    return value


def self_heal_status_fast(config_path: str | None = None, *, bounded_limit: int = 100) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        ensure_schema(conn)
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_vectors'").fetchone()
        if not exists:
            out = {"ok": True, "mode": "fast", "table_exists": False, "missing_vectors": 0}
            set_cache("self_heal_status", out, config_path=config_path)
            return out
        missing_rows = conn.execute(
            """
            SELECT m.id FROM memories m
            LEFT JOIN memory_vectors v ON v.memory_id=m.id AND v.layer=m.layer
            WHERE m.content IS NOT NULL AND m.content != ''
              AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0) != 1
              AND v.id IS NULL
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
        eligible_sample = conn.execute(
            """
            SELECT COUNT(*) c FROM (
              SELECT id FROM memories
              WHERE content IS NOT NULL AND content != ''
                AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1
              LIMIT 100000
            )
            """
        ).fetchone()["c"]
    out = {
        "ok": True,
        "mode": "fast",
        "bounded": True,
        "table_exists": True,
        "missing_vectors": len(missing_rows),
        "missing_vectors_is_lower_bound": len(missing_rows) >= bounded_limit,
        "eligible_memories_sample": eligible_sample,
    }
    set_cache("self_heal_status", out, config_path=config_path)
    return out
