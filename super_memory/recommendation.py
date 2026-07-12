"""Recommendation engine for Super Memory operational next actions.

This module intentionally stays deterministic and local-only. It aggregates
signals from existing health/audit helpers and returns ranked, actionable
recommendations for operators and agents.
"""

from __future__ import annotations

from typing import Any

from .config import load_config
from .memory_core import embedding_auto_select, short_term_audit
from .service import SuperMemoryService
from .stabilize import graph_health
from .storage import SuperMemoryStore


def _rec(
    action: str,
    reason: str,
    *,
    priority: int = 5,
    command: str | None = None,
    tool: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "reason": reason,
        "priority": priority,
        "command": command,
        "tool": tool,
        "evidence": evidence or {},
    }


def recommendations(limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    """Return ranked recommendations for Super Memory maintenance and UX.

    The result is intentionally MCP/CLI friendly: each recommendation includes
    an action, reason, priority, optional CLI command, optional MCP tool, and
    compact evidence. Higher priority means more urgent/actionable.
    """
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    items: list[dict[str, Any]] = []

    # Retrieval backend recommendation.
    embed = embedding_auto_select(config_path=config_path)
    doctor = embed.get("doctor", {})
    if doctor.get("warnings"):
        items.append(
            _rec(
                "Keep SQLite FTS retrieval active until semantic vector dependencies are healthy",
                "; ".join(doctor.get("warnings", [])),
                priority=8,
                command="super-memory doctor",
                tool="super_memory_deep_debug",
                evidence=doctor,
            )
        )
    else:
        items.append(
            _rec(
                f"Use {embed.get('selected')} as the active retrieval backend",
                embed.get("reason", "Backend selected by local health checks."),
                priority=4,
                tool="super_memory_status",
                evidence=doctor,
            )
        )

    # Autocomplete coverage recommendation.
    from . import autocomplete

    ac_status = autocomplete.status(config_path=config_path)
    prefix_count = int(ac_status.get("prefix_count") or 0)
    if prefix_count == 0:
        items.append(
            _rec(
                "Rebuild autocomplete prefix index",
                "No autocomplete prefixes are indexed yet, so prefix suggestions will be empty or fallback-only.",
                priority=9,
                command="super-memory autocomplete-rebuild",
                tool="super_memory_autocomplete_rebuild",
                evidence=ac_status,
            )
        )
    else:
        items.append(
            _rec(
                "Autocomplete index is available; use prefix suggestions in agent/UI flows",
                f"{prefix_count} distinct prefixes are indexed.",
                priority=3,
                tool="super_memory_autocomplete_suggest",
                evidence=ac_status,
            )
        )

    # Short-term promotion recommendations.
    try:
        audit = short_term_audit(limit=500, config_path=config_path)
        if audit.get("candidate_count", 0) > 0:
            items.append(
                _rec(
                    "Promote high-signal short-term memories",
                    f"Found {audit.get('candidate_count')} promotion candidates.",
                    priority=7,
                    command="super-memory short-term-repair --dry-run",
                    tool="super_memory_promotion_candidates",
                    evidence={"candidates": audit.get("candidates", [])[:3]},
                )
            )
    except Exception as exc:  # pragma: no cover - defensive for old DBs
        items.append(
            _rec(
                "Run deep debug before short-term promotion",
                f"Short-term audit could not run cleanly: {exc}",
                priority=5,
                tool="super_memory_deep_debug",
            )
        )

    # Graph consistency recommendations.
    try:
        graph = graph_health(store)
        for text in graph.get("recommendations", []):
            items.append(
                _rec(
                    text,
                    f"Graph health grade is {graph.get('grade', 'unknown')} with {graph.get('issues', 0)} warning(s).",
                    priority=6 if graph.get("grade") != "healthy" else 2,
                    tool="super_memory_full_drift_repair",
                    evidence={"grade": graph.get("grade"), "checks": graph.get("checks", {})},
                )
            )
    except Exception as exc:  # pragma: no cover - graph tables may be absent in partial installs
        items.append(
            _rec(
                "Initialize or rebuild graph projections",
                f"Graph health check is unavailable: {exc}",
                priority=5,
                tool="super_memory_graph_rebuild",
            )
        )

    items.sort(key=lambda r: r.get("priority", 0), reverse=True)
    return {"ok": True, "recommendations": items[: max(1, limit)], "count": min(len(items), max(1, limit))}
