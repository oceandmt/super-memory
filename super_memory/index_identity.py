"""Index identity tracking — track which embedding provider built the index.

Matches OpenClaw memory-core manager-embedding-errors:
- Store provider_id + model per index build
- Warn on mismatch when querying with different provider
- Auto-detect index identity on startup
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore

logger = logging.getLogger(__name__)

INDEX_IDENTITY_KEY = "index_identity"
INDEX_IDENTITY_TABLE = "meta_store"  # Using existing meta_store KV table


def _ensure_meta_table(store: SuperMemoryStore) -> None:
    """Ensure meta_store table exists."""
    with store.connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS meta_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )


def set_index_identity(
    provider_id: str,
    *,
    model: str = "",
    dimensions: int = 384,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Record which embedding provider built the index."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_meta_table(store)

    identity = {
        "provider_id": provider_id,
        "model": model,
        "dimensions": dimensions,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    with store.connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO meta_store (key, value) VALUES (?, ?)",
            (INDEX_IDENTITY_KEY, json.dumps(identity)),
        )
    logger.info(f"index_identity: set provider={provider_id} model={model}")
    return {"ok": True, "identity": identity}


def get_index_identity(config_path: str | None = None) -> dict[str, Any]:
    """Get the current index identity, if set."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_meta_table(store)
    try:
        with store.connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta_store WHERE key = ?", (INDEX_IDENTITY_KEY,)
            ).fetchone()
        if row:
            identity = json.loads(row[0])
            return {"ok": True, "identity": identity, "set": True}
    except Exception:
        pass
    return {"ok": True, "identity": None, "set": False}


def check_index_compatibility(
    provider_id: str,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Check if a provider is compatible with the current index.

    Returns warning if provider differs from index builder.
    """
    current = get_index_identity(config_path=config_path)
    if not current.get("set"):
        return {"ok": True, "compatible": True, "warning": None}

    index_provider = current["identity"]["provider_id"]
    if index_provider != provider_id:
        return {
            "ok": True,
            "compatible": False,
            "warning": (
                f"Index was built by '{index_provider}' "
                f"but querying with '{provider_id}'. "
                "Results may be suboptimal."
            ),
            "index_provider": index_provider,
            "query_provider": provider_id,
        }
    return {"ok": True, "compatible": True, "warning": None}
