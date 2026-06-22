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


def generate_systemd_service(
    workspace_root: str | Path,
    config_path: str | Path = "~/.openclaw/super-memory.yaml",
    api_bind: str = "127.0.0.1:8765",
) -> str:
    """Generate systemd user service file content for always-on API service."""
    cfg_path = str(Path(config_path).expanduser())
    root = str(Path(workspace_root).expanduser())
    return """[Unit]
Description=Super Memory API (user-level)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%(python)s -m super_memory.api --host %(bind_host)s --port %(bind_port)s --config %(config)s
WorkingDirectory=%(root)s
Restart=on-failure
RestartSec=10
Environment=SUPER_MEMORY_WORKSPACE_ROOT=%(root)s

[Install]
WantedBy=default.target
""" % {
        "python": "super-memory-api" if "SUPER_MEMORY_API" not in __import__("os").environ else __import__("os").environ["SUPER_MEMORY_API"],
        "bind_host": api_bind.split(":")[0],
        "bind_port": api_bind.split(":")[1] if ":" in api_bind else "8765",
        "config": cfg_path,
        "root": root,
    }


def write_systemd_service(
    workspace_root: str | Path,
    config_path: str | Path = "~/.openclaw/super-memory.yaml",
    output_path: str | Path = "~/.config/systemd/user/super-memory-api.service",
    api_bind: str = "127.0.0.1:8765",
    overwrite: bool = False,
) -> Path:
    """Write systemd user service file.

    Args:
        workspace_root: OpenClaw workspace root path.
        config_path: Super Memory YAML config path.
        output_path: Systemd unit file output path.
        api_bind: API bind address (host:port).
        overwrite: Overwrite existing file if True.

    Returns:
        Path to written service file.
    """
    out = Path(output_path).expanduser()
    if out.exists() and not overwrite:
        raise FileExistsError(f"Systemd unit exists: {out}. Use overwrite=True or delete first.")
    out.parent.mkdir(parents=True, exist_ok=True)
    content = generate_systemd_service(workspace_root, config_path, api_bind)
    out.write_text(content, encoding="utf-8")
    return out


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
