"""Configuration for 3-tier dedup pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DedupConfig:
    enabled: bool = True
    simhash_threshold: int = 7
    embedding_threshold: float = 0.85
    embedding_ambiguous_low: float = 0.75
    llm_enabled: bool = False
    llm_provider: str = "none"
    llm_max_pairs_per_encode: int = 3
    merge_strategy: str = "keep_newer"
    max_candidates: int = 30

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled, "simhash_threshold": self.simhash_threshold,
            "embedding_threshold": self.embedding_threshold,
            "embedding_ambiguous_low": self.embedding_ambiguous_low,
            "llm_enabled": self.llm_enabled, "llm_provider": self.llm_provider,
            "llm_max_pairs_per_encode": self.llm_max_pairs_per_encode,
            "merge_strategy": self.merge_strategy, "max_candidates": self.max_candidates,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DedupConfig:
        try:
            return cls(
                enabled=bool(data.get("enabled", True)),
                simhash_threshold=int(data.get("simhash_threshold", 7)),
                embedding_threshold=float(data.get("embedding_threshold", 0.85)),
                embedding_ambiguous_low=float(data.get("embedding_ambiguous_low", 0.75)),
                llm_enabled=bool(data.get("llm_enabled", False)),
                llm_provider=str(data.get("llm_provider", "none")),
                llm_max_pairs_per_encode=int(data.get("llm_max_pairs_per_encode", 3)),
                merge_strategy=str(data.get("merge_strategy", "keep_newer")),
                max_candidates=int(data.get("max_candidates", 30)),
            )
        except (ValueError, TypeError):
            return cls()
