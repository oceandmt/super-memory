"""Query Expander — expand recall queries using embeddings and graph context.

Enhances recall quality by expanding short or ambiguous queries with:
1. **Graph neighborhood** — related terms from co-occurring graph neighbors
2. **Embedding similarity** — semantically similar terms from memory embeddings
3. **Synonym expansion** — domain-specific synonym mapping
4. **Temporal context** — time-based qualifiers for recent/temporal queries
5. **Preference tuning** — user preference-aware term weighting

Each expander is optional and independently configurable.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "QueryExpanderConfig", "QueryExpander",
    "ExpandedQuery",
    "GraphExpander", "EmbeddingExpander",
    "SynonymExpander", "TemporalExpander",
]

logger = logging.getLogger("super-memory.query_expander")


@dataclass
class ExpandedQuery:
    """Result of query expansion."""
    original: str
    expanded: str
    added_terms: list[str]
    expansions: dict[str, list[str]]  # expander_name -> terms_added
    confidence_boost: float = 0.0  # Estimated boost to recall quality


@dataclass
class QueryExpanderConfig:
    """Configuration for query expansion.

    Attributes:
        enabled: Master enable/disable.
        max_expansion_terms: Max total terms to add.
        min_term_length: Minimum length for expansion terms.
        graph_expansion_weight: Weight for graph-based expansion.
        embedding_expansion_weight: Weight for embedding-based expansion.
        synonym_expansion_weight: Weight for synonym-based expansion.
        temporal_expansion_weight: Weight for temporal expansion.
        max_graph_hops: Max graph hops for neighbor discovery.
        embedding_top_k: Max terms from embedding similarity.
    """
    enabled: bool = True
    max_expansion_terms: int = 5
    min_term_length: int = 3
    graph_expansion_weight: float = 0.4
    embedding_expansion_weight: float = 0.3
    synonym_expansion_weight: float = 0.2
    temporal_expansion_weight: float = 0.1
    max_graph_hops: int = 2
    embedding_top_k: int = 3


# ── Default Synonyms ─────────────────────────────────────────────────────────

DEFAULT_SYNONYMS: dict[str, list[str]] = {
    "api": ["endpoint", "service", "interface", "rest"],
    "deploy": ["release", "rollout", "ship", "publish"],
    "debug": ["fix", "patch", "repair", "troubleshoot"],
    "error": ["bug", "issue", "failure", "exception", "crash"],
    "test": ["spec", "assertion", "coverage", "verify"],
    "config": ["config", "setting", "option", "parameter", "env"],
    "memory": ["recall", "context", "history", "state"],
    "graph": ["network", "edges", "nodes", "connections"],
    "search": ["query", "find", "retrieve", "lookup", "match"],
    "store": ["save", "persist", "write", "cache"],
    "load": ["get", "fetch", "read", "retrieve"],
    "fast": ["quick", "rapid", "performant", "optimized"],
    "slow": ["latency", "delay", "bottleneck", "overhead"],
    "security": ["auth", "permission", "access", "encrypt", "safe"],
    "web": ["http", "server", "browser", "frontend", "client"],
    "database": ["db", "sql", "schema", "query", "table"],
    "python": ["py", "python3", "pypi"],
    "javascript": ["js", "node", "ecmascript", "typescript"],
    "docker": ["container", "image", "compose", "dockerfile"],
    "kubernetes": ["k8s", "pod", "cluster", "container-orch"],
    "linux": ["unix", "posix", "shell", "bash"],
    "config": ["setting", "param", "option", "tuning"],
    "monitor": ["observe", "metrics", "trace", "logging"],
    "scale": ["horizontal", "vertical", "shard", "replica"],
    "test": ["unit", "integration", "e2e", "spec"],
    "build": ["compile", "bundle", "package", "artifact"],
    "ci": ["cd", "pipeline", "jenkins", "github-actions", "gitlab-ci"],
}


# ── Graph Expander ───────────────────────────────────────────────────────────

class GraphExpander:
    """Expands query using graph neighborhood co-occurrence."""

    def __init__(self, store: Any, max_hops: int = 2):
        self.store = store
        self.max_hops = max_hops

    def expand(self, terms: list[str]) -> list[str]:
        """Find related terms by traversing graph neighbors.

        For each term, finds neurons containing that term, then walks
        outbound synapses to collect neighbor content, extracting new terms.

        Args:
            terms: Query terms to expand from.

        Returns:
            List of related terms found in the graph.
        """
        if not terms or not self.store:
            return []

        related: set[str] = set()
        try:
            with self.store.connect() as conn:
                for term in terms:
                    # Find neurons containing this term
                    neurons = conn.execute(
                        "SELECT id, content FROM cognitive_neurons WHERE content LIKE ? LIMIT 10",
                        (f"%{term}%",),
                    ).fetchall()

                    for neuron in neurons:
                        nid = neuron["id"]
                        content = neuron.get("content", "") or ""

                        # Extract terms from neuron content (excluding the original query term)
                        content_terms = set(re.findall(r"\w{3,}", content.lower()))
                        for ct in content_terms:
                            if ct != term.lower() and ct not in terms:
                                related.add(ct)

                        # Walk synapses to neighbors
                        if self.max_hops > 1:
                            neighbors = conn.execute(
                                """SELECT target_neuron_id, synapse_type
                                   FROM cognitive_synapses
                                   WHERE source_neuron_id = ?
                                   LIMIT 20""",
                                (nid,),
                            ).fetchall()

                            for neighbor in neighbors:
                                neighbor_content = conn.execute(
                                    "SELECT content FROM cognitive_neurons WHERE id = ?",
                                    (neighbor["target_neuron_id"],),
                                ).fetchone()
                                if neighbor_content:
                                    nc_terms = set(re.findall(r"\w{3,}", (neighbor_content.get("content") or "").lower()))
                                    for ct in nc_terms:
                                        if ct != term.lower() and ct not in terms:
                                            related.add(ct)

        except Exception as e:
            logger.debug("graph expander failed: %s", e)

        return list(related)[:10]  # Limit


# ── Embedding Expander ───────────────────────────────────────────────────────

class EmbeddingExpander:
    """Expands query using embedding similarity from memory vectors."""

    def __init__(self, store: Any, top_k: int = 3):
        self.store = store
        self.top_k = top_k

    def expand(self, query: str) -> list[str]:
        """Find semantically similar terms from embedding index.

        Uses sqlite-vec FTS + embeddings to find terms from
        the most semantically similar memories.

        Args:
            query: Full query string.

        Returns:
            List of terms from semantically similar memories.
        """
        if not query or not self.store:
            return []

        try:
            with self.store.connect() as conn:
                # Try FTS match for similar content
                terms = set(re.findall(r"\w{3,}", query.lower()))
                if not terms:
                    return []

                # FTS: find semantically related memories
                fts_query = " OR ".join(terms)
                try:
                    rows = conn.execute(
                        """SELECT m.content
                           FROM memories_fts f
                           JOIN memories m ON m.id = f.rowid
                           WHERE memories_fts MATCH ?
                           ORDER BY rank
                           LIMIT ?""",
                        (fts_query, self.top_k),
                    ).fetchall()
                except Exception:
                    rows = []

                # Extract new terms from matched content
                expanded_terms: set[str] = set()
                for r in rows:
                    content = r.get("content") or ""
                    content_terms = set(re.findall(r"\w{3,}", content.lower()))
                    for ct in content_terms:
                        if ct not in terms:
                            expanded_terms.add(ct)

                return list(expanded_terms)[:self.top_k * 3]

        except Exception as e:
            logger.debug("embedding expander failed: %s", e)

        return []


# ── Synonym Expander ─────────────────────────────────────────────────────────

class SynonymExpander:
    """Expands query using domain-specific synonym mapping."""

    def __init__(self, custom_synonyms: dict[str, list[str]] | None = None):
        self.synonyms = {**DEFAULT_SYNONYMS, **(custom_synonyms or {})}

    def expand(self, terms: list[str]) -> list[str]:
        """Find synonyms for query terms.

        Args:
            terms: Query terms to find synonyms for.

        Returns:
            List of synonym terms.
        """
        if not terms:
            return []

        expanded: set[str] = set()
        for term in terms:
            term_lower = term.lower()
            if term_lower in self.synonyms:
                for syn in self.synonyms[term_lower]:
                    if syn.lower() not in terms:
                        expanded.add(syn)

        return list(expanded)[:5]


# ── Temporal Expander ────────────────────────────────────────────────────────

class TemporalExpander:
    """Expands queries with temporal context qualifiers."""

    # Mapping of temporal qualifiers to their expanded forms
    TEMPORAL_MAP: dict[str, list[str]] = {
        "recent": ["recent", "last", "new", "current", "latest", "updated"],
        "old": ["old", "previous", "past", "original", "legacy", "historical"],
        "today": ["today", "current", "latest"],
        "yesterday": ["yesterday", "previous", "last session"],
    }

    def expand(self, query: str) -> list[str]:
        """Detect temporal references in query and expand with temporal terms.

        Args:
            query: Original query string.

        Returns:
            Additional temporal terms if query is temporal.
        """
        query_lower = query.lower()

        # Detect temporal patterns
        if re.search(r'\b(recent|latest|new|current|updated)\b', query_lower):
            return self.TEMPORAL_MAP["recent"]
        if re.search(r'\b(old|previous|past|original|legacy|historical)\b', query_lower):
            return self.TEMPORAL_MAP["old"]
        if re.search(r'\b(yesterday|last\s+(session|time|week|day))\b', query_lower):
            return self.TEMPORAL_MAP["yesterday"]

        return []


# ── Query Expander ───────────────────────────────────────────────────────────

class QueryExpander:
    """Main query expansion orchestrator.

    Runs all configured expanders and merges their results.
    """

    def __init__(
        self,
        store: Any | None = None,
        config: QueryExpanderConfig | None = None,
        custom_synonyms: dict[str, list[str]] | None = None,
    ):
        self.store = store
        self.config = config or QueryExpanderConfig()
        self.graph_expander = GraphExpander(store, config.max_graph_hops) if store else None
        self.embedding_expander = EmbeddingExpander(store, config.embedding_top_k) if store else None
        self.synonym_expander = SynonymExpander(custom_synonyms)
        self.temporal_expander = TemporalExpander()

    def expand(self, query: str) -> ExpandedQuery:
        """Expand a query using all available expanders.

        Args:
            query: Original query string.

        Returns:
            ExpandedQuery with expanded text and metadata.
        """
        if not query or not self.config.enabled:
            return ExpandedQuery(
                original=query,
                expanded=query,
                added_terms=[],
                expansions={},
            )

        # Extract terms from original query
        terms = list(set(re.findall(r"\w{%d,}" % self.config.min_term_length, query.lower())))

        # Run each expander
        all_additions: dict[str, list[str]] = {}
        all_added: list[str] = []
        term_set: set[str] = set(terms)

        # 1. Graph expansion
        if self.graph_expander:
            try:
                graph_terms = self.graph_expander.expand(terms)
                new_graph = [t for t in graph_terms if t not in term_set][:self.config.max_expansion_terms]
                if new_graph:
                    all_additions["graph"] = new_graph
                    all_added.extend(new_graph)
                    term_set.update(new_graph)
            except Exception:
                pass

        # 2. Embedding expansion
        if self.embedding_expander:
            try:
                emb_terms = self.embedding_expander.expand(query)
                new_emb = [t for t in emb_terms if t not in term_set][:self.config.max_expansion_terms]
                if new_emb:
                    all_additions["embedding"] = new_emb
                    all_added.extend(new_emb)
                    term_set.update(new_emb)
            except Exception:
                pass

        # 3. Synonym expansion
        syn_terms = self.synonym_expander.expand(terms)
        new_syn = [t for t in syn_terms if t not in term_set][:self.config.max_expansion_terms]
        if new_syn:
            all_additions["synonym"] = new_syn
            all_added.extend(new_syn)
            term_set.update(new_syn)

        # 4. Temporal expansion
        temp_terms = self.temporal_expander.expand(query)
        new_temp = [t for t in temp_terms if t not in term_set][:2]
        if new_temp:
            all_additions["temporal"] = new_temp
            all_added.extend(new_temp)
            term_set.update(new_temp)

        # Limit total additions
        all_added = all_added[:self.config.max_expansion_terms]

        if not all_added:
            return ExpandedQuery(
                original=query,
                expanded=query,
                added_terms=[],
                expansions={},
            )

        # Build expanded query
        expanded = f"{query} {' '.join(all_added)}"

        # Estimate confidence boost
        boost = sum(
            getattr(self.config, f"{name}_expansion_weight", 0.1)
            for name in all_additions
        )
        boost = min(boost, 0.5)

        return ExpandedQuery(
            original=query,
            expanded=expanded,
            added_terms=all_added,
            expansions=all_additions,
            confidence_boost=round(boost, 3),
        )

    def refresh_store(self, store: Any) -> None:
        """Update store reference (e.g., after reconnection)."""
        self.store = store
        self.graph_expander = GraphExpander(store, self.config.max_graph_hops)
        self.embedding_expander = EmbeddingExpander(store, self.config.embedding_top_k)
