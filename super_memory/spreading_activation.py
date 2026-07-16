"""Spreading activation algorithm for memory retrieval.

Ported from neural-memory v4.58.0 engine/activation.py.
Synchronous version adapted for super-memory's non-async graph storage.
"""

from __future__ import annotations

__all__ = [
    "ActivationTrace", "ActivationResult", "ActivationState",
    "should_stop_spreading", "SpreadingActivation",
]
import heapq
import logging
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("super-memory.activation")

# Role-based multipliers: semantic synapses conduct stronger
_ROLE_MULTIPLIERS: dict[str, float] = {
    "causal": 1.3,
    "sequential": 1.3,
    "reinforcement": 1.2,
    "supersession": 1.1,
    "structural": 1.0,
    "weakening": 0.9,
    "lateral": 0.85,
    "related_to": 0.85,
    "tagged": 0.85,
    "mentions": 0.9,
    "is_type": 1.0,
    "in_project": 1.0,
    "in_scope": 1.0,
    "co_occurs": 0.85,
    "passive": 0.0,
}

_MAX_QUEUE_SIZE = 50_000
_DEFAULT_SYNAPSE_WEIGHT = 0.5


@dataclass
class ActivationTrace:
    new_neurons_per_hop: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    activation_gain_per_hop: dict[int, float] = field(default_factory=lambda: defaultdict(float))
    max_hop_used: int = 0
    max_hop_allowed: int = 0
    stopped_early: bool = False
    stop_reason: str = ""

    @property
    def total_neurons_activated(self) -> int:
        """Return number of activated neurons."""
        return sum(self.new_neurons_per_hop.values())


@dataclass
class ActivationResult:
    neuron_id: str
    activation_level: float
    hop_distance: int
    path: list[str]
    source_anchor: str


@dataclass
class ActivationState:
    neuron_id: str
    level: float
    hops: int
    path: list[str]
    source: str

    def __lt__(self, other: ActivationState) -> bool:
        """Comparison for priority queue ordering."""
        return self.level > other.level


def should_stop_spreading(
    trace: ActivationTrace,
    current_hop: int,
    threshold: float = 0.15,
    min_new_neurons: int = 2,
    grace_hops: int = 1,
) -> tuple[bool, str]:
    if current_hop <= grace_hops:
        return False, ""
    prev_hop = current_hop - 1
    prev_new = trace.new_neurons_per_hop.get(prev_hop, 0)
    if prev_new < min_new_neurons:
        return True, f"hop {prev_hop} added only {prev_new} neurons (min={min_new_neurons})"
    if current_hop >= 2:
        prev_prev_new = trace.new_neurons_per_hop.get(prev_hop - 1, 0)
        if prev_prev_new > 0:
            gain_ratio = prev_new / prev_prev_new
            if gain_ratio < threshold:
                return True, f"gain ratio {gain_ratio:.2f} < {threshold}"
    return False, ""


class SpreadingActivation:
    """Spreading activation algorithm for memory retrieval.

    Starts from anchor neurons and spreads through synapses,
    decaying with distance, to find related memories.
    Uses generation-based visited tracking for O(1) "clear" between searches.
    """

    def __init__(self, db: Any, config: Any) -> None:
        """Initialize SpreadingActivation with DB and config."""
        self._db = db  # SQLite connection or connection factory
        self._config = config
        self._generation = 0
        self._visited_gen: dict[tuple[str, str], int] = {}
        self._TRIM_INTERVAL = 100
        self._TRIM_KEEP_GENERATIONS = 50

    def activate(
        self,
        anchor_neurons: list[str],
        max_hops: int | None = None,
        decay_factor: float = 0.5,
        min_activation: float | None = None,
        anchor_activations: dict[str, float] | None = None,
        scope: set[str] | None = None,
        dim_returns_enabled: bool = True,
        dim_returns_threshold: float = 0.15,
        dim_returns_min_neurons: int = 2,
    ) -> tuple[dict[str, ActivationResult], ActivationTrace]:
        if max_hops is None:
            max_hops = getattr(self._config, "max_spread_hops", 4)
        if min_activation is None:
            min_activation = getattr(self._config, "activation_threshold", 0.05)

        trace = ActivationTrace(max_hop_allowed=max_hops)
        results: dict[str, ActivationResult] = {}
        freq_cache: dict[str, int] = {}
        neighbor_cache: dict[str, list[tuple[dict, dict]]] = {}
        queue: list[ActivationState] = []

        # Seed anchors
        for anchor_id in anchor_neurons:
            initial_level = (anchor_activations or {}).get(anchor_id, 1.0)
            state = ActivationState(anchor_id, initial_level, 0, [anchor_id], anchor_id)
            heapq.heappush(queue, state)
            results[anchor_id] = ActivationResult(anchor_id, initial_level, 0, [anchor_id], anchor_id)
            trace.new_neurons_per_hop[0] += 1
            trace.activation_gain_per_hop[0] += initial_level

        self._generation += 1
        current_gen = self._generation
        if current_gen % self._TRIM_INTERVAL == 0:
            cutoff = current_gen - self._TRIM_KEEP_GENERATIONS
            self._visited_gen = {k: g for k, g in self._visited_gen.items() if g >= cutoff}

        dr_checked_hops: set[int] = set()

        while queue:
            if len(queue) > _MAX_QUEUE_SIZE:
                break
            current = heapq.heappop(queue)

            visit_key = (current.neuron_id, current.source)
            if self._visited_gen.get(visit_key, -1) == current_gen:
                continue
            self._visited_gen[visit_key] = current_gen

            if current.hops >= max_hops:
                continue

            next_hop = current.hops + 1
            if dim_returns_enabled and next_hop not in dr_checked_hops and next_hop >= 2:
                dr_checked_hops.add(next_hop)
                stop, reason = should_stop_spreading(trace, next_hop, dim_returns_threshold, dim_returns_min_neurons)
                if stop:
                    trace.stopped_early = True
                    trace.stop_reason = reason
                    logger.debug("Diminishing returns: stopping at hop %d — %s", next_hop, reason)
                    break

            # Get neighbors
            if current.neuron_id in neighbor_cache:
                neighbors = neighbor_cache[current.neuron_id]
            else:
                neighbors = self._fetch_neighbors(current.neuron_id)
                neighbor_cache[current.neuron_id] = neighbors

            for neighbor_neuron, synapse in neighbors:
                if scope is not None and neighbor_neuron.get("id") not in scope:
                    continue

                # Frequency boost (myelination metaphor)
                freq = freq_cache.get(neighbor_neuron.get("id"), 0)
                freq_factor = 1.0 + min(0.15, 0.05 * math.log1p(freq))
                freq_cache[neighbor_neuron.get("id", "")] = freq + 1

                # Role-based multiplier
                syn_type = synapse.get("type", "")
                role_mult = _ROLE_MULTIPLIERS.get(syn_type, 1.0)
                if role_mult == 0.0:
                    continue

                syn_weight = synapse.get("weight", _DEFAULT_SYNAPSE_WEIGHT)
                new_level = current.level * decay_factor * syn_weight * freq_factor * role_mult

                if new_level < min_activation:
                    continue

                nid = neighbor_neuron.get("id", "")
                new_path = [*current.path, nid]
                hop = current.hops + 1

                existing = results.get(nid)
                if existing is None or new_level > existing.activation_level:
                    if existing is None:
                        trace.new_neurons_per_hop[hop] += 1
                    trace.activation_gain_per_hop[hop] += new_level

                    results[nid] = ActivationResult(nid, new_level, hop, new_path, current.source)
                    trace.max_hop_used = max(trace.max_hop_used, hop)

                new_state = ActivationState(nid, new_level, hop, new_path, current.source)
                heapq.heappush(queue, new_state)

        return results, trace

    def _fetch_neighbors(self, neuron_id: str) -> list[tuple[dict, dict]]:
        """Fetch neighbor neurons and synapses from graph storage."""
        neighbors: list[tuple[dict, dict]] = []
        # NOTE: plain sqlite3.Connection objects are themselves callable on
        # Python 3.14+ (Connection.__call__ exists), so callable(self._db) no
        # longer distinguishes "connection" from "factory function" and used to
        # call the connection itself, raising TypeError (swallowed below,
        # collapsing spreading activation to anchor-only). Check explicitly for
        # a real sqlite3.Connection first.
        if isinstance(self._db, sqlite3.Connection):
            conn = self._db
        elif callable(self._db):
            conn = self._db()
        else:
            conn = self._db
        try:
            syn_cols = {row[1] for row in conn.execute("PRAGMA table_info(cognitive_synapses)").fetchall()}
            relation_expr = "s.relation" if "relation" in syn_cols else "s.synapse_type" if "synapse_type" in syn_cols else "'structural'"
            # Query cognitive_synapses for outgoing edges
            rows = conn.execute(
                "SELECT s.target_neuron_id as nid, s.source_neuron_id as sid, "
                f"{relation_expr} as stype, s.weight, "
                "n.id, n.content, n.kind "
                "FROM cognitive_synapses s "
                "LEFT JOIN cognitive_neurons n ON n.id = s.target_neuron_id "
                "WHERE s.source_neuron_id = ? AND (s.weight IS NULL OR s.weight >= 0.1) "
                "LIMIT 30",
                (neuron_id,),
            ).fetchall()
            for row in rows:
                r = dict(row)
                neighbor = {"id": r.get("nid") or r.get("id", ""), "content": r.get("content", ""), "kind": r.get("kind", "memory")}
                synapse = {"type": r.get("stype", "structural"), "weight": r.get("weight", _DEFAULT_SYNAPSE_WEIGHT)}
                if neighbor.get("id"):
                    neighbors.append((neighbor, synapse))

            # Also incoming edges
            rows2 = conn.execute(
                "SELECT s.source_neuron_id as nid, "
                f"{relation_expr} as stype, s.weight, "
                "n.id, n.content, n.kind "
                "FROM cognitive_synapses s "
                "LEFT JOIN cognitive_neurons n ON n.id = s.source_neuron_id "
                "WHERE s.target_neuron_id = ? AND (s.weight IS NULL OR s.weight >= 0.1) "
                "LIMIT 30",
                (neuron_id,),
            ).fetchall()
            seen_ids = {n.get("id", "") for n, _ in neighbors}
            for row2 in rows2:
                r = dict(row2)
                nid = r.get("nid") or r.get("id", "")
                if nid and nid not in seen_ids:
                    neighbor = {"id": nid, "content": r.get("content", ""), "kind": r.get("kind", "memory")}
                    synapse = {"type": r.get("stype", "structural"), "weight": r.get("weight", _DEFAULT_SYNAPSE_WEIGHT)}
                    neighbors.append((neighbor, synapse))
        except Exception as e:
            logger.error("fetch_neighbors failed for %s: %s", neuron_id, e)
            raise RuntimeError(f"cognitive graph schema/query failure for {neuron_id}: {e}") from e
        return neighbors

    def activate_from_multiple(
        self,
        anchor_sets: list[list[str]],
        max_hops: int | None = None,
        anchor_activations: dict[str, float] | None = None,
        scope: set[str] | None = None,
    ) -> tuple[dict[str, ActivationResult], list[str]]:
        if not anchor_sets:
            return {}, []
        activation_results = []
        for anchors in anchor_sets:
            if not anchors:
                continue
            result, _ = self.activate(anchors, max_hops, anchor_activations=anchor_activations, scope=scope)
            activation_results.append(result)
        if len(activation_results) == 1:
            return activation_results[0], list(activation_results[0].keys())
        intersection = self._find_intersection(activation_results)
        combined: dict[str, ActivationResult] = {}
        for result_set in activation_results:
            for neuron_id, activation in result_set.items():
                existing = combined.get(neuron_id)
                if existing is None:
                    combined[neuron_id] = activation
                else:
                    if neuron_id in intersection:
                        new_level = min(1.0, existing.activation_level + activation.activation_level * 0.5)
                    else:
                        new_level = max(existing.activation_level, activation.activation_level)
                    combined[neuron_id] = ActivationResult(
                        neuron_id=neuron_id, activation_level=new_level,
                        hop_distance=min(existing.hop_distance, activation.hop_distance),
                        path=existing.path if existing.hop_distance <= activation.hop_distance else activation.path,
                        source_anchor=existing.source_anchor,
                    )
        return combined, intersection

    def _find_intersection(self, activation_sets: list[dict[str, ActivationResult]]) -> list[str]:
        appearances: dict[str, int] = defaultdict(int)
        total_activation: dict[str, float] = defaultdict(float)
        for result_set in activation_sets:
            for neuron_id, activation in result_set.items():
                appearances[neuron_id] += 1
                total_activation[neuron_id] += activation.activation_level
        multi = [(nid, total_activation[nid], cnt) for nid, cnt in appearances.items() if cnt > 1]
        multi.sort(key=lambda x: (x[2], x[1]), reverse=True)
        return [n[0] for n in multi]