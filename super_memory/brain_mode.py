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

    def get_strategy(self, key: str) -> SyncStrategy:
        """Get sync strategy for a given key."""
        try:
            return self.sync_strategy
        except Exception:
            return SyncStrategy.MANUAL

    def validate(self) -> list[str]:
        """Validate configuration, returning list of warnings."""
        warnings: list[str] = []
        try:
            if self.max_spread_hops < 1:
                warnings.append("max_spread_hops must be >= 1")
            if self.max_spread_hops > 20:
                warnings.append("max_spread_hops > 20 may be expensive")
            if not 0.0 <= self.activation_threshold <= 1.0:
                warnings.append("activation_threshold out of range [0,1]")
            if not 0.0 <= self.dim_returns_threshold <= 1.0:
                warnings.append("dim_returns_threshold out of range [0,1]")
            if self.dim_returns_min_neurons < 1:
                warnings.append("dim_returns_min_neurons must be >= 1")
        except Exception as e:
            warnings.append(f"validation error: {e}")
        return warnings