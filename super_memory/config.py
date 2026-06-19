from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import SuperMemoryConfig

DEFAULT_CONFIG_PATHS = [
    Path("super-memory.yaml"),
    Path(".openclaw/super-memory.yaml"),
    Path("config/super-memory.yaml"),
    Path.home() / ".openclaw" / "super-memory.yaml",
]


def load_config(path: str | Path | None = None) -> SuperMemoryConfig:
    candidates = [Path(path)] if path else DEFAULT_CONFIG_PATHS
    data: dict[str, Any] = {}
    for candidate in candidates:
        if candidate.exists():
            data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            break
    if env_root := os.getenv("SUPER_MEMORY_WORKSPACE_ROOT"):
        data["workspace_root"] = env_root
    if env_sqlite := os.getenv("SUPER_MEMORY_SQLITE_PATH"):
        data["sqlite_path"] = env_sqlite
    if env_token := (os.getenv("SUPER_MEMORY_API_TOKEN") or os.getenv("API_TOKEN")):
        data["api_token"] = env_token
    return SuperMemoryConfig(**data)
