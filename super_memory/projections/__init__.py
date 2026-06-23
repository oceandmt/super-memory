"""Projections package — derived layers from canonical Markdown.

P0 modules:
- closet.py: Semantic closets & drawers — verbatim-preserving pointer layer
"""

from .closet import (
    ClosetEntry,
    DrawerEntry,
    build_closets,
    rebuild_closets,
    search_closets,
    hydrate_closets,
    closet_stats,
)
