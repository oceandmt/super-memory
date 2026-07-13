"""Storage Mixins — composable behavior mixins for CoreStorage backends.

Provides reusable mixin classes that add specific capabilities to storage
backends without deep inheritance chains. Each mixin handles one concern:

- **TagMixin** — tag filtering, aggregation, dedup
- **LeitnerMixin** — spaced repetition box management
- **PriorityMixin** — priority sorting, boost computation
- **TemporalMixin** — time-window queries, freshness scoring
- **StatsMixin** — aggregated statistics, distributions
- **SearchMixin** — full-text search, hybrid recall delegation
- **GraphMixin** — graph neighbor queries, synapse stats

Usage::

    class MyStore(TagMixin, LeitnerMixin, PriorityMixin, ...):
        ...
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "TagMixin", "LeitnerMixin", "PriorityMixin",
    "TemporalMixin", "StatsMixin", "SearchMixin", "GraphMixin",
]

logger = logging.getLogger("super-memory.storage.mixins")


# ── Tag Mixin ────────────────────────────────────────────────────────────────

class TagMixin:
    """Adds tag-based querying and aggregation to a storage backend.

    Expects self.connect() and tables with tags_json column.
    """

    def get_memories_by_tag(
        self, tag: str, limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get memories containing a specific tag."""
        tag_lower = tag.lower()
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                """SELECT id, layer, content, type, tags_json, priority, created_at
                   FROM memories
                   WHERE LOWER(tags_json) LIKE ?
                   ORDER BY priority DESC, created_at DESC
                   LIMIT ? OFFSET ?""",
                (f"%{tag_lower}%", limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tag_frequencies(self, min_count: int = 1) -> dict[str, int]:
        """Get frequency of all tags across memories."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                "SELECT tags_json FROM memories WHERE tags_json IS NOT NULL"
            ).fetchall()

        counter: Counter = Counter()
        for r in rows:
            tags = self._parse_json_list(r["tags_json"])
            for tag in tags:
                counter[tag.lower()] += 1

        return {tag: count for tag, count in counter.items() if count >= min_count}

    def get_memories_by_tags_all(
        self, tags: list[str], limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get memories matching ALL specified tags."""
        if not tags:
            return []
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                "SELECT id, layer, content, type, tags_json, priority, created_at FROM memories"
            ).fetchall()

        tag_set = {t.lower() for t in tags}
        results = []
        for r in rows:
            mem_tags = {t.lower() for t in self._parse_json_list(r["tags_json"])}
            if tag_set.issubset(mem_tags):
                results.append(dict(r))

        return sorted(results, key=lambda x: x.get("priority", 0) or 0, reverse=True)[:limit]

    def get_memories_by_tags_any(
        self, tags: list[str], limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get memories matching ANY of the specified tags."""
        if not tags:
            return []
        tag_lower = {t.lower() for t in tags}
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                "SELECT id, layer, content, type, tags_json, priority, created_at FROM memories"
            ).fetchall()

        results = []
        for r in rows:
            mem_tags = {t.lower() for t in self._parse_json_list(r["tags_json"])}
            if tag_lower & mem_tags:
                results.append(dict(r))

        return sorted(results, key=lambda x: x.get("priority", 0) or 0, reverse=True)[:limit]

    @staticmethod
    def _parse_json_list(val: Any) -> list[str]:
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val) if isinstance(val, str) else []
        except Exception:
            return []

    @staticmethod
    def _dump_json(val: Any) -> str:
        return json.dumps(val, ensure_ascii=False)


# ── Leitner Mixin ────────────────────────────────────────────────────────────

BOX_INTERVALS: dict[int, int] = {0: 1, 1: 3, 2: 7, 3: 30, 4: 90}


class LeitnerMixin:
    """Adds Leitner spaced repetition query support.

    Expects memories table with leiter_box and next_review columns.
    """

    def get_due_for_review(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get memories due for Leitner review."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                """SELECT id, content, type, leiter_box, next_review, created_at
                   FROM memories
                   WHERE next_review IS NOT NULL AND next_review <= ?
                   ORDER BY leiter_box ASC, next_review ASC
                   LIMIT ?""",
                (now, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_review_distribution(self) -> dict[str, int]:
        """Get distribution of memories across Leitner boxes."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                "SELECT leiter_box, COUNT(*) as c FROM memories GROUP BY leiter_box"
            ).fetchall()
        return {str(r["leiter_box"] or 0): r["c"] for r in rows}

    def get_box_counts(self) -> dict[int, int]:
        """Get count of memories per box keyed by int."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                "SELECT leiter_box, COUNT(*) as c FROM memories GROUP BY leiter_box"
            ).fetchall()
        return {r["leiter_box"] or 0: r["c"] for r in rows}


# ── Priority Mixin ───────────────────────────────────────────────────────────

class PriorityMixin:
    """Adds priority-based sorting and boost computation."""

    def get_high_priority(self, min_priority: int = 7, limit: int = 50) -> list[dict[str, Any]]:
        """Get high-priority memories."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                """SELECT id, layer, content, type, priority, tags_json, created_at
                   FROM memories
                   WHERE (priority IS NOT NULL AND priority >= ?)
                   ORDER BY priority DESC, created_at DESC
                   LIMIT ?""",
                (min_priority, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def compute_priority_boost(self, priority: int | None, base_score: float = 0.5) -> float:
        """Compute a score boost from priority (1-10 scale)."""
        if priority is None or priority <= 0:
            return base_score
        # Priority 5 → 1.0x, Priority 10 → 2.0x
        factor = 1.0 + (priority - 1) * 0.1
        return min(base_score * factor, 1.0)

    def apply_priority_to_results(
        self, results: list[dict[str, Any]], score_key: str = "score",
    ) -> list[dict[str, Any]]:
        """Apply priority boost to result scores in-place."""
        for r in results:
            priority = r.get("priority", r.get("_priority"))
            if priority is not None:
                current = r.get(score_key, 0.5)
                r[score_key] = self.compute_priority_boost(priority, current)
        return results


# ── Temporal Mixin ───────────────────────────────────────────────────────────

class TemporalMixin:
    """Adds time-window queries and freshness scoring."""

    def get_memories_in_window(
        self, start: str, end: str, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get memories created within a time window."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                """SELECT id, layer, content, type, priority, created_at
                   FROM memories
                   WHERE created_at >= ? AND created_at <= ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (start, end, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_memories(self, hours: int = 24, limit: int = 50) -> list[dict[str, Any]]:
        """Get memories from the last N hours."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return self.get_memories_in_window(cutoff, datetime.now(timezone.utc).isoformat(), limit)

    def compute_freshness_score(self, created_at: str | None) -> float:
        """Compute freshness score (0-1) based on age."""
        if not created_at:
            return 0.5
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
            return 1.0 / (1.0 + age_days / 30.0)
        except Exception:
            return 0.5

    def apply_freshness_to_results(
        self, results: list[dict[str, Any]], score_key: str = "score",
        weight: float = 0.15,
    ) -> list[dict[str, Any]]:
        """Blend freshness into result scores."""
        for r in results:
            freshness = self.compute_freshness_score(r.get("created_at"))
            current = r.get(score_key, 0.5)
            r[score_key] = round(current * (1.0 - weight) + freshness * weight, 4)
            r["_freshness"] = freshness
        return results


# ── Stats Mixin ──────────────────────────────────────────────────────────────

class StatsMixin:
    """Adds aggregated statistics and distribution queries."""

    def get_type_distribution(self) -> dict[str, int]:
        """Get count of memories per type."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                "SELECT type, COUNT(*) as c FROM memories WHERE type IS NOT NULL GROUP BY type"
            ).fetchall()
        return {r["type"]: r["c"] for r in rows}

    def get_layer_distribution(self) -> dict[str, int]:
        """Get count of memories per layer."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                "SELECT layer, COUNT(*) as c FROM memories WHERE layer IS NOT NULL GROUP BY layer"
            ).fetchall()
        return {r["layer"]: r["c"] for r in rows}

    def get_daily_creation_counts(self, days: int = 30) -> list[dict[str, Any]]:
        """Get memory creation counts per day for the last N days."""
        with self.connect() as conn:  # type: ignore
            rows = conn.execute(
                """SELECT DATE(created_at) as day, COUNT(*) as count
                   FROM memories
                   WHERE created_at >= DATE('now', ?)
                   GROUP BY DATE(created_at)
                   ORDER BY day DESC""",
                (f"-{days} days",),
            ).fetchall()
        return [{"day": r["day"], "count": r["count"]} for r in rows]

    def get_memory_count(self, where_clause: str | None = None, where_args: list[Any] | None = None) -> int:
        """Count memories matching a WHERE clause."""
        with self.connect() as conn:  # type: ignore
            sql = "SELECT COUNT(*) as c FROM memories"
            if where_clause:
                sql += f" WHERE {where_clause}"
            row = conn.execute(sql, where_args or []).fetchone()
            return row["c"] if row else 0


# ── Search Mixin ─────────────────────────────────────────────────────────────

class SearchMixin:
    """Adds FTS and hybrid search delegation."""

    def fts_search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Full-text search using SQLite FTS5."""
        try:
            with self.connect() as conn:  # type: ignore
                rows = conn.execute(
                    """SELECT m.id, m.layer, m.content, m.type, m.tags_json, m.priority, m.created_at,
                              rank
                       FROM memories_fts f
                       JOIN memories m ON m.rowid = f.rowid
                       WHERE memories_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (query, limit),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.debug("FTS search failed: %s", e)
            return []

    def hybrid_search(
        self, query: str, limit: int = 10,
        semantic_weight: float = 0.5, bm25_weight: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining FTS and semantic scores."""
        # FTS results
        fts_results = self.fts_search(query, limit)
        for r in fts_results:
            r["_fts_score"] = r.get("rank", 1.0) / max(
                max(rr.get("rank", 1.0) for rr in fts_results) if fts_results else 1.0, 1.0
            )

        # Semantic recall delegation
        try:
            from .hybrid_recall import HybridRecall
            from .config import load_config
            cfg = load_config()
            recall = HybridRecall(cfg)
            semantic = recall.cross_scope_recall(query, agent_scope="current", limit=limit)
            semantic_results = semantic.get("results", [])
            for r in semantic_results:
                r["_semantic_score"] = r.get("score", 0.5)
        except Exception:
            semantic_results = []

        # Merge: prefer semantic results, augment with FTS
        seen = set()
        merged = []
        for r in semantic_results:
            nid = r.get("id", r.get("neuron_id"))
            if nid and nid not in seen:
                seen.add(nid)
                merged.append(r)

        for r in fts_results:
            nid = r.get("id", r.get("neuron_id"))
            if nid and nid not in seen:
                seen.add(nid)
                merged.append(r)

        return merged[:limit]


# ── Graph Mixin ──────────────────────────────────────────────────────────────

class GraphMixin:
    """Adds graph neighbor and synapse statistics."""

    def get_neighbors(
        self, neuron_id: str, direction: str = "out", limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get graph neighbors for a neuron."""
        with self.connect() as conn:  # type: ignore
            if direction == "in":
                rows = conn.execute(
                    """SELECT * FROM cognitive_synapses WHERE target_neuron_id = ?
                       ORDER BY weight DESC LIMIT ?""",
                    (neuron_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM cognitive_synapses WHERE source_neuron_id = ?
                       ORDER BY weight DESC LIMIT ?""",
                    (neuron_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_graph_stats(self) -> dict[str, int]:
        """Get graph statistics."""
        with self.connect() as conn:  # type: ignore
            neurons = conn.execute(
                "SELECT COUNT(*) as c FROM cognitive_neurons"
            ).fetchone()["c"]
            synapses = conn.execute(
                "SELECT COUNT(*) as c FROM cognitive_synapses"
            ).fetchone()["c"]
            synapse_types = {
                r["synapse_type"]: r["c"]
                for r in conn.execute(
                    "SELECT synapse_type, COUNT(*) as c FROM cognitive_synapses GROUP BY synapse_type"
                ).fetchall()
            }
        return {
            "neurons": neurons,
            "synapses": synapses,
            "synapse_types": synapse_types,
        }
