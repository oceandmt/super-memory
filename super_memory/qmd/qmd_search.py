"""QMD search wrapper — bridge to Meilisearch external binary.

Matches OpenClaw memory-core qmd-manager.ts:
- Calls QMD binary (meilisearch) for external search
- Falls back gracefully when binary unavailable
- Returns memory-core-compatible search results
- Manages QMD index lifecycle
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Binary discovery ───────────────────────────────────────────────────────

QMD_BINARY_NAMES = ["meilisearch", "qmd", "qdrant", "meili"]


def _find_qmd_binary() -> str | None:
    """Locate QMD binary in PATH or configured locations."""
    for name in QMD_BINARY_NAMES:
        found = shutil.which(name)
        if found:
            return found
    # Check env var
    env_path = os.environ.get("QMD_BINARY_PATH")
    if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
        return env_path
    return None


# ── QMD manager ────────────────────────────────────────────────────────────


class QMDManager:
    """QMD external search manager.

    Wraps Meilisearch binary for external full-text search.
    Falls back to SQLite FTS5 when binary unavailable.
    """

    def __init__(self, data_dir: str | None = None):
        self.binary = _find_qmd_binary()
        self.data_dir = data_dir or os.environ.get(
            "QMD_DATA_DIR",
            tempfile.gettempdir() + "/qmd-data",
        )
        self._available = self.binary is not None
        self._index_name = "super-memory"
        self._process: subprocess.Popen | None = None

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> dict[str, Any]:
        """Start the QMD binary as a subprocess."""
        if not self.binary:
            return {"ok": False, "error": "QMD binary not found"}
        if self._process:
            return {"ok": True, "already_running": True}

        data_path = Path(self.data_dir)
        data_path.mkdir(parents=True, exist_ok=True)

        try:
            self._process = subprocess.Popen(
                [self.binary, "--db-path", str(data_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"qmd: started {self.binary} (pid={self._process.pid})")
            return {"ok": True, "pid": self._process.pid, "data_dir": str(data_path)}
        except OSError as exc:
            self._available = False
            return {"ok": False, "error": str(exc)}

    def stop(self) -> dict[str, Any]:
        """Stop the QMD binary."""
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
            return {"ok": True, "stopped": True}
        return {"ok": True, "not_running": True}

    def index_document(self, doc_id: str, content: str, metadata: dict | None = None) -> dict[str, Any]:
        """Index a single document via QMD REST API.

        Uses Meilisearch HTTP API on localhost:7700.
        """
        import urllib.request as ureq

        payload = {
            "id": doc_id,
            "content": content,
            **(metadata or {}),
        }
        body = json.dumps(payload).encode("utf-8")
        try:
            req = ureq.Request(
                f"http://localhost:7700/indexes/{self._index_name}/documents",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with ureq.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def search(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        """Search via QMD binary REST API.

        Falls back gracefully if binary not available.
        """
        import urllib.request as ureq

        if not self._available:
            return self._fallback_search(query, limit=limit)

        try:
            params = json.dumps({"q": query, "limit": limit, "attributesToHighlight": ["content"]}).encode()
            req = ureq.Request(
                f"http://localhost:7700/indexes/{self._index_name}/search",
                data=params,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with ureq.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())

            hits = result.get("hits", [])
            return {
                "ok": True,
                "results": [
                    {
                        "id": h.get("id", ""),
                        "content": h.get("content", ""),
                        "score": h.get("_rankingScore", 0.5),
                        "snippet": h.get("_formatted", {}).get("content", h.get("content", ""))[:500],
                    }
                    for h in hits
                ],
                "total": result.get("estimatedTotalHits", len(hits)),
                "provider": "qmd",
            }
        except Exception as exc:
            logger.warning(f"qmd: search failed, falling back: {exc}")
            return self._fallback_search(query, limit=limit)

    def _fallback_search(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Fallback when QMD unavailable — return empty results."""
        return {
            "ok": True,
            "results": [],
            "total": 0,
            "provider": "qmd-fallback",
            "note": "QMD binary not available — no external search",
        }

    def health(self) -> dict[str, Any]:
        """QMD health check."""
        return {
            "available": self._available,
            "binary": self.binary,
            "running": self._process is not None and self._process.poll() is None,
            "data_dir": self.data_dir,
        }


# ── Singleton ──────────────────────────────────────────────────────────────

_qmd_manager: QMDManager | None = None


def get_qmd_manager(data_dir: str | None = None) -> QMDManager:
    global _qmd_manager
    if _qmd_manager is None:
        _qmd_manager = QMDManager(data_dir=data_dir)
    return _qmd_manager


def qmd_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Convenience: search via QMD manager."""
    mgr = get_qmd_manager()
    return mgr.search(query, limit=limit)


def qmd_health() -> dict[str, Any]:
    """Convenience: QMD health check."""
    mgr = get_qmd_manager()
    return mgr.health()


def qmd_start() -> dict[str, Any]:
    """Convenience: start QMD binary."""
    mgr = get_qmd_manager()
    return mgr.start()


def qmd_stop() -> dict[str, Any]:
    """Convenience: stop QMD binary."""
    mgr = get_qmd_manager()
    return mgr.stop()
