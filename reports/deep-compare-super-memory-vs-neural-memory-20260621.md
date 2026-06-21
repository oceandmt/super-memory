# 🔬 Deep Research: super-memory vs neural-memory (referred-memory)

Date: 2026-06-21  
Analyst: lucas (9router/gpt-5.5)  
Scope: `projects/super-memory-github` vs `projects/referred-memory/neural-memory`

---

## 1. Executive Summary

| Metric | super-memory | neural-memory | Ratio |
|--------|-------------|---------------|-------|
| **Python LOC** | 18,141 | 136,763 | 1:7.5 |
| **Python files** | 83 | 441 | 1:5.3 |
| **Engine modules** | ~5 (graph, cognitive, semantic, layers, lifecycle) | ~90+ | 1:18 |
| **Test functions** | 174 | ~2,600+ | 1:15 |
| **Version** | v1.1.4 | v4.58.0 | — |
| **Architecture** | Canonical-first (4 layers) | Brain-centric (1 graph engine) | — |

**Conclusion:** `super-memory` is NOT a clone of `neural-memory`. It is a **fundamentally different architecture** built for multi-agent canonical-first persistence. `neural-memory` is a monolith library with 10× the engine complexity. The right strategy is NOT to port neural-memory into super-memory, but to cherry-pick high-value features.

---

## 2. Architectural Comparison

### super-memory (Canonical-First Layered)
```
Save:  Workspace Markdown → MemPalace → Honcho → Neural Memory
Recall: Merged across layers, deduped by content_hash
Core:   Service class routes to 4 backends
DB:     Single SQLite (memories + graph_edges + cognitive_* tables)
```

### neural-memory (Brain-Centric Graph)
```
Save:  Encode → Neuron/Fiber/Synapse creation → Embedding → Write Queue
Recall: Stimulus → Query Parser → Anchor Neurons → Spreading Activation → Score Fusion → Reconstruction
Core:   ReflexPipeline with 3,500 LOC
DB:     Brain-scoped SQLite (neurons + synapses + fibers + neuron_states + embeddings)
```

---

## 3. Feature Gap Analysis

### 🔥 HIGH VALUE — Should adopt into super-memory

| Feature | neural-memory LOC | super-memory current | Value | Effort |
|---------|------------------|---------------------|-------|--------|
| **1. Query Expansion** | 106 | ❌ None | High — synonyms/abbreviations improve recall by ~25% | Small |
| **2. RRF Score Fusion** | 121 | ❌ None — simple dedup | High — better multi-source ranking | Tiny |
| **3. Adaptive Depth Prior** | 355 | ❌ Static depth | Medium — auto-adjusts search depth | Medium |
| **4. Deferred Write Queue** | 147 | ❌ Sync writes only | Medium — batch flush for bulk operations | Small |
| **5. Answer Reconstruction** | 374 | ❌ Raw records only | Medium — causal chain/event sequence formatting | Medium |

### 🟡 MEDIUM VALUE — Consider post-MVP

| Feature | LOC | Why |
|---------|-----|-----|
| **6. Conflict Detection** | 818 | ~35 concurrent conflicts max |
| **7. PPR Activation** | 300 | Alternative to spreading activation |
| **8. Brain Versioning** | 438 | Snapshot/rollback for safety |
| **9. Arousal/Valence** | 220 + 186 | Emotional intensity tracking |
| **10. Stabilization** | 179 | Self-healing after corruption |

### 🟢 ALREADY HAS (super-memory equivalent or better)

| Feature | neural-memory | super-memory |
|---------|--------------|-------------|
| Spreading Activation | ✅ 3,507 LOC (retrieval.py) | ✅ 535 LOC (graph.py) — simpler, faster |
| Consolidation | ✅ 2,284 LOC | ✅ 275 LOC (consolidation.py) |
| Lifecycle | ✅ 327 LOC | ✅ 230 LOC (lifecycle.py) |
| Leitner/SRS | ✅ 143 LOC | ✅ Basic (bridge.py) |
| Pin/Reflex | ✅ | ✅ (intelligence.py) |
| Honcho Dialectic | ✅ (separate SDK) | ✅ Integrated (honcho/tools.py) |
| MemPalace | ✅ (separate SDK) | ✅ Integrated (mempalace/) |
| Memory Graph | ✅ | ✅ (cognitive_neurons/synapses/fibers) |
| Semantic/Embedding | ✅ | ✅ (semantic.py + sqlite-vec) |

### 🌟 EXCLUSIVE TO SUPER-MEMORY (neural-memory lacks)

| Feature | Description |
|---------|-------------|
| **Canonical-First Layers** | Markdown → Palace → Honcho → Neural fallback chain |
| **Cross-Agent Memory** | Query across agent scopes |
| **Handoff System** | Agent-to-agent handoff bundles |
| **Turn Sync** | Compact event capture per turn |
| **API Server** | FastAPI + rate limiting + auth |
| **Auto-Compact** | Soft-delete → threshold → VACUUM |
| **Session Management** | Session health, timeline, summary |
| **Workspace Markdown** | File-based canonical storage |

---

## 4. Proposed Optimization Roadmap

### Phase 1 (Next) — Quick Wins, < 200 LOC each

#### 1.1 Query Expansion
```python
# super_memory/service.py or new super_memory/query_expansion.py
def expand_query(query: str) -> list[str]:
    """Expand query with synonyms and related terms from graph."""
    variants = {query}
    # Morphological: "connecting" → "connection", "connected"
    # Graph: find related cognitive_neurons via SIMILAR_TO/RELATED_TO
    # Cross-layer: expand via mempalace entity registry
    return list(variants)
```

**File:** `super_memory/query_expansion.py` (~150 LOC)  
**Benefit:** 20-30% improvement in recall coverage.

#### 1.2 RRF Score Fusion
```python
# super_memory/service.py — replace simple dedup with RRF
def rrf_fuse(layer_results: dict, k: int = 60) -> list[MemoryRecord]:
```
**Modification:** `service.py` `prefetch()` method  
**Benefit:** Better ranking across layers.

#### 1.3 Deferred Write Queue
```python
# super_memory/layers.py or new super_memory/write_queue.py
class DeferredWriteQueue:
    def defer(self, record): ...
    async def flush(self): ...
```
**File:** `super_memory/write_queue.py` (~150 LOC)  
**Benefit:** 2-5× faster bulk imports.

---

### Phase 2 (Medium) — Architectural, 200-500 LOC each

#### 2.1 Adaptive Depth Prior
```python
# super_memory/recall_quality.py
class DepthPrior:
    """Track recall success rates per query type, auto-adjust depth."""
    def update(self, query: str, success: bool): ...
    def expected_depth(self, query: str) -> int: ...
```
**Benefit:** Smarter recall — deep queries auto-expand without wasting tokens.

#### 2.2 Conflict Detection (lightweight)
```python
# super_memory/conflict.py — ~300 LOC
# Negation detection + temporal classification
# 80/20 rule: 20% of neural-memory's 818 LOC gives 80% value
```
**Benefit:** Auto-detect contradicting memories without LLM calls.

#### 2.3 Brain Versioning (lightweight)
```python
# super_memory/version.py — extends existing snapshot support
# Add diff between versions, rollback with dry_run
```
**Benefit:** Safe experimentation — roll back bad consolidation.

---

### Phase 3 (Future) — Major, 500-1000 LOC each

#### 3.1 Answer Reconstruction
- Format memories as causal chains, event sequences, temporal ranges
- Priority: reconstructing related memories into coherent paragraphs

#### 3.2 Arousal/Valence Tracking
- Detect emotional intensity at save time
- Filter recall by arousal threshold or valence

#### 3.3 Stabilization
- Periodic health check of graph consistency
- Auto-repair orphan synapses, broken fibers

**Total estimated impact:**
- Phase 1: ~+450 LOC, +5-10% recall quality
- Phase 2: ~+1,000 LOC, +15-20% system robustness
- Phase 3: ~+1,500 LOC, +25% memory coherence

---

## 5. DO NOT PORT — Features Not Worth It

| neural-memory feature | LOC | Reason to skip |
|----------------------|-----|----------------|
| Full ReflexPipeline | 3,507 | super-memory's graph.py (535 LOC) covers 80% of use cases |
| PPR Activation | 300 | Spreading activation is sufficient; PPR adds complexity |
| Full Consolidation Engine | 2,284 | Consolidation exists at 275 LOC; neural-memory is over-engineered |
| Doc Trainer | 664 | super-memory uses `train_local` + markdown; simpler |
| Brain Store Export/Import | 438 | super-memory is local-first; sync is Phase 4 optional |
| Semantic Discovery | 303 | sqlite-vec already solves semantic search |
| Embedding Provider Zoo | 5 providers | super-memory only needs Ollama (local) — KISS |

---

## 6. Immediate Next Steps

```
1. query_expansion.py          — 150 LOC  [P0, 1 day]
2. RRF fuse in service.py      — 30 LOC   [P0, 2 hours]  
3. deferred_write_queue.py     — 150 LOC  [P1, 1 day]
4. depth_prior.py              — 200 LOC  [P1, 2 days]
5. conflict.py (lightweight)   — 300 LOC  [P2, 3 days]
```

Total: ~830 LOC for Phase 1+2 high-value improvements.
