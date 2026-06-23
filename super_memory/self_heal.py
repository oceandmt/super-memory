"""Self-heal — auto-detect and repair missing embeddings.

Matches OpenClaw memory-core self-heal pattern:
- Detect memories without embeddings
- Auto-rebuild missing embeddings
- Report repair stats
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore
from .embeddings_registry import select_best_adapter

logger = logging.getLogger(__name__)


def self_heal_embeddings(
    *,
    batch_size: int = 50,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Auto-detect and repair memories missing embeddings.

    Scans for memories without vector embeddings, generates them
    using the best available provider, and saves them back.

    Returns:
        Dict with repair stats
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    adapter = select_best_adapter()
    if adapter is None:
        return {"ok": False, "error": "no embedding provider available", "repaired": 0}

    detected = 0
    repaired = 0
    errors = 0
    provider = adapter.name

    # Check if memory_vectors table exists
    with store.connect() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_vectors'"
        ).fetchone()
        if not tables:
            return {
                "ok": True,
                "error": None,
                "detected": 0,
                "repaired": 0,
                "provider": provider,
                "note": "no memory_vectors table exists",
            }

        # Find memories missing vectors
        missing = conn.execute(
            """
            SELECT m.id, m.content, m.layer
            FROM memories m
            LEFT JOIN memory_vectors v ON v.memory_id = m.id AND v.layer = m.layer
            WHERE m.content IS NOT NULL
              AND m.content != ''
              AND v.id IS NULL
            LIMIT ?
            """,
            (batch_size,),
        ).fetchall()
        detected = len(missing)

        for mid, content, layer in missing:
            try:
                vec = adapter.embed(str(content))
                vec_json = json.dumps(vec)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_vectors (memory_id, layer, vector, provider, dimensions)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (mid, layer, vec_json, provider, len(vec)),
                )
                repaired += 1
            except Exception as exc:
                logger.error(f"self_heal: failed for {mid}: {exc}")
                errors += 1

    return {
        "ok": errors == 0,
        "detected": detected,
        "repaired": repaired,
        "errors": errors,
        "provider": provider,
    }


def self_heal_status(config_path: str | None = None) -> dict[str, Any]:
    """Show self-heal status — count of memories missing embeddings."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    try:
        with store.connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_vectors'"
            ).fetchone()
            if not tables:
                return {"ok": True, "total_memories": 0, "missing_vectors": 0, "table_exists": False}

            total = conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]
            missing = conn.execute(
                """
                SELECT COUNT(*) FROM memories m
                LEFT JOIN memory_vectors v ON v.memory_id = m.id AND v.layer = m.layer
                WHERE v.id IS NULL
                """
            ).fetchone()[0]
            return {
                "ok": True,
                "total_memories": total,
                "missing_vectors": missing,
                "table_exists": True,
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
