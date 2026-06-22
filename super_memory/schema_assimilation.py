"""Schema Assimilation — detect and extract schema patterns from memory data.

Analyzes memory content to discover recurring structural patterns
(entity schemas, relationship templates, workflow patterns) and
assimilates them into the cognitive graph as schema neurons.

Inspired by how the brain extracts schemas from repeated experiences.

Phases:
1. **Scan** — analyze memory contents for recurring patterns
2. **Extract** — build schema templates from detected patterns
3. **Register** — store schemas as typed neurons in the graph
4. **Match** — classify new memories against existing schemas
5. **Evolve** — update schemas as new data arrives
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "SchemaAssimilatorConfig", "SchemaAssimilator",
    "SchemaTemplate", "SchemaMatchResult",
    "run_schema_assimilation",
]

logger = logging.getLogger("super-memory.schema_assimilation")


# ── Constants ────────────────────────────────────────────────────────────────

SCHEMA_TYPES = [
    "entity",           # Person, place, thing with attributes
    "relationship",     # A→B connection with semantics
    "workflow",         # Sequential steps or decision tree
    "template",         # Recurring document/message structure
    "pattern",          # Statistical or temporal pattern
    "category",         # Taxonomic grouping
]


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class SchemaAssimilatorConfig:
    """Configuration for schema assimilation.

    Attributes:
        enabled: Set False to disable.
        min_frequency: Min occurrences for a pattern to become a schema.
        min_fields: Min fields/attributes to form an entity schema.
        similarity_threshold: Jaccard similarity to consider a match.
        max_schemas: Max schemas to maintain per type.
        analyze_window_hours: How far back to scan.
        dry_run: If True, report without mutating.
        auto_evolve: Update schemas on new data (True) or require manual.
    """
    enabled: bool = True
    min_frequency: int = 3
    min_fields: int = 2
    similarity_threshold: float = 0.4
    max_schemas: int = 50
    analyze_window_hours: int = 168  # 7 days
    dry_run: bool = False
    auto_evolve: bool = True


# ── Schema Types ─────────────────────────────────────────────────────────────

@dataclass
class SchemaTemplate:
    """A discovered schema template."""
    id: str = ""
    schema_type: str = "pattern"  # entity, relationship, workflow, template, pattern, category
    name: str = ""
    description: str = ""
    fields: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    sample_memory_ids: list[str] = field(default_factory=list)
    frequency: int = 0
    confidence: float = 0.5
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaMatchResult:
    """Result of matching a memory against known schemas."""
    matched: bool = False
    schema_id: str = ""
    schema_name: str = ""
    schema_type: str = ""
    similarity: float = 0.0
    field_overlap: list[str] = field(default_factory=list)
    error: str = ""


# ── Pattern Detectors ────────────────────────────────────────────────────────

def _detect_key_value_patterns(contents: list[str]) -> list[dict[str, Any]]:
    """Detect K=V patterns from memory contents."""
    patterns = []
    for content in contents:
        lines = content.strip().split("\n")
        fields = set()
        for line in lines:
            m = re.match(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*[:=]\s*(.+)$', line)
            if m:
                fields.add(m.group(1).lower())
        if len(fields) >= 2:
            patterns.append({"type": "entity", "fields": sorted(fields), "count": 1})
    return patterns


def _detect_list_patterns(contents: list[str]) -> list[dict[str, Any]]:
    """Detect list/markdown table patterns."""
    patterns = []
    for content in contents:
        lines = content.strip().split("\n")
        # Check for markdown tables
        table_lines = [l for l in lines if "|" in l and "--" not in l]
        if len(table_lines) >= 3:
            headers = [h.strip() for h in table_lines[0].split("|") if h.strip()]
            if len(headers) >= 2:
                patterns.append({
                    "type": "template",
                    "format": "markdown_table",
                    "fields": [h.lower() for h in headers],
                    "count": 1,
                })

        # Check for dash lists with consistent structure
        dash_items = [l for l in lines if l.strip().startswith("- ") or l.strip().startswith("* ")]
        if len(dash_items) >= 3:
            patterns.append({
                "type": "pattern",
                "format": "dash_list",
                "count": len(dash_items),
                "avg_length": sum(len(i) for i in dash_items) / len(dash_items),
            })

    return patterns


def _detect_code_patterns(contents: list[str]) -> list[dict[str, Any]]:
    """Detect code/function/class patterns."""
    patterns = []
    for content in contents:
        # Function definitions
        funcs = re.findall(r'(?:^|\n)\s*(?:def |function |async def |pub (?:fn|async) )(\w+)', content)
        if len(funcs) >= 2:
            patterns.append({
                "type": "workflow",
                "format": "function_definitions",
                "names": funcs[:10],
                "count": len(funcs),
            })

        # Class definitions
        classes = re.findall(r'(?:^|\n)\s*(?:class |struct |interface )(\w+)', content)
        if classes:
            patterns.append({
                "type": "entity",
                "format": "class_definitions",
                "names": classes[:10],
                "count": len(classes),
            })

        # Import statements pattern
        imports = re.findall(r'(?:^|\n)\s*(?:import |from \S+ import )', content)
        if len(imports) >= 3:
            patterns.append({
                "type": "relationship",
                "format": "import_graph",
                "count": len(imports),
            })

    return patterns


def _detect_temporal_patterns(contents: list[str], timestamps: list[str]) -> list[dict[str, Any]]:
    """Detect temporal sequencing patterns."""
    if len(contents) < 3 or len(timestamps) < 3:
        return []

    # Check for daily/weekly patterns in timestamps
    try:
        dates = []
        for ts in timestamps:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            dates.append(dt.date())

        if len(dates) >= 3:
            # Check weekday consistency
            weekday_counts = Counter(d.weekday() for d in dates)
            if max(weekday_counts.values()) >= len(dates) * 0.5:
                return [{
                    "type": "pattern",
                    "format": "temporal_rhythm",
                    "dominant_weekday": weekday_counts.most_common(1)[0][0],
                    "total_events": len(dates),
                }]
    except Exception:
        pass

    return []


# ── Schema Assimilator ───────────────────────────────────────────────────────

class SchemaAssimilator:
    """Main schema assimilation engine."""

    def __init__(
        self,
        store: Any,
        config: SchemaAssimilatorConfig | None = None,
    ):
        self.store = store
        self.config = config or SchemaAssimilatorConfig()

    def run_analysis(self) -> dict[str, Any]:
        """Run full schema analysis cycle.

        Steps:
        1. Scan recent memories for patterns
        2. Build/update schema templates
        3. Register schemas in the store
        4. Return analysis results
        """
        if not self.config.enabled:
            return {"ok": False, "skipped": "schema assimilation disabled"}

        recent = self._get_recent_memories()
        if not recent:
            return {"ok": True, "skipped": "no recent memories", "schemas_found": 0}

        # Extract contents and timestamps
        contents = [r.get("content", "") for r in recent if r.get("content")]
        timestamps = [r.get("created_at", "") for r in recent if r.get("created_at")]

        # Run detectors
        kv_patterns = _detect_key_value_patterns(contents)
        list_patterns = _detect_list_patterns(contents)
        code_patterns = _detect_code_patterns(contents)
        temporal_patterns = _detect_temporal_patterns(contents, timestamps)

        # Merge into schema templates
        schemas = self._merge_patterns("entity", kv_patterns)
        schemas.extend(self._merge_patterns("template", list_patterns))
        schemas.extend(self._merge_patterns("workflow", code_patterns))
        schemas.extend(self._merge_patterns("pattern", temporal_patterns))

        if self.config.dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "schemas_found": len(schemas),
                "schemas": [s.name for s in schemas],
                "patterns_detected": {
                    "kv": len(kv_patterns),
                    "list": len(list_patterns),
                    "code": len(code_patterns),
                    "temporal": len(temporal_patterns),
                },
            }

        # Register schemas
        registered = self._register_schemas(schemas)
        return {
            "ok": True,
            "schemas_found": len(schemas),
            "schemas_registered": registered,
            "patterns_detected": {
                "kv": len(kv_patterns),
                "list": len(list_patterns),
                "code": len(code_patterns),
                "temporal": len(temporal_patterns),
            },
        }

    def _get_recent_memories(self) -> list[dict[str, Any]]:
        """Get recent memories for analysis."""
        try:
            with self.store.connect() as conn:
                cutoff = datetime.now(timezone.utc).isoformat()
                rows = conn.execute(
                    """SELECT id, content, type, tags_json, created_at
                       FROM memories
                       WHERE julianday(?) - julianday(created_at) <= ?
                         AND content IS NOT NULL
                       ORDER BY created_at DESC
                       LIMIT 200""",
                    (cutoff, self.config.analyze_window_hours / 24.0),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.debug("get recent memories failed: %s", e)
            return []

    def _merge_patterns(
        self, schema_type: str, patterns: list[dict[str, Any]],
    ) -> list[SchemaTemplate]:
        """Merge raw patterns into schema templates."""
        # Group similar patterns by field intersection
        merged: dict[str, SchemaTemplate] = {}

        for p in patterns:
            key = p.get("format", p.get("type", "unknown"))
            if key not in merged:
                merged[key] = SchemaTemplate(
                    schema_type=schema_type,
                    name=f"{schema_type}_{key}",
                    description=f"Auto-detected {schema_type} schema: {key}",
                    tags=[schema_type, key],
                    frequency=0,
                )

            t = merged[key]
            t.frequency += p.get("count", 1)

            # Merge fields
            if "fields" in p:
                t.fields = list(set(t.fields + p["fields"]))

            # Update confidence based on frequency
            t.confidence = min(1.0, t.frequency / max(self.config.min_frequency, 1) * 0.3)

        # Filter by minimum frequency
        return [
            t for t in merged.values()
            if t.frequency >= self.config.min_frequency
        ][:self.config.max_schemas]

    def _register_schemas(self, schemas: list[SchemaTemplate]) -> int:
        """Register schema templates in the store as schema neurons."""
        registered = 0
        now = datetime.now(timezone.utc).isoformat()

        try:
            with self.store.connect() as conn:
                for schema in schemas:
                    # Check if similar schema already exists
                    existing = conn.execute(
                        """SELECT id, content FROM cognitive_neurons
                           WHERE content LIKE ?
                           LIMIT 1""",
                        (f"%{schema.name}%",),
                    ).fetchone()

                    if existing:
                        # Update existing schema
                        existing_data = json.loads(existing["content"]) if isinstance(existing["content"], str) else {}
                        existing_data["frequency"] = schema.frequency
                        existing_data["fields"] = schema.fields
                        existing_data["version"] = existing_data.get("version", 1) + 1 if self.config.auto_evolve else existing_data.get("version", 1)
                        conn.execute(
                            "UPDATE cognitive_neurons SET content = ? WHERE id = ?",
                            (json.dumps(existing_data, ensure_ascii=False), existing["id"]),
                        )
                    else:
                        # Create new schema neuron
                        schema_data = {
                            "schema_type": schema.schema_type,
                            "name": schema.name,
                            "description": schema.description,
                            "fields": schema.fields,
                            "tags": schema.tags,
                            "frequency": schema.frequency,
                            "confidence": schema.confidence,
                            "version": 1,
                        }
                        conn.execute(
                            """INSERT INTO cognitive_neurons (content, neuron_type, created_at)
                               VALUES (?, 'schema', ?)""",
                            (json.dumps(schema_data, ensure_ascii=False), now),
                        )
                    registered += 1
                conn.commit()
        except Exception as e:
            logger.debug("register schemas failed: %s", e)

        return registered

    def match_memory(self, content: str) -> SchemaMatchResult:
        """Match a memory against known schemas.

        Returns the best matching schema if similarity exceeds threshold.
        """
        if not content:
            return SchemaMatchResult(error="empty content")

        # Get existing schemas
        try:
            with self.store.connect() as conn:
                rows = conn.execute(
                    "SELECT id, content FROM cognitive_neurons WHERE neuron_type = 'schema'"
                ).fetchall()
        except Exception as e:
            return SchemaMatchResult(error=str(e))

        if not rows:
            return SchemaMatchResult(matched=False, error="no schemas registered")

        best_match: SchemaMatchResult = SchemaMatchResult()
        content_lower = content.lower()
        content_words = set(re.findall(r"\w{3,}", content_lower))

        for r in rows:
            try:
                schema_data = json.loads(r["content"]) if isinstance(r["content"], str) else {}
            except Exception:
                continue

            fields = schema_data.get("fields", [])
            if not fields:
                continue

            # Field overlap
            field_overlap = [f for f in fields if f.lower() in content_lower]
            if not field_overlap:
                continue

            # Compute similarity
            overlap_ratio = len(field_overlap) / max(len(fields), 1)
            schema_words = set(re.findall(r"\w{3,}", schema_data.get("name", "").lower()))
            word_overlap = len(content_words & schema_words) / max(len(content_words | schema_words), 1)

            similarity = max(overlap_ratio, word_overlap)

            if similarity >= self.config.similarity_threshold and similarity > best_match.similarity:
                best_match = SchemaMatchResult(
                    matched=True,
                    schema_id=r["id"],
                    schema_name=schema_data.get("name", ""),
                    schema_type=schema_data.get("schema_type", ""),
                    similarity=similarity,
                    field_overlap=field_overlap,
                )

        return best_match


# ── Convenience entry point ──────────────────────────────────────────────────

def run_schema_assimilation(
    store: Any,
    config: SchemaAssimilatorConfig | None = None,
) -> dict[str, Any]:
    """Run one schema assimilation cycle."""
    assimilator = SchemaAssimilator(store, config)
    return assimilator.run_analysis()
