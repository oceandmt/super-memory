"""Activation cache — thermal state save/load for warm-start recall.

Ported from neural-memory v4.58.0 cache/.
SSC-lite: Sparse Selective Restore for query-embedding ranked warm activation.
"""
from .manager import ActivationCache, get_cache_manager
from .selector import select_warm_activations

__all__ = ["ActivationCache", "get_cache_manager", "select_warm_activations"]
