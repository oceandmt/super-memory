import json
import subprocess
import sys
from pathlib import Path

from super_memory.phase5 import build_plan, execute_plan


def test_phase5_plan_is_safe_by_default(tmp_path: Path):
    plan = build_plan(tmp_path)
    data = plan.to_dict()
    assert data["execute"] is False
    assert "noRealCredentials" in data["files"]["sandbox_config"]
    assert "noRealOpenClawMount" in data["files"]["sandbox_config"]
    assert "phase4HeavyOptionalDisabled" in data["files"]["sandbox_config"]
    assert any("Dry-run" in warning for warning in data["warnings"])
    assert any("pytest -q" in cmd for cmd in data["commands"])


def test_phase5_execute_without_execute_is_dry_run(tmp_path: Path):
    plan = build_plan(tmp_path)
    result = execute_plan(plan)
    assert result["ok"] is True
    assert result["dry_run"] is True


def test_phase5_cli_dry_run_outputs_json():
    proc = subprocess.run(
        [sys.executable, "scripts/phase5_sandbox_backtest.py"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["plan"]["image"] == "node:22-bookworm"
