"""Activation cache — save/load thermal states for warm-start recall."""
from __future__ import annotations
import json, logging, time
from typing import Any

logger = logging.getLogger("super-memory.cache")

class ActivationCache:
    def __init__(self, store: Any, ttl_seconds: int = 3600):
        self._store = store
        self._ttl = ttl_seconds
        self._cache: dict[str, float] = {}

    def save_snapshot(self, activations: dict[str, float]) -> bool:
        try:
            now = time.time()
            data = {k: v for k, v in activations.items() if v >= 0.05}
            data["_timestamp"] = now
            with self._store.connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                    ("_activation_cache", json.dumps(data, ensure_ascii=False)),
                )
                conn.commit()
            self._cache = data
            return True
        except Exception as e:
            logger.debug("cache save failed: %s", e)
            return False

    def load_snapshot(self) -> dict[str, float]:
        try:
            now = time.time()
            if self._cache and self._cache.get("_timestamp", 0) + self._ttl > now:
                return {k: v for k, v in self._cache.items() if k != "_timestamp"}
            with self._store.connect() as conn:
                row = conn.execute("SELECT value FROM metadata WHERE key='_activation_cache'").fetchone()
            if row:
                data = json.loads(row["value"])
                ts = data.get("_timestamp", 0)
                if ts + self._ttl > now:
                    self._cache = data
                    return {k: v for k, v in data.items() if k != "_timestamp"}
            return {}
        except Exception as e:
            logger.debug("cache load failed: %s", e)
            return {}

    def invalidate(self) -> None:
        self._cache = {}
        try:
            with self._store.connect() as conn:
                conn.execute("DELETE FROM metadata WHERE key='_activation_cache'")
                conn.commit()
        except Exception:
            pass


_cache_instances: dict[str, ActivationCache] = {}

def get_cache_manager(store: Any) -> ActivationCache:
    key = id(store)
    if key not in _cache_instances:
        _cache_instances[key] = ActivationCache(store)
    return _cache_instances[key]
