from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_AGENTS = ["lucas", "alex", "max", "isol"]


def build_setup_config(
    workspace_root: str | Path,
    sqlite_path: str = "data/super-memory.sqlite3",
    agents: list[str] | None = None,
    require_canonical_first: bool = True,
    vector_backend: str = "sqlite_exact",
) -> dict[str, Any]:
    """Build a concrete Super Memory config for cross-agent/session operation."""
    root = str(Path(workspace_root).expanduser())
    return {
        "workspace_root": root,
        "sqlite_path": sqlite_path,
        "daily_memory_dir": "memory",
        "long_term_file": "MEMORY.md",
        "registers_dir": "memory/registers",
        "require_canonical_first": require_canonical_first,
        "enabled_layers": ["workspace_markdown", "mempalace", "honcho", "neural_memory"],
        "default_agents": agents or DEFAULT_AGENTS,
        "mcp_profile": "admin",
        "vector_backend": vector_backend,
        "cross_agent_memory": {
            "enabled": True,
            "required_fields": ["agent_id", "session_id", "scope"],
            "shared_scopes": ["shared", "project", "cross-agent"],
        },
        "cross_session_memory": {
            "enabled": True,
            "capture_tools": ["super_memory_capture_event", "super_memory_capture_turn"],
            "archive_tools": [
                "super_memory_create_session_summary",
                "super_memory_search_session_archives",
            ],
        },
    }


def write_setup_config(config: dict[str, Any], output_path: str | Path, overwrite: bool = False) -> Path:
    """Write setup YAML, refusing to clobber unless overwrite=True."""
    path = Path(output_path).expanduser()
    if path.exists() and not overwrite:
        raise FileExistsError(f"config exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def setup_instructions(config_path: str | Path) -> str:
    path = Path(config_path)
    return "\n".join(
        [
            "Super Memory cross-agent/session setup generated.",
            f"Config: {path}",
            "Next checks:",
            "  python -m super_memory.cli qualify-cross-agent --config " + str(path),
            "  super-memory-mcp --stdio --profile admin",
        ]
    )
