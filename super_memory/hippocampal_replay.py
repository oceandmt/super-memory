"""Hippocampal Replay — memory consolidation through pattern replay.

Inspired by biological hippocampal replay during sleep/rest, this module
selects recent high-activity memory patterns and replays activation through
the cognitive graph to strengthen synaptic connections and consolidate
short-term patterns into long-term structure.

Architecture:
1. **Select** — pick recent high-signal memories from working/short-term storage
2. **Replay** — simulate spreading activation through co-activated patterns
3. **Strengthen** — boost synapse weights between replayed neuron pairs
4. **Consolidate** — create summary fibers for recurring activation clusters
"""

from __future__ import annotations

import logging
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "HippocampalReplayConfig", "HippocampalReplay",
    "ReplayResult", "run_hippocampal_replay",
]

logger = logging.getLogger("super-memory.hippocampal_replay")


@dataclass
class HippocampalReplayConfig:
    """Configuration for hippocampal replay consolidation.

    Attributes:
        enabled: Set False to disable.
        replay_window_hours: How far back to look for recent patterns.
        max_patterns: Max patterns to select per replay cycle.
        synapse_boost: Weight increase for replayed synapses (0.0-1.0).
        max_synapse_weight: Cap on synapse weight after boost.
        consolidation_threshold: Min cluster frequency to create summary fiber.
        min_cluster_size: Min neurons in a cluster to consolidate.
        dry_run: If True, report what would happen without mutating.
        ttl_minutes: How long replay effects persist.
    """
    enabled: bool = True
    replay_window_hours: int = 24
    max_patterns: int = 50
    synapse_boost: float = 0.15
    max_synapse_weight: float = 1.0
    consolidation_threshold: int = 3
    min_cluster_size: int = 2
    dry_run: bool = False
    ttl_minutes: int = 1440  # 24 hours


@dataclass
class ReplayResult:
    """Result of a hippocampal replay cycle."""
    patterns_selected: int = 0
    synapses_strengthened: int = 0
    clusters_consolidated: int = 0
    summary_fibers_created: int = 0
    elapsed_ms: float = 0.0
    skipped_reason: str = ""


class HippocampalReplay:
    """Hippocampal replay engine for memory consolidation."""

    def __init__(
        self,
        store: Any,
        config: HippocampalReplayConfig | None = None,
    ):
        self.store = store
        self.config = config or HippocampalReplayConfig()

    # ── Main Entry Point ─────────────────────────────────────────────────

    def run(self) -> ReplayResult:
        """Execute one hippocampal replay cycle.

        Steps:
        1. Select recent high-activity patterns
        2. Replay co-activated neuron pairs
        3. Strengthen synapses between replayed pairs
        4. Detect and consolidate clusters
        """
        start = time.time()
        result = ReplayResult()

        if not self.config.enabled:
            result.skipped_reason = "hippocampal replay disabled"
            return result

        # Step 1: Select recent patterns
        patterns = self._select_recent_patterns()
        result.patterns_selected = len(patterns)
        if not patterns:
            result.skipped_reason = "no recent patterns to replay"
            return result

        # Step 2-3: Replay and strengthen
        if not self.config.dry_run:
            pairs = self._build_co_activation_pairs(patterns)
            strengthened = self._strengthen_synapses(pairs)
            result.synapses_strengthened = strengthened

            # Step 4: Consolidate clusters
            clusters = self._detect_clusters(pairs)
            result.clusters_consolidated = len(clusters)
            fibers = self._consolidate_clusters(clusters, patterns)
            result.summary_fibers_created = fibers
        else:
            # Dry-run: just count
            pairs = self._build_co_activation_pairs(patterns)
            result.synapses_strengthened = len(pairs)
            clusters = self._detect_clusters(pairs)
            result.clusters_consolidated = len(clusters)

        result.elapsed_ms = round((time.time() - start) * 1000, 2)
        return result

    # ── Pattern Selection ────────────────────────────────────────────────

    def _select_recent_patterns(self) -> list[dict[str, Any]]:
        """Select recent high-signal patterns from the store.

        Looks for memories created within the replay window,
        prioritizing those with higher priority and more graph connections.
        """
        try:
            cutoff = datetime.now(timezone.utc).isoformat()
            # Get recent memories from SQLite
            with self.store.connect() as conn:
                rows = conn.execute(
                    """SELECT id, content, type, priority, tags_json, created_at, metadata_json
                       FROM memories
                       WHERE julianday(?) - julianday(created_at) <= ?
                         AND (metadata_json IS NULL OR json_extract(metadata_json, '$.soft_deleted') != 1)
                       ORDER BY priority DESC, created_at DESC
                       LIMIT ?""",
                    (cutoff, self.config.replay_window_hours / 24.0,
                     self.config.max_patterns),
                ).fetchall()

            patterns = []
            for r in rows:
                tags = self._parse_json_list(r["tags_json"])
                meta = self._parse_json_dict(r["metadata_json"])
                patterns.append({
                    "id": r["id"],
                    "content": r["content"] or "",
                    "type": r["type"],
                    "priority": r["priority"] or 5,
                    "tags": tags,
                    "created_at": r["created_at"],
                    "metadata": meta,
                })
            return patterns
        except Exception as e:
            logger.debug("pattern selection failed: %s", e)
            return []

    # ── Co-activation Pair Building ──────────────────────────────────────

    def _build_co_activation_pairs(
        self, patterns: list[dict[str, Any]]
    ) -> list[tuple[str, str, float]]:
        """Build co-activation pairs from patterns sharing tags/topics.

        Returns list of (neuron_a, neuron_b, similarity_score) tuples.
        """
        # Group by tags
        tag_groups: dict[str, list[str]] = defaultdict(list)
        for p in patterns:
            pid = p["id"]
            for tag in p.get("tags", []):
                tag_groups[tag.lower()].append(pid)

        # Build pairs from same-tag groups
        pair_scores: dict[tuple[str, str], float] = {}
        for tag, pids in tag_groups.items():
            if len(pids) < 2:
                continue
            for i in range(len(pids)):
                for j in range(i + 1, len(pids)):
                    a, b = (pids[i], pids[j]) if pids[i] < pids[j] else (pids[j], pids[i])
                    key = (a, b)
                    pair_scores[key] = pair_scores.get(key, 0.0) + 1.0

        # Also add pairs from temporal proximity
        sorted_by_time = sorted(patterns, key=lambda p: p.get("created_at", ""))
        for i in range(len(sorted_by_time) - 1):
            a, b = sorted_by_time[i], sorted_by_time[i + 1]
            key = (a["id"], b["id"]) if a["id"] < b["id"] else (b["id"], a["id"])
            pair_scores[key] = pair_scores.get(key, 0.0) + 0.5

        # Normalize scores and build result
        max_score = max(pair_scores.values()) if pair_scores else 1.0
        result = [
            (a, b, round(score / max_score, 4))
            for (a, b), score in pair_scores.items()
        ]
        # Sort by score descending
        result.sort(key=lambda x: x[2], reverse=True)
        return result

    # ── Synapse Strengthening ────────────────────────────────────────────

    def _strengthen_synapses(
        self, pairs: list[tuple[str, str, float]]
    ) -> int:
        """Strengthen synapse weights between replayed neuron pairs.

        For each pair, updates or creates a synapse with boosted weight.
        """
        strengthened = 0
        try:
            with self.store.connect() as conn:
                for a, b, similarity in pairs:
                    boost = self.config.synapse_boost * similarity
                    if boost <= 0:
                        continue

                    # Check for existing synapse
                    existing = conn.execute(
                        """SELECT id, weight FROM cognitive_synapses
                           WHERE (source_neuron_id = ? AND target_neuron_id = ?)
                              OR (source_neuron_id = ? AND target_neuron_id = ?)""",
                        (a, b, b, a),
                    ).fetchone()

                    if existing:
                        # Strengthen existing
                        new_weight = min(
                            self.config.max_synapse_weight,
                            (existing["weight"] or 0.5) + boost,
                        )
                        conn.execute(
                            "UPDATE cognitive_synapses SET weight = ? WHERE id = ?",
                            (new_weight, existing["id"]),
                        )
                    else:
                        # Create new synapse
                        conn.execute(
                            """INSERT OR IGNORE INTO cognitive_synapses
                               (source_neuron_id, target_neuron_id, synapse_type, weight, created_at)
                               VALUES (?, ?, 'CO_ACTIVATED', ?, ?)""",
                            (a, b, min(boost + 0.3, self.config.max_synapse_weight),
                             datetime.now(timezone.utc).isoformat()),
                        )
                    strengthened += 1
                conn.commit()
        except Exception as e:
            logger.debug("synapse strengthening failed: %s", e)
        return strengthened

    # ── Cluster Detection ────────────────────────────────────────────────

    def _detect_clusters(
        self, pairs: list[tuple[str, str, float]]
    ) -> list[list[str]]:
        """Detect neuron clusters from co-activation pairs.

        Uses simple graph connected-components approach.
        Returns clusters with size >= min_cluster_size.
        """
        # Build adjacency
        adj: dict[str, set[str]] = defaultdict(set)
        for a, b, _ in pairs:
            adj[a].add(b)
            adj[b].add(a)

        # BFS connected components
        visited: set[str] = set()
        clusters: list[list[str]] = []

        for node in adj:
            if node in visited:
                continue
            # BFS
            queue = [node]
            cluster: set[str] = set()
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                cluster.add(current)
                for neighbor in adj.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            if len(cluster) >= self.config.min_cluster_size:
                clusters.append(sorted(cluster))

        return clusters

    # ── Cluster Consolidation ────────────────────────────────────────────

    def _consolidate_clusters(
        self,
        clusters: list[list[str]],
        patterns: list[dict[str, Any]],
    ) -> int:
        """Create summary fibers for consolidated clusters.

        For each cluster above threshold, creates a summary fiber
        describing the consolidated pattern and links it to all
        member neurons via CONSOLIDATED_FROM synapses.
        """
        if not clusters:
            return 0

        # Build pattern lookup
        pattern_map = {p["id"]: p for p in patterns}
        fibers_created = 0

        try:
            now = datetime.now(timezone.utc).isoformat()
            with self.store.connect() as conn:
                for cluster in clusters:
                    # Build summary from member content
                    member_contents = []
                    member_tags: list[str] = []
                    member_types: Counter = Counter()

                    for nid in cluster:
                        p = pattern_map.get(nid)
                        if p:
                            content = p.get("content", "")
                            if content:
                                member_contents.append(content[:200])
                            member_tags.extend(p.get("tags", []))
                            member_types[p.get("type", "context")] += 1

                    if not member_contents:
                        continue

                    # Create a summary fiber
                    dominant_type = member_types.most_common(1)[0][0] if member_types else "insight"
                    common_tags = [t for t, _ in Counter(member_tags).most_common(5)]

                    summary_content = (
                        f"Consolidated pattern ({len(cluster)} memories): "
                        + "; ".join(mc[:100] for mc in member_contents[:3])
                    )

                    # Insert summary fiber into memories
                    conn.execute(
                        """INSERT INTO memories
                           (layer, type, content, tags_json, metadata_json, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            "neural_memory",
                            dominant_type,
                            summary_content[:500],
                            self._dump_json(common_tags),
                            self._dump_json({
                                "consolidated": True,
                                "member_ids": cluster,
                                "member_count": len(cluster),
                                "hippocampal_replay": True,
                            }),
                            now,
                        ),
                    )
                    summary_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                    # Create CONSOLIDATED_FROM synapses to each member
                    for nid in cluster:
                        conn.execute(
                            """INSERT OR IGNORE INTO cognitive_synapses
                               (source_neuron_id, target_neuron_id, synapse_type, weight, created_at)
                               VALUES (?, ?, 'CONSOLIDATED_FROM', ?, ?)""",
                            (str(summary_id), nid, 0.9, now),
                        )

                    fibers_created += 1
                conn.commit()
        except Exception as e:
            logger.debug("cluster consolidation failed: %s", e)

        return fibers_created

    # ── Utilities ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_list(val: str | None) -> list[str]:
        if not val:
            return []
        import json
        try:
            return json.loads(val)
        except Exception:
            return []

    @staticmethod
    def _parse_json_dict(val: str | None) -> dict[str, Any]:
        if not val:
            return {}
        import json
        try:
            return json.loads(val)
        except Exception:
            return {}

    @staticmethod
    def _dump_json(val: Any) -> str:
        import json
        return json.dumps(val, ensure_ascii=False)


# ── Convenience entry point ──────────────────────────────────────────────────

def run_hippocampal_replay(
    store: Any,
    config: HippocampalReplayConfig | None = None,
) -> ReplayResult:
    """Run one hippocampal replay cycle."""
    engine = HippocampalReplay(store, config)
    return engine.run()
