from __future__ import annotations
# MemPalace - Spatial Memory Intelligence Layer
# Inspired by mempalace/mempalace (GitHub) but local, no LLM cost

from .collision_scan import assert_no_collisions, scan_existing
from .compressor import AAAKCompressor
from .convo_miner import detect_entities_from_convo, mine_conversation, mine_directory
from .dedup import deduplicate
from .entity_detector import detect_and_register, scan_text
from .entity_registry import EntityRegistry
from .extractor import SpatialExtractor
from .fact_checker import fact_check
from .hallways import build_hallways, find_path, list_hallways
from .knowledge_graph import KnowledgeGraph
from .loader import MemPalaceLoader
from .onboarding import quick_setup, run_onboarding
from .searcher import find_similar_drawers, search_sqlite
from .spatial import SpatialNavigator
from .spellcheck import spellcheck_user_text, spellcheck_with_registry

__all__ = [
    "AAAKCompressor",
    "EntityRegistry",
    "KnowledgeGraph",
    "MemPalaceLoader",
    "SpatialExtractor",
    "SpatialNavigator",
    "assert_no_collisions",
    "build_hallways",
    "deduplicate",
    "detect_and_register",
    "detect_entities_from_convo",
    "fact_check",
    "find_path",
    "find_similar_drawers",
    "list_hallways",
    "mine_conversation",
    "mine_directory",
    "quick_setup",
    "run_onboarding",
    "scan_existing",
    "scan_text",
    "search_sqlite",
    "spellcheck_user_text",
    "spellcheck_with_registry",
]