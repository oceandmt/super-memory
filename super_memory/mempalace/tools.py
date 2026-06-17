"""MemPalace MCP tool definitions.

Exposes spatial memory navigation and 4-layer progressive loading
to OpenClaw MCP clients.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import SuperMemoryConfig
from .compressor import AAAKCompressor
from .extractor import SpatialExtractor
from .loader import MemPalaceLoader
from .spatial import SpatialNavigator


class MemPalaceTools:
    """MCP tool wrapper for MemPalace operations."""

    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.db_path = Path(config.workspace_root) / config.sqlite_path
        self.workspace_root = Path(config.workspace_root)
        self.loader = MemPalaceLoader(self.db_path, self.workspace_root)
        self.navigator = SpatialNavigator(self.db_path)
        self.extractor = SpatialExtractor()
        self.compressor = AAAKCompressor()

    def palace_search(
        self,
        query: str,
        wing: str | None = None,
        room: str | None = None,
        hall: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search within spatial scope (wing/room/hall)."""
        if not query or not isinstance(query, str) or query.strip() == "":
            return {"ok": False, "error": "Search query must be a non-empty string."}
        limit = max(1, min(limit, 200))
        results = self.navigator.search(query.strip(), wing=wing, room=room, hall=hall, limit=limit)
        return {
            "ok": True,
            "query": query,
            "spatial_scope": {"wing": wing, "room": room, "hall": hall},
            "results": results,
            "count": len(results),
        }

    def palace_load_layer(
        self,
        layer: int,
        query: str | None = None,
        wing: str | None = None,
        room: str | None = None,
        hall: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Load a specific memory layer (1-4)."""
        limit = max(1, min(limit, 200))
        if layer == 1:
            memories = self.loader.load_layer1_verbatim(limit=limit)
            return {
                "ok": True,
                "layer": 1,
                "name": "verbatim",
                "memories": [m.__dict__ for m in memories],
                "count": len(memories),
            }
        elif layer == 2:
            result = self.loader.load_layer2_structured(query=query, limit=limit)
            return {"ok": True, "layer": 2, "name": "structured", **result}
        elif layer == 3:
            result = self.loader.load_layer3_spatial(wing=wing, room=room, hall=hall, limit=limit)
            return {"ok": True, "layer": 3, "name": "spatial", **result}
        elif layer == 4:
            if not query:
                return {"ok": False, "error": "Layer 4 requires query parameter"}
            result = self.loader.load_layer4_compressed(query=query, limit=limit)
            return {"ok": True, "layer": 4, "name": "compressed", **result}
        else:
            return {"ok": False, "error": f"Invalid layer: {layer}. Must be 1-4."}

    def palace_wings(self) -> dict[str, Any]:
        """List all palace wings with counts."""
        wings = self.navigator.wings()
        return {"ok": True, "wings": wings, "count": len(wings)}

    def palace_rooms(self, wing: str | None = None) -> dict[str, Any]:
        """List rooms, optionally filtered by wing."""
        rooms = self.navigator.rooms(wing=wing)
        return {"ok": True, "wing": wing, "rooms": rooms, "count": len(rooms)}

    def palace_halls(self, wing: str | None = None, room: str | None = None) -> dict[str, Any]:
        """List halls, optionally filtered by wing/room."""
        halls = self.navigator.halls(wing=wing, room=room)
        return {"ok": True, "wing": wing, "room": room, "halls": halls, "count": len(halls)}

    def palace_drawers(
        self,
        wing: str | None = None,
        room: str | None = None,
        hall: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List drawers with optional spatial filters."""
        limit = max(1, min(limit, 200))
        drawers = self.navigator.drawers(wing=wing, room=room, hall=hall, limit=limit)
        return {
            "ok": True,
            "spatial_scope": {"wing": wing, "room": room, "hall": hall},
            "drawers": drawers,
            "count": len(drawers),
        }

    def palace_summary(self) -> dict[str, Any]:
        """Quick spatial overview."""
        summary = self.navigator.summary()
        return {"ok": True, "summary": summary}

    def palace_startup_context(self, max_tokens: int = 200) -> dict[str, Any]:
        """Generate minimal startup context (target ≤200 tokens)."""
        context = self.loader.startup_context(max_tokens=max_tokens)
        return {"ok": True, **context}

    def palace_extract(self, text: str) -> dict[str, Any]:
        """Extract entities, concepts, domains, and relationships from text."""
        extracted = self.extractor.extract_all(text)
        return {"ok": True, "text_length": len(text), **extracted}

    def palace_compress(self, texts: list[tuple[str, str]], query: str | None = None) -> dict[str, Any]:
        """Compress batch of (id, text) pairs and optionally search."""
        index = self.compressor.compress_batch(texts)
        stats = self.compressor.stats(index)
        result: dict[str, Any] = {
            "ok": True,
            "compressed_count": len(index.compressed),
            "stats": stats,
        }
        if query:
            results = self.compressor.search(query, index, limit=10)
            result["search_results"] = [
                {
                    "id": cm.id,
                    "keywords": cm.keywords,
                    "dense_text": cm.dense_text,
                    "compression_ratio": cm.compression_ratio,
                }
                for cm in results
            ]
        return result


# MCP tool descriptors
MEMPALACE_TOOLS = [
    {
        "name": "super_memory_palace_search",
        "description": "Search memories within spatial scope (wing/room/hall)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "wing": {"type": "string", "description": "Filter by palace wing (e.g. project name)"},
                "room": {"type": "string", "description": "Filter by room (e.g. session or type)"},
                "hall": {"type": "string", "description": "Filter by hall (facts, events, decisions, etc.)"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "super_memory_palace_load_layer",
        "description": "Load a specific memory layer (1=verbatim, 2=structured, 3=spatial, 4=compressed)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer": {"type": "integer", "minimum": 1, "maximum": 4, "description": "Layer number 1-4"},
                "query": {"type": "string", "description": "Query for layers 2 and 4"},
                "wing": {"type": "string", "description": "Wing filter for layer 3"},
                "room": {"type": "string", "description": "Room filter for layer 3"},
                "hall": {"type": "string", "description": "Hall filter for layer 3"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "required": ["layer"],
        },
    },
    {
        "name": "super_memory_palace_wings",
        "description": "List all palace wings with memory counts",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "super_memory_palace_rooms",
        "description": "List palace rooms, optionally filtered by wing",
        "inputSchema": {
            "type": "object",
            "properties": {"wing": {"type": "string", "description": "Filter by wing"}},
            "required": [],
        },
    },
    {
        "name": "super_memory_palace_halls",
        "description": "List palace halls, optionally filtered by wing/room",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string"},
                "room": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "super_memory_palace_drawers",
        "description": "List palace drawers with optional spatial filters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "hall": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "super_memory_palace_summary",
        "description": "Quick spatial overview (wings/rooms/halls/drawers counts)",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "super_memory_palace_startup_context",
        "description": "Generate minimal startup context (target ≤200 tokens)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_tokens": {"type": "integer", "minimum": 50, "maximum": 500, "default": 200},
            },
            "required": [],
        },
    },
    {
        "name": "super_memory_palace_extract",
        "description": "Extract entities, concepts, domains, and relationships from text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to analyze"}},
            "required": ["text"],
        },
    },
]
