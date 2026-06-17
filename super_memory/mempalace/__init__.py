# MemPalace - Spatial Memory Intelligence Layer
# Inspired by mempalace/mempalace (GitHub) but local, no LLM cost

from .compressor import AAAKCompressor
from .entity_detector import detect_and_register, scan_text
from .entity_registry import EntityRegistry
from .extractor import SpatialExtractor
from .loader import MemPalaceLoader
from .spatial import SpatialNavigator
from .spellcheck import spellcheck_user_text, spellcheck_with_registry

__all__ = [
    "AAAKCompressor",
    "EntityRegistry",
    "MemPalaceLoader",
    "SpatialExtractor",
    "SpatialNavigator",
    "detect_and_register",
    "scan_text",
    "spellcheck_user_text",
    "spellcheck_with_registry",
]