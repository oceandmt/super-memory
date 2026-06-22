"""Brain mode — multi-mode configuration for different storage profiles.

Ported from neural-memory v4.58.0 core/brain_mode.py.
"""
from __future__ import annotations
from enum import StrEnum
__all__ = ["BrainMode", "SyncStrategy", "BrainModeConfig"]
from dataclasses import dataclass
from typing import Any

class BrainMode(StrEnum):
    LOCAL = "local"
    HYBRID = "hybrid"
    READ_ONLY = "read_only"
    MIRROR = "mirror"

class SyncStrategy(StrEnum):
    MANUAL = "manual"
    AUTO_PUSH = "auto_push"
    AUTO_PULL = "auto_pull"
    BIDIRECTIONAL = "bidirectional"

@dataclass
class BrainModeConfig:
    mode: BrainMode = BrainMode.LOCAL
    sync_strategy: SyncStrategy = SyncStrategy.MANUAL
    max_spread_hops: int = 4
    activation_threshold: float = 0.05
    diminishing_returns_enabled: bool = True
    abstraction_constraint_enabled: bool = True
    abstraction_max_distance: int = 3
    dim_returns_threshold: float = 0.15
    dim_returns_min_neurons: int = 2
    dim_returns_grace_hops: int = 1