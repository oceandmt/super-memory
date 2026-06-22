"""3-tier dedup pipeline: SimHash → Embedding → LLM.
"""
from .config import DedupConfig
from .pipeline import DedupPipeline, DedupResult

__all__ = ["DedupConfig", "DedupPipeline", "DedupResult"]
