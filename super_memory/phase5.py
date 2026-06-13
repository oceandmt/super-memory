from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_IMAGE = "node:22-bookworm"
SAFE_ENV = {
    "OPENCLAW_DISABLE_NETWORK_CREDENTIALS": "1",
    "SUPER_MEMORY_PHASE5": "1",
    "SUPER_MEMORY_DISABLE_HEAVY_OPTIONAL": "1",
}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Phase5Plan:
    repo_root: str
    image: str = DEFAULT_IMAGE
    timeout: str = "45m"
    execute: bool = False
    checks: list[Check] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "image": self.image,
            "timeout": self.timeout,
            "execute": self.execute,
            "checks": [c.__dict__ for c in self.checks],
            "commands": self.commands,
            "files": self.files,
            "warnings": self.warnings,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


def check_prereqs() -> list[Check]:
    checks = []
    for binary in ["docker", "osb", "python", "node", "npm"]:
        path = shutil.which(binary)
        checks.append(Check(binary, bool(path), path or "not found"))
    return checks


def sandbox_config(repo_root: Path) -> str:
    plugin_path = repo_root / "openclaw-plugin" / "super-memory"
    return json.dumps(
        {
            "plugins": [
                {
                    "path": str(plugin_path),
                    "config": {
                        "apiBaseUrl": "http://127.0.0.1:8765",
                        "registerExclusiveMemoryCapability": True,
                        "registerLegacyMemoryShims": True,
                        "registerDynamicMcpToolProxy": True,
                        "registerSuperMemoryHooks": False,
                    },
                }
            ],
            "memory": {"mode": "super-memory-sandbox-fixture"},
            "safety": {
                "noRealCredentials": True,
                "noRealOpenClawMount": True,
                "phase4HeavyOptionalDisabled": True,
            },
        },
        indent=2,
    )


def build_plan(repo_root: Path, *, image: str = DEFAULT_IMAGE, timeout: str = "45m", execute: bool = False) -> Phase5Plan:
    plan = Phase5Plan(repo_root=str(repo_root), image=image, timeout=timeout, execute=execute)
    plan.checks = check_prereqs()
    plan.files = {
        "sandbox_config": sandbox_config(repo_root),
        "fixture_memory": "# Sandbox MEMORY fixture\n\n- Phase 5 fixture only; do not mount real ~/.openclaw read-write.\n",
    }
    plan.commands = [
        f"osb sandbox create --image {image} --timeout {timeout} -o json",
        "# copy repo into sandbox workspace using osb file APIs or git clone a test branch",
        "python -m venv .venv && . .venv/bin/activate && pip install -e .[dev]",
        "python -m super_memory.api --host 127.0.0.1 --port 8765",
        "node --check openclaw-plugin/super-memory/index.js",
        "node --check openclaw-plugin/super-memory/mcp-client.js",
        "pytest -q",
        "# install/run OpenClaw in sandbox only, then load generated sandbox config fixture",
        "# run memory_search/memory_get/plugin-load/hook smoke tests against sandbox OpenClaw",
    ]
    plan.warnings = [
        "Dry-run by default. Pass --execute only after reviewing the generated plan.",
        "Do not inject real provider tokens or mount the real ~/.openclaw read-write.",
        "Keep Phase 4 cloud/telegram/store/watch features disabled during sandbox backtest.",
    ]
    return plan


def execute_plan(plan: Phase5Plan) -> dict[str, Any]:
    if not plan.execute:
        return {"ok": True, "dry_run": True, "plan": plan.to_dict()}
    missing = [c.name for c in plan.checks if c.name in {"docker", "osb"} and not c.ok]
    if missing:
        return {"ok": False, "error": f"missing required sandbox prerequisites: {', '.join(missing)}", "plan": plan.to_dict()}
    # Keep execution intentionally bounded for this harness: verify local repo commands
    # before any sandbox lifecycle action. Sandbox lifecycle execution should be added
    # only when OpenSandbox endpoint details are known.
    results = []
    for cmd in ["python -m py_compile super_memory/*.py", "node --check openclaw-plugin/super-memory/index.js", "node --check openclaw-plugin/super-memory/mcp-client.js", "pytest -q"]:
        proc = subprocess.run(cmd, shell=True, cwd=plan.repo_root, text=True, capture_output=True, timeout=180)
        results.append({"command": cmd, "returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]})
        if proc.returncode != 0:
            return {"ok": False, "dry_run": False, "failed": cmd, "results": results, "plan": plan.to_dict()}
    return {"ok": True, "dry_run": False, "results": results, "plan": plan.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5 OpenSandbox/OpenClaw isolated backtest harness")
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--timeout", default="45m")
    parser.add_argument("--execute", action="store_true", help="Run bounded local verification; sandbox lifecycle remains guarded")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args(argv)
    plan = build_plan(Path(args.repo_root).resolve(), image=args.image, timeout=args.timeout, execute=args.execute)
    result = execute_plan(plan)
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
