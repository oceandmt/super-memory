"""Tests for diagnostics — runtime health monitoring."""
from __future__ import annotations

import pytest
from super_memory.diagnostics import (
    DiagnosticsCollector, DiagnosticsConfig, DiagnosticsReport,
    Alert, get_diagnostics, check_health, record_milestone,
)


class TestDiagnosticsCollector:
    def test_check_health(self):
        d = DiagnosticsCollector(DiagnosticsConfig(enabled=True), version="1.6.0")
        report = d.check_health(force=True)
        assert isinstance(report, DiagnosticsReport)
        assert report.version == "1.6.0"
        assert isinstance(report.healthy, bool)

    def test_health_has_components(self):
        d = DiagnosticsCollector()
        report = d.check_health(force=True)
        assert len(report.component_status) > 0

    def test_record_milestone(self):
        d = DiagnosticsCollector()
        ok = d.record_milestone("test_count", 100)
        assert ok is True
        # Duplicate should return False
        ok2 = d.record_milestone("test_count", 100)
        assert ok2 is False

    def test_check_memory_milestone(self):
        d = DiagnosticsCollector()
        d.config.milestone_thresholds = [10]
        achieved = d.check_memory_milestone(15)
        assert len(achieved) == 1
        assert achieved[0]["value"] == 10

    def test_record_error(self):
        d = DiagnosticsCollector()
        d.record_error("test_comp", "something broke")
        assert len(d._alerts) == 1
        assert d._alerts[0].severity == "warning"

    def test_resolve_alert(self):
        d = DiagnosticsCollector()
        d.record_error("test_comp", "error 1")
        d.resolve_alert("test_comp")
        assert all(a.resolved for a in d._alerts if a.component == "test_comp")

    def test_get_summary(self):
        d = DiagnosticsCollector()
        summary = d.get_summary()
        assert "healthy" in summary
        assert "components_ok" in summary
        assert "version" in summary


class TestSingleton:
    def test_get_diagnostics(self):
        d1 = get_diagnostics()
        d2 = get_diagnostics()
        assert d1 is d2


class TestCheckHealth:
    def test_check_health_function(self):
        report = check_health(force=True)
        assert isinstance(report, DiagnosticsReport)

    def test_record_milestone_function(self):
        ok = record_milestone("test_milestone", 1)
        assert isinstance(ok, bool)
