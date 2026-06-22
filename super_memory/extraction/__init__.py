"""Super Memory extraction module: relation extraction and structure detection."""

from .relations import RelationCandidate, RelationType, extract_relations
from .structure_detector import StructuredContent, detect_structure

__all__ = [
    "RelationType", "RelationCandidate", "extract_relations",
    "StructuredContent", "detect_structure",
]
