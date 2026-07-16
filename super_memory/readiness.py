"""Bounded, read-only readiness diagnostics for Super Memory.

Unlike the legacy health/status paths, this module never initializes storage,
runs migrations, checkpoints WAL, or calls an embedding provider. It is safe
for liveness/readiness probes against a live SQLite deployment.
"""

from __future__ import annotations

import os
import resource
import sqlite3
from pathlib import Path
from typing import Any

from .config import load_config
from .models import MemoryLayer, SuperMemoryConfig

_REQUIRED_MEMORY_COLUMNS = {"id", "layer", "content", "metadata_json"}
_DERIVED_LAYERS = (
    MemoryLayer.MEMPALACE.value,
    MemoryLayer.HONCHO.value,
    MemoryLayer.NEURAL_MEMORY.value,
)
_SAMPLE_LIMIT = 100


def _readonly_connection(path: Path) -> sqlite3.Connection:
    """Open an existing SQLite database without creating or mutating it."""
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=2000")
    return conn


def _fd_check() -> dict[str, Any]:
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    used: int | None = None
    try:
        used = len(os.listdir("/proc/self/fd"))
    except OSError:
        pass

    finite_limit = soft_limit if soft_limit not in (-1, resource.RLIM_INFINITY) else None
    ratio = (used / finite_limit) if used is not None and finite_limit else None
    status = "ok"
    if ratio is not None and ratio >= 0.8:
        status = "critical"
    elif ratio is not None and ratio >= 0.6:
        status = "warning"
    return {
        "status": status,
        "used": used,
        "soft_limit": finite_limit,
        "hard_limit": None if hard_limit in (-1, resource.RLIM_INFINITY) else hard_limit,
        "ratio": round(ratio, 4) if ratio is not None else None,
    }


def _database_check(cfg: SuperMemoryConfig) -> dict[str, Any]:
    path = Path(cfg.workspace_root) / cfg.sqlite_path
    result: dict[str, Any] = {
        "status": "unavailable",
        "path": str(path),
        "exists": path.is_file(),
        "wal_bytes": 0,
    }
    wal_path = Path(f"{path}-wal")
    try:
        if wal_path.is_file():
            result["wal_bytes"] = wal_path.stat().st_size
    except OSError:
        result["wal_bytes"] = None

    if not path.is_file():
        result["reason"] = "database_missing"
        return result

    try:
        with _readonly_connection(path) as conn:
            conn.execute("SELECT 1").fetchone()
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memories'"
            ).fetchone()
            if table is None:
                result.update(status="invalid_schema", reason="memories_table_missing")
                return result

            columns = {row["name"] for row in conn.execute("PRAGMA table_info(memories)")}
            missing = sorted(_REQUIRED_MEMORY_COLUMNS - columns)
            result["missing_columns"] = missing
            if missing:
                result.update(status="invalid_schema", reason="required_columns_missing")
                return result

            layer_rows = conn.execute(
                "SELECT layer, COUNT(*) AS count FROM memories GROUP BY layer"
            ).fetchall()
            result["layer_counts"] = {
                str(row["layer"]): int(row["count"]) for row in layer_rows
            }

            if "pending_canonical_sync" in columns:
                pending = conn.execute(
                    "SELECT COUNT(*) AS count FROM memories WHERE pending_canonical_sync=1"
                ).fetchone()
                result["pending_canonical_sync"] = int(pending["count"])
            else:
                result["pending_canonical_sync"] = None

            # Bounded parity probe: newest 100 canonical IDs only. Composite
            # primary-key lookups keep this safe for a frequent health probe.
            sample = conn.execute(
                "SELECT id FROM memories WHERE layer=? ORDER BY rowid DESC LIMIT ?",
                (MemoryLayer.WORKSPACE_MARKDOWN.value, _SAMPLE_LIMIT),
            ).fetchall()
            sample_ids = [str(row["id"]) for row in sample]
            enabled_layers = {layer.value for layer in cfg.enabled_layers}
            derived_layers = tuple(
                layer for layer in _DERIVED_LAYERS if layer in enabled_layers
            )
            missing_by_layer: dict[str, int] = {}
            if sample_ids:
                placeholders = ",".join("?" for _ in sample_ids)
                for layer in derived_layers:
                    row = conn.execute(
                        f"SELECT COUNT(DISTINCT id) AS count FROM memories "
                        f"WHERE layer=? AND id IN ({placeholders})",
                        (layer, *sample_ids),
                    ).fetchone()
                    missing_by_layer[layer] = len(sample_ids) - int(row["count"])
            else:
                missing_by_layer = {layer: 0 for layer in derived_layers}
            result["parity_sample"] = {
                "bounded": True,
                "sample_size": len(sample_ids),
                "missing_by_layer": missing_by_layer,
            }
            result["status"] = "ok"
            return result
    except (OSError, sqlite3.Error) as exc:
        result["reason"] = "read_failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def _vector_check(cfg: SuperMemoryConfig) -> dict[str, Any]:
    enabled = bool(getattr(cfg, "vector_enabled", False) or cfg.vector.enabled)
    result: dict[str, Any] = {"enabled": enabled, "status": "disabled"}
    if not enabled:
        return result

    # Keep aligned with VectorStore without instantiating it: construction may
    # create directories/tables and load a native extension.
    path = Path(cfg.workspace_root) / "data" / "vectors.sqlite3"
    result["path"] = str(path)
    if not path.is_file():
        result.update(status="unavailable", reason="vector_database_missing")
        return result
    try:
        with _readonly_connection(path) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='embeddings'"
            ).fetchone()
        if table is None:
            result.update(status="unavailable", reason="embeddings_table_missing")
        else:
            result["status"] = "ok"
    except (OSError, sqlite3.Error) as exc:
        result.update(
            status="unavailable",
            reason="vector_database_read_failed",
            error=f"{type(exc).__name__}: {exc}",
        )
    return result


def readiness(config_path: str | None = None) -> dict[str, Any]:
    """Return liveness plus bounded readiness evidence.

    ``ok`` remains process-liveness compatible with the old API. Operators and
    orchestrators must use ``ready`` for traffic admission.
    """
    cfg = load_config(config_path)
    enabled_layers = [layer.value for layer in cfg.enabled_layers]
    canonical = {
        "status": "ok",
        "canonical_first": bool(cfg.require_canonical_first),
        "workspace_markdown_enabled": MemoryLayer.WORKSPACE_MARKDOWN.value in enabled_layers,
    }
    if not canonical["canonical_first"] or not canonical["workspace_markdown_enabled"]:
        canonical["status"] = "invalid"

    checks = {
        "canonical": canonical,
        "database": _database_check(cfg),
        "vector": _vector_check(cfg),
        "file_descriptors": _fd_check(),
    }
    # The SLO collector is read-only and all event scans are time/row bounded.
    from .operational_slo import snapshot as slo_snapshot
    slo = slo_snapshot(
        Path(cfg.workspace_root) / cfg.sqlite_path,
        vector_path=Path(cfg.workspace_root) / "data" / "vectors.sqlite3",
    )
    # Probe responses should compare deterministically; generation time is
    # useful for persisted snapshots but not readiness evidence.
    slo.pop("generated_at", None)
    checks["operational_slo"] = slo
    blocking: list[str] = []
    if canonical["status"] != "ok":
        blocking.append("canonical")
    if checks["database"]["status"] != "ok":
        blocking.append("database")
    if checks["vector"]["enabled"] and checks["vector"]["status"] != "ok":
        blocking.append("vector")
    if checks["file_descriptors"]["status"] == "critical":
        blocking.append("file_descriptors")

    warnings: list[str] = []
    pending = checks["database"].get("pending_canonical_sync")
    if isinstance(pending, int) and pending > 0:
        warnings.append("pending_canonical_sync")
    parity = checks["database"].get("parity_sample", {}).get("missing_by_layer", {})
    if any(value > 0 for value in parity.values()):
        warnings.append("layer_projection_drift")
    if checks["file_descriptors"]["status"] == "warning":
        warnings.append("file_descriptor_pressure")

    return {
        "ok": True,
        "service": "super-memory",
        # Compatibility fields retained for existing MCP/API consumers. The
        # authoritative evidence is under checks and traffic gates use ready.
        "canonical_first": canonical["canonical_first"],
        "workspace_markdown_enabled": canonical["workspace_markdown_enabled"],
        "enabled_layers": enabled_layers,
        "ready": not blocking,
        "degraded": bool(blocking or warnings),
        "blocking": blocking,
        "warnings": warnings,
        "checks": checks,
    }
