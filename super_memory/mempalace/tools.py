"""MemPalace MCP tool definitions.

Exposes spatial memory navigation, 4-layer progressive loading,
entity registry, entity detection, spellcheck, BM25 hybrid search,
deduplication, hallways, knowledge graph, and fact checking
to OpenClaw MCP clients.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import SuperMemoryConfig
from .compressor import AAAKCompressor
from .dedup import deduplicate
from .entity_detector import detect_and_register
from .entity_registry import EntityRegistry
from .extractor import SpatialExtractor
from .fact_checker import fact_check
from .hallways import build_hallways as _build_hallways, find_path as _find_path, list_hallways as _list_hallways
from .knowledge_graph import KnowledgeGraph
from .loader import MemPalaceLoader
from .searcher import find_similar_drawers as _find_similar_drawers, search_sqlite as _search_sqlite
from .spatial import SpatialNavigator
from .spellcheck import spellcheck_with_registry


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
        self._entity_registry: EntityRegistry | None = None
        self._knowledge_graph: KnowledgeGraph | None = None

    @property
    def entity_registry(self) -> EntityRegistry:
        if self._entity_registry is None:
            self._entity_registry = EntityRegistry.load(
                workspace_root=str(self.workspace_root)
            )
        return self._entity_registry

    @property
    def knowledge_graph(self) -> KnowledgeGraph:
        if self._knowledge_graph is None:
            self._knowledge_graph = KnowledgeGraph(str(self.db_path))
        return self._knowledge_graph

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

    # ── Entity Registry Tools ────────────────────────────────────────────

    def entity_list(self, kind: str | None = None) -> dict[str, Any]:
        entities = self.entity_registry.list_all(kind=kind)
        return {"ok": True, "entities": entities, "count": len(entities)}

    def entity_lookup(self, name: str, context: str = "") -> dict[str, Any]:
        result = self.entity_registry.lookup(name, context=context)
        return {"ok": True, "name": name, **result}

    def entity_add(self, name: str, kind: str = "person", confidence: float = 1.0, aliases: list[str] | None = None) -> dict[str, Any]:
        self.entity_registry.add(name=name, kind=kind, source="onboarding", confidence=confidence, aliases=aliases)
        self.entity_registry.save()
        return {"ok": True, "added": name, "kind": kind, "confidence": confidence}

    def entity_remove(self, name: str) -> dict[str, Any]:
        removed = self.entity_registry.remove(name)
        return {"ok": True, "removed": removed, "name": name}

    def entity_stats(self) -> dict[str, Any]:
        return {"ok": True, **self.entity_registry.stats()}

    def entity_detect(self, text: str) -> dict[str, Any]:
        result = detect_and_register(text, registry_path=str(self.workspace_root))
        return {"ok": True, **result}

    def spellcheck(self, text: str) -> dict[str, Any]:
        corrected = spellcheck_with_registry(text, registry_path=str(self.workspace_root))
        changed = corrected != text
        return {"ok": True, "corrected": corrected, "original": text, "changed": changed}

    def palace_startup_context(self, max_tokens: int = 200) -> dict[str, Any]:
        context = self.loader.startup_context(max_tokens=max_tokens)
        return {"ok": True, **context}

    def palace_extract(self, text: str) -> dict[str, Any]:
        extracted = self.extractor.extract_all(text)
        return {"ok": True, "text_length": len(text), **extracted}

    def palace_compress(self, texts: list[tuple[str, str]], query: str | None = None) -> dict[str, Any]:
        index = self.compressor.compress_batch(texts)
        stats = self.compressor.stats(index)
        result: dict[str, Any] = {"ok": True, "compressed_count": len(index.compressed), "stats": stats}
        if query:
            results = self.compressor.search(query, index, limit=10)
            result["search_results"] = [
                {"id": cm.id, "keywords": cm.keywords, "dense_text": cm.dense_text, "compression_ratio": cm.compression_ratio}
                for cm in results
            ]
        return result

    # ── Phase 2: BM25 Hybrid Search ──────────────────────────────────────

    def search_query(
        self, query: str, wing: str | None = None, room: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """BM25+keyword hybrid search across all drawers."""
        return {"ok": True, **_search_sqlite(str(self.db_path), query, wing=wing, room=room, limit=limit)}

    def search_similar(self, drawer_id: str, wing: str | None = None, limit: int = 5, threshold: float = 0.2) -> dict[str, Any]:
        """Find drawers similar to a given drawer (Jaccard)."""
        return {"ok": True, **_find_similar_drawers(str(self.db_path), drawer_id, wing=wing, limit=limit, threshold=threshold)}

    # ── Phase 3: Deduplication ───────────────────────────────────────────

    def dedup(self, wing: str | None = None, threshold: float = 0.7, dry_run: bool = True) -> dict[str, Any]:
        """Run deduplication scan on drawers."""
        return {"ok": True, **deduplicate(str(self.db_path), wing=wing, threshold=threshold, dry_run=dry_run)}

    # ── Phase 4: Hallways ────────────────────────────────────────────────

    def hallways_build(self, wing: str | None = None, min_strength: float = 0.02) -> dict[str, Any]:
        """Build/rebuild hallways from drawer entity co-occurrence."""
        return {"ok": True, **_build_hallways(str(self.db_path), wing=wing, min_strength=min_strength)}

    def hallways_list(self, wing: str | None = None, entity: str | None = None, min_strength: float = 0.0, limit: int = 50) -> dict[str, Any]:
        """List hallways with optional filters."""
        return {"ok": True, **_list_hallways(str(self.db_path), wing=wing, entity=entity, min_strength=min_strength, limit=limit)}

    def hallways_find_path(self, entity_a: str, entity_b: str, wing: str | None = None, max_hops: int = 4) -> dict[str, Any]:
        """Find connection path between two entities through hallways."""
        return {"ok": True, **_find_path(str(self.db_path), entity_a, entity_b, wing=wing, max_hops=max_hops)}

    # ── Phase 4b: Knowledge Graph ────────────────────────────────────────

    def kg_add_entity(self, name: str, kind: str = "unknown") -> dict[str, Any]:
        return {"ok": True, **self.knowledge_graph.add_entity(name, kind)}

    def kg_get_entity(self, name: str) -> dict[str, Any]:
        entity = self.knowledge_graph.get_entity(name)
        if entity is None:
            return {"ok": False, "error": f"Entity not found: {name}"}
        return {"ok": True, **entity}

    def kg_list_entities(self, kind: str | None = None, limit: int = 100) -> dict[str, Any]:
        entities = self.knowledge_graph.list_entities(kind=kind, limit=limit)
        return {"ok": True, "entities": entities, "count": len(entities)}

    def kg_add_relationship(
        self, source: str, target: str, rel_type: str, strength: float = 1.0,
        valid_from: str | None = None, valid_until: str | None = None,
        source_drawer_id: str | None = None,
    ) -> dict[str, Any]:
        return {"ok": True, **self.knowledge_graph.add_relationship(
            source, target, rel_type, strength=strength,
            valid_from=valid_from, valid_until=valid_until, source_drawer_id=source_drawer_id,
        )}

    def kg_query_entity(
        self, name: str, direction: str = "both", rel_type: str | None = None,
        valid_at: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        return {"ok": True, **self.knowledge_graph.query_entity(
            name, direction=direction, rel_type=rel_type, valid_at=valid_at, limit=limit,
        )}

    def kg_add_fact(
        self, subject: str, predicate: str, obj: str, confidence: float = 1.0,
        valid_from: str | None = None, valid_until: str | None = None,
    ) -> dict[str, Any]:
        return {"ok": True, **self.knowledge_graph.add_fact(
            subject, predicate, obj, confidence=confidence,
            valid_from=valid_from, valid_until=valid_until,
        )}

    def kg_query_facts(
        self, subject: str | None = None, predicate: str | None = None, obj: str | None = None,
        valid_at: str | None = None, min_confidence: float = 0.0, limit: int = 50,
    ) -> dict[str, Any]:
        facts = self.knowledge_graph.query_facts(
            subject=subject, predicate=predicate, obj=obj,
            valid_at=valid_at, min_confidence=min_confidence, limit=limit,
        )
        return {"ok": True, "facts": facts, "count": len(facts)}

    def kg_stats(self) -> dict[str, Any]:
        return {"ok": True, **self.knowledge_graph.stats()}

    # ── Phase 5: Fact Checker ────────────────────────────────────────────

    def fact_check(self, text: str) -> dict[str, Any]:
        result = fact_check(text, kg=self.knowledge_graph, registry=self.entity_registry)
        return {"ok": True, **result}


# ── MCP tool descriptors ────────────────────────────────────────────────────
MEMPALACE_TOOLS = [
    # ── Palace spatial / core ────────────────────────────────────────────────
    {
        "name": "super_memory_palace_search",
        "description": "Search memories within spatial scope (wing/room/hall)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "wing": {"type": "string", "description": "Filter by palace wing"},
                "room": {"type": "string", "description": "Filter by room"},
                "hall": {"type": "string", "description": "Filter by hall"},
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
                "layer": {"type": "integer", "minimum": 1, "maximum": 4},
                "query": {"type": "string"},
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "hall": {"type": "string"},
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
        "inputSchema": {"type": "object", "properties": {"wing": {"type": "string"}}, "required": []},
    },
    {
        "name": "super_memory_palace_halls",
        "description": "List palace halls, optionally filtered by wing/room",
        "inputSchema": {"type": "object", "properties": {"wing": {"type": "string"}, "room": {"type": "string"}}, "required": []},
    },
    {
        "name": "super_memory_palace_drawers",
        "description": "List palace drawers with optional spatial filters",
        "inputSchema": {
            "type": "object",
            "properties": {"wing": {"type": "string"}, "room": {"type": "string"}, "hall": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50}},
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
        "inputSchema": {"type": "object", "properties": {"max_tokens": {"type": "integer", "minimum": 50, "maximum": 500, "default": 200}}, "required": []},
    },
    {
        "name": "super_memory_palace_extract",
        "description": "Extract entities, concepts, domains, and relationships from text",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    },

    # ── Phase 1: Entity Registry ─────────────────────────────────────────────
    {"name": "super_memory_entity_list", "description": "List all registered entities optionally filtered by kind", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": []}},
    {"name": "super_memory_entity_lookup", "description": "Look up entity by name with person-vs-common-word disambiguation", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "context": {"type": "string", "default": ""}}, "required": ["name"]}},
    {"name": "super_memory_entity_add", "description": "Register a new entity (person, project, agent)", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "kind": {"type": "string", "default": "person"}, "confidence": {"type": "number", "default": 1.0, "minimum": 0, "maximum": 1}, "aliases": {"type": "array", "items": {"type": "string"}}}, "required": ["name"]}},
    {"name": "super_memory_entity_remove", "description": "Remove an entity from the registry", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "super_memory_entity_stats", "description": "Get entity registry statistics", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "super_memory_entity_detect", "description": "Scan text for entities and auto-register high-confidence detections", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "super_memory_spellcheck", "description": "Spellcheck text, preserving technical terms, known entities, URLs, and code", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},

    # ── Phase 2: BM25 Hybrid Search ──────────────────────────────────────────
    {
        "name": "super_memory_search_query",
        "description": "BM25+keyword hybrid search across all drawers in the palace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "wing": {"type": "string", "description": "Optional wing filter"},
                "room": {"type": "string", "description": "Optional room filter"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "super_memory_search_similar",
        "description": "Find drawers similar to a given drawer using Jaccard token similarity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "drawer_id": {"type": "string", "description": "Reference drawer ID"},
                "wing": {"type": "string", "description": "Optional wing filter"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
                "threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.2},
            },
            "required": ["drawer_id"],
        },
    },

    # ── Phase 3: Deduplication ───────────────────────────────────────────────
    {
        "name": "super_memory_dedup",
        "description": "Detect and remove near-duplicate drawers using Jaccard similarity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string", "description": "Optional wing filter"},
                "threshold": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.7, "description": "Jaccard similarity threshold"},
                "dry_run": {"type": "boolean", "default": True, "description": "Preview only, no deletion"},
            },
            "required": [],
        },
    },

    # ── Phase 4: Hallways ────────────────────────────────────────────────────
    {
        "name": "super_memory_hallways_build",
        "description": "Build/rebuild entity-to-entity hallways from drawer co-occurrence",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string", "description": "Optional wing filter"},
                "min_strength": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.02},
            },
            "required": [],
        },
    },
    {
        "name": "super_memory_hallways_list",
        "description": "List entity-to-entity hallways with optional filters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string"},
                "entity": {"type": "string"},
                "min_strength": {"type": "number", "default": 0.0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "super_memory_hallways_find_path",
        "description": "Find shortest connection path between two entities through hallways",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_a": {"type": "string"},
                "entity_b": {"type": "string"},
                "wing": {"type": "string"},
                "max_hops": {"type": "integer", "minimum": 1, "maximum": 10, "default": 4},
            },
            "required": ["entity_a", "entity_b"],
        },
    },

    # ── Phase 4b: Knowledge Graph ────────────────────────────────────────────
    {"name": "super_memory_kg_add_entity", "description": "Add/update an entity node in the knowledge graph", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "kind": {"type": "string", "default": "unknown"}}, "required": ["name"]}},
    {"name": "super_memory_kg_get_entity", "description": "Get entity details from knowledge graph", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "super_memory_kg_list_entities", "description": "List all knowledge graph entities optionally filtered by kind", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "limit": {"type": "integer", "default": 100}}, "required": []}},
    {"name": "super_memory_kg_add_relationship", "description": "Add a typed relationship edge with temporal validity and provenance", "inputSchema": {"type": "object", "properties": {"source": {"type": "string"}, "target": {"type": "string"}, "rel_type": {"type": "string"}, "strength": {"type": "number", "default": 1.0}, "valid_from": {"type": "string"}, "valid_until": {"type": "string"}, "source_drawer_id": {"type": "string"}}, "required": ["source", "target", "rel_type"]}},
    {"name": "super_memory_kg_query_entity", "description": "Query all relationships for an entity with time filtering and traversal direction", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "direction": {"type": "string", "default": "both"}, "rel_type": {"type": "string"}, "valid_at": {"type": "string"}, "limit": {"type": "integer", "default": 50}}, "required": ["name"]}},
    {"name": "super_memory_kg_add_fact", "description": "Add a fact triple (subject, predicate, object) with confidence", "inputSchema": {"type": "object", "properties": {"subject": {"type": "string"}, "predicate": {"type": "string"}, "obj": {"type": "string"}, "confidence": {"type": "number", "default": 1.0}, "valid_from": {"type": "string"}, "valid_until": {"type": "string"}}, "required": ["subject", "predicate", "obj"]}},
    {"name": "super_memory_kg_query_facts", "description": "Query facts with optional time and confidence filters", "inputSchema": {"type": "object", "properties": {"subject": {"type": "string"}, "predicate": {"type": "string"}, "obj": {"type": "string"}, "valid_at": {"type": "string"}, "min_confidence": {"type": "number", "default": 0.0}, "limit": {"type": "integer", "default": 50}}, "required": []}},
    {"name": "super_memory_kg_stats", "description": "Get knowledge graph statistics (entities, relationships, facts)", "inputSchema": {"type": "object", "properties": {}, "required": []}},

    # ── Phase 5: Fact Checker ────────────────────────────────────────────────
    {
        "name": "super_memory_fact_check",
        "description": "Verify text statement against knowledge graph: detect similar_name, relationship_mismatch, temporal_conflict",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to fact-check"}},
            "required": ["text"],
        },
    },
]
