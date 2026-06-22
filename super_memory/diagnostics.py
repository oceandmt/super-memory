"""Diagnostics — runtime health monitoring and milestone tracking.

Provides:
1. **Health check**: component availability, error rates, storage status
2. **Milestone tracking**: memory count growth, score improvements
3. **Alert management**: warning conditions with auto-resolution
4. **Dashboard summary**: single-call overview for MCP

Based on neural-memory v4.58.0 engine/diagnostics.py + core/alert.py.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "DiagnosticsConfig", "DiagnosticsReport", "DiagnosticsCollector",
    "get_diagnostics", "check_health", "record_milestone",
]

logger = logging.getLogger("super-memory.diagnostics")


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class DiagnosticsConfig:
    """Diagnostics configuration."""
    enabled: bool = True
    track_health: bool = True
    track_milestones: bool = True
    track_errors: bool = True
    health_interval_seconds: int = 300  # 5 min between full checks
    milestone_thresholds: list[int] = field(default_factory=lambda: [10, 50, 100, 250, 500, 1000, 2500, 5000])


# ── Report ───────────────────────────────────────────────────────────────────

@dataclass
class DiagnosticsReport:
    """Full diagnostics snapshot."""
    healthy: bool = True
    component_status: dict[str, bool] = field(default_factory=dict)
    component_errors: dict[str, str] = field(default_factory=dict)
    memory_count: int = 0
    session_count: int = 0
    uptime_hours: float = 0.0
    last_health_check: str = ""
    milestones: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version: str = ""
    duration_ms: float = 0.0


# ── Alert ────────────────────────────────────────────────────────────────────

@dataclass
class Alert:
    """A diagnostic alert."""
    severity: str  # info, warning, error, critical
    component: str
    message: str
    timestamp: str = ""
    resolved: bool = False
    resolved_at: str = ""


# ── Collector ────────────────────────────────────────────────────────────────

class DiagnosticsCollector:
    """Collects and reports diagnostics for super-memory.

    Tracks health checks, milestones, and component status.
    """

    def __init__(self, config: DiagnosticsConfig | None = None, version: str = "1.6.0"):
        self.config = config or DiagnosticsConfig()
        self.version = version
        self._start_time = time.time()
        self._alerts: list[Alert] = []
        self._milestones: list[dict[str, Any]] = []
        self._error_counts: dict[str, int] = defaultdict(int)
        self._last_health_check: float = 0.0
        self._health_cache: DiagnosticsReport | None = None

    # ── Health Check ─────────────────────────────────────────────────────────

    def check_health(self, force: bool = False) -> DiagnosticsReport:
        """Run a health check on all registered components.

        Uses caching (refreshes every health_interval_seconds) unless force=True.
        """
        now = time.time()
        if not force and self._health_cache and (now - self._last_health_check) < self.config.health_interval_seconds:
            return self._health_cache

        start = time.monotonic()
        report = DiagnosticsReport(version=self.version)
        report.uptime_hours = (now - self._start_time) / 3600

        # Component checks (best-effort, non-blocking)
        components = {
            "spreading_activation": self._check_import("super_memory.spreading_activation"),
            "firewall": self._check_import("super_memory.safety.firewall"),
            "freshness": self._check_import("super_memory.safety.freshness"),
            "encryption": self._check_import("super_memory.safety.encryption"),
            "dedup": self._check_import("super_memory.dedup.pipeline"),
            "relations": self._check_import("super_memory.extraction.relations"),
            "cache": self._check_import("super_memory.cache.manager"),
            "reranker": self._check_import("super_memory.reranker"),
            "quality_scorer": self._check_import("super_memory.quality_scorer"),
            "priming": self._check_import("super_memory.priming"),
            "reflex_arc": self._check_import("super_memory.reflex_arc"),
            "preference_detector": self._check_import("super_memory.preference_detector"),
            "sync": self._check_import("super_memory.sync.protocol"),
            "auto_deep": self._check_import("super_memory.auto_deep"),
        }

        report.component_status = {k: v["ok"] for k, v in components.items()}
        report.component_errors = {
            k: v.get("error", "") for k, v in components.items() if not v["ok"]
        }

        # Summary
        failed = sum(1 for v in report.component_status.values() if not v)
        report.healthy = failed == 0

        if failed > 0:
            report.warnings.append(f"{failed} component(s) unhealthy")
            for comp, err in report.component_errors.items():
                report.warnings.append(f"{comp}: {err[:100]}")

        # Alerts
        for alert in self._alerts:
            if not alert.resolved:
                report.warnings.append(f"[{alert.severity.upper()}] {alert.component}: {alert.message}")

        # Milestones
        report.milestones = self._milestones[-5:]  # Last 5

        report.last_health_check = datetime.now(timezone.utc).isoformat()
        report.duration_ms = (time.monotonic() - start) * 1000

        self._health_cache = report
        self._last_health_check = now
        return report

    @staticmethod
    def _check_import(module_path: str) -> dict[str, Any]:
        """Check if a module can be imported successfully."""
        try:
            __import__(module_path)
            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Milestones ───────────────────────────────────────────────────────────

    def record_milestone(self, name: str, value: int | float, metadata: dict[str, Any] | None = None) -> bool:
        """Record a milestone event.

        Returns True if milestone is newly achieved (first time).
        """
        if not self.config.track_milestones:
            return False

        # Check if already recorded
        for m in self._milestones:
            if m["name"] == name and m["value"] == value:
                return False  # Duplicate

        entry = {
            "name": name,
            "value": value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._milestones.append(entry)

        # Keep last 50
        if len(self._milestones) > 50:
            self._milestones = self._milestones[-50:]

        logger.info("milestone: %s = %s", name, value)
        return True

    def check_memory_milestone(self, memory_count: int) -> list[dict[str, Any]]:
        """Check if memory count crosses a milestone threshold.

        Returns newly achieved milestones.
        """
        achieved = []
        for threshold in self.config.milestone_thresholds:
            if memory_count >= threshold:
                recorded = self.record_milestone("memory_count", threshold, {"threshold": threshold})
                if recorded:
                    achieved.append({"name": "memory_count", "value": threshold})
        return achieved

    # ── Error Tracking ───────────────────────────────────────────────────────

    def record_error(self, component: str, error: str) -> None:
        """Record a component error for alert tracking."""
        if not self.config.track_errors:
            return
        self._error_counts[component] += 1
        count = self._error_counts[component]

        # Create alert if threshold exceeded
        if count in (1, 5, 10, 25, 50):
            self._alerts.append(Alert(
                severity="error" if count >= 10 else "warning",
                component=component,
                message=f"{count} errors recorded: {error[:100]}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

    def resolve_alert(self, component: str) -> None:
        """Resolve all active alerts for a component."""
        for alert in self._alerts:
            if alert.component == component and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.now(timezone.utc).isoformat()
        self._error_counts[component] = 0

    # ── Summary ──────────────────────────────────────────────────────────────

    def get_summary(self) -> dict[str, Any]:
        """Get a concise diagnostics summary for display."""
        report = self.check_health()
        return {
            "healthy": report.healthy,
            "components_ok": sum(1 for v in report.component_status.values() if v),
            "components_total": len(report.component_status),
            "warnings": len(report.warnings),
            "uptime_hours": round(report.uptime_hours, 1),
            "milestones": len(self._milestones),
            "active_alerts": sum(1 for a in self._alerts if not a.resolved),
            "version": self.version,
            "duration_ms": round(report.duration_ms, 1),
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_COLLECTOR: DiagnosticsCollector | None = None


def get_diagnostics() -> DiagnosticsCollector:
    global _COLLECTOR
    if _COLLECTOR is None:
        _COLLECTOR = DiagnosticsCollector()
    return _COLLECTOR


def check_health(force: bool = False) -> DiagnosticsReport:
    """Quick-access health check."""
    return get_diagnostics().check_health(force)


def record_milestone(name: str, value: int | float, metadata: dict[str, Any] | None = None) -> bool:
    """Quick-access milestone recording."""
    return get_diagnostics().record_milestone(name, value, metadata)
