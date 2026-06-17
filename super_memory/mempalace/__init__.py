# MemPalace - Spatial Memory Intelligence Layer
# Inspired by mempalace/mempalace (GitHub) but local, no LLM cost

from .compressor import AAAKCompressor
from .dedup import deduplicate
from .entity_detector import detect_and_register, scan_text
from .entity_registry import EntityRegistry
from .extractor import SpatialExtractor
from .fact_checker import fact_check
from .hallways import build_hallways, find_path, list_hallways
from .knowledge_graph import KnowledgeGraph
from .loader import MemPalaceLoader
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
    "build_hallways",
    "deduplicate",
    "detect_and_register",
    "fact_check",
    "find_path",
    "find_similar_drawers",
    "list_hallways",
    "scan_text",
    "search_sqlite",
    "spellcheck_user_text",
    "spellcheck_with_registry",
]