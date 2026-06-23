# Deep Research + Deep Analyse + Deep Compare: Super Memory vs OpenClaw memory-core

**Generated:** 2026-06-23 15:10 ICT  
**Super Memory:** v2.1.0 — Python (36,721 LoC, 171 files, 186 MCP tools)  
**OpenClaw memory-core:** TypeScript (~84,492 LoC, 253 files, 2 MCP tools)  

---

## 1. 🏗 SYSTEM ARCHITECTURE COMPARISON

### Super Memory (Python)

```
┌──────────────────────────────────────────────────────┐
│                   186 MCP Tools                       │
├──────────────────────────────────────────────────────┤
│  bridge.py → MCP Server → 4-Layer Projection         │
│                                                        │
│  Layer 1: workspace_markdown (.md files) ← canonical  │
│  Layer 2: mempalace (spatial drawers)                  │
│  Layer 3: honcho (event log)                           │
│  Layer 4: neural_memory (cognitive encode)             │
│                                                        │
│  Cognitive Graph (5,664 neurons → 13,410 synapses)     │
│  Memory Palace (679 drawers)                           │
│  Honcho Events (915)                                   │
│  Autocomplete Index (158,162 entries)                  │
└──────────────────────────────────────────────────────┘
```

### OpenClaw memory-core (TypeScript — Builtin Backend)

```
┌─────────────────────────────────────────────────────────────┐
│          2 MCP Tools: memory_search, memory_get              │
├─────────────────────────────────────────────────────────────┤
│  index.ts → Plugin Entry (runtime + tool registration)      │
│                                                              │
│  Engine: memory-host-sdk (108 files)                         │
│    ├── FTS Search (sqlite-vec)                               │
│    ├── QMD Search (external binary — Meilisearch-like)      │
│    ├── Hybrid Search (FTS + vector + QMD)                    │
│    ├── Session visibility filtering                          │
│    ├── MMR diversity reranking                               │
│    ├── Temporal decay scoring                                │
│    ├── Embedding providers (8 registered)                    │
│    └── Cooldown + timeout management                         │
│                                                              │
│  Short-term: dreaming reconstruction + promotion             │
│  REMs: Rapid Evidence-based Memories from transcripts        │
│  Flush Planning: token-budget-aware context management       │
│  Watch/Settle: file watcher debouncing                       │
│  Cache: embedding cache + manager state cache                │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 📊 FEATURE MATRIX: Super Memory vs OpenClaw memory-core

### Core Memory Operations

| Feature | Super Memory | memory-core | Gap? |
|---------|-------------|-------------|------|
| **memory_search tool** | ✅ via compat.py (custom format) | ✅ native (standard format) | 🔶 Format mismatch |
| **memory_get tool** | ✅ via compat.py (virtual + file) | ✅ native (canonical .md only) | ⚠️ |
| **Corpus selection** | 4 layers | memory/wiki/all/sessions | 🔶 No "sessions" corpus |
| **Session search** | ❌ No session FTS | ✅ Session transcript indexing | ❌ **MISSING** |
| **File-based memory** | ✅ Canonical .md files | ✅ MEMORY.md + memory/*.md | ✅ Same |
| **Exact path read** | ✅ memory_get_compatible | ✅ memory_get native | ✅ Compat |

### Search & Retrieval

| Feature | Super Memory | memory-core | Gap? |
|---------|-------------|-------------|------|
| **FTS (SQLite FTS5)** | ✅ CJK trigram FTS | ✅ Standard FTS5 | ✅ Both |
| **Vector search** | ✅ sqlite-vec (optional) | ✅ sqlite-vec (optional) | ✅ Both |
| **QMD external search** | ❌ No QMD | ✅ QMD binary support | ❌ **MISSING** |
| **Hybrid search** | ⚠️ Sequential (FTS then vector) | ✅ Hybrid (FTS+vector+QMD) | 🔶 **GAP** |
| **MMR diversity** | ❌ No MMR | ✅ Maximum Marginal Relevance | ❌ **MISSING** |
| **Temporal decay** | ❌ No time penalty | ✅ configurable decay | ❌ **MISSING** |
| **Query expansion** | ✅ semantic synonyms | ✅ query expansion module | ✅ Both |
| **Cooldowns** | ❌ No rate limiting | ✅ 60s cooldown on errors | ❌ **MISSING** |
| **Timeout handling** | ❌ No tool timeout | ✅ 15s deadline + abort | ❌ **MISSING** |

### Embedding Providers

| Feature | Super Memory | memory-core | Gap? |
|---------|-------------|-------------|------|
| **Ollama** | ✅ (env var) | ✅ registered | ✅ Both |
| **OpenAI** | ❌ | ✅ registered | ❌ **MISSING** |
| **Mistral** | ❌ | ✅ registered | ❌ **MISSING** |
| **Voyage** | ❌ | ✅ registered | ❌ **MISSING** |
| **Amazon Bedrock** | ❌ | ✅ registered | ❌ **MISSING** |
| **LM Studio** | ❌ | ✅ registered | ❌ **MISSING** |
| **DeepInfra** | ❌ | ✅ registered | ❌ **MISSING** |
| **Google** | ❌ | ✅ registered | ❌ **MISSING** |
| **sqlite-vec local** | ✅ | ✅ local | ✅ Both |

### Session & Visibility

| Feature | Super Memory | memory-core | Gap? |
|---------|-------------|-------------|------|
| **Session transcript search** | ❌ | ✅ session file indexing | ❌ **MISSING** |
| **Session visibility** | ❌ All results visible | ✅ Per-session access control | ❌ **MISSING** |
| **Session corpus** | ❌ | ✅ `corpus=sessions` filter | ❌ **MISSING** |

### Memory Budget & Flush

| Feature | Super Memory | memory-core | Gap? |
|---------|-------------|-------------|------|
| **Token budget estimation** | ✅ nmem_budget tool | ✅ memory-budget.ts | ✅ Both |
| **Flush plan resolver** | ❌ | ✅ context-aware flush | ❌ **MISSING** |
| **Prompt section builder** | ❌ | ✅ builds memory context | ❌ **MISSING** |

### Short-term Promotion & Dreaming

| Feature | Super Memory | memory-core | Gap? |
|---------|-------------|-------------|------|
| **Short-term audit** | ✅ short_term_audit | ✅ short-term-promotion.ts | ✅ Both |
| **Event→durable promotion** | ✅ short_term_repair | ✅ REM + dreaming | ✅ Both |
| **Dreaming phases** | ✅ 3-phase engine | ✅ 8-phase dreaming | ✅ Both |
| **REM extraction** | ❌ No REM pipeline | ✅ Rapid Evidence-based Memories | ❌ **MISSING** |
| **Narrative generation** | ❌ | ✅ dreaming-narrative.ts | ❌ **MISSING** |

### Infrastructure

| Feature | Super Memory | memory-core | Gap? |
|---------|-------------|-------------|------|
| **File watcher** | ❌ No debouncing | ✅ watch-pressure + watch-settle | ❌ **MISSING** |
| **Cache management** | ✅ activation cache | ✅ embedding + manager cache | ✅ Both |
| **Index identity** | ❌ | ✅ embedding provider tracking | ❌ **MISSING** |
| **Atomic reindex** | ❌ | ✅ manager-atomic-reindex.ts | ❌ **MISSING** |
| **Self-heal** | ❌ | ✅ manager.self-heal-missing | ❌ **MISSING** |
| **CLI** | ✅ typer CLI | ✅ memory status/index/search | ✅ Both |

### Unique to Super Memory (no memory-core equivalent)

| Feature | Description | Count |
|---------|-------------|-------|
| **Cognitive Graph** | 5,664 neurons, 13,410 synapses | ✅ UNIQUE |
| **Memory Palace** | 679 spatial drawers | ✅ UNIQUE |
| **Honcho Peer Modeling** | 915 events | ✅ UNIQUE |
| **Leitner Spaced Repetition** | 5-box system | ✅ UNIQUE |
| **Hypothesis/Prediction Engine** | Bayesian reasoning | ✅ UNIQUE |
| **Cross-Agent Handoffs** | 21 handoff bundles | ✅ UNIQUE |
| **Version Snapshots** | Brain state versioning | ✅ UNIQUE |
| **Agent Isolation** | Per-agent scoping | ✅ UNIQUE |
| **Auto Deep Pipeline** | audit→qualify→debug→improve | ✅ UNIQUE |
| **Quality Gate** | Auto-classify + score | ✅ UNIQUE |
| **Recall Arbitration** | Multi-layer explanation | ✅ UNIQUE |
| **186 MCP Tools** | vs 2 for memory-core | ✅ UNIQUE |

---

## 3. 🔍 GAP ANALYSIS: What Super Memory needs to match memory-core

### P0 — Critical (memory-slot replacement contract)

| # | Feature | Priority | Effort | Description |
|---|---------|----------|--------|-------------|
| 1 | **Standard `memory_search` output** | 🔴 P0 | Medium | Align compat.py output format to match memory-core exactly (path, startLine, endLine, score, textScore, vectorScore, snippet, source, corpus, citation) |
| 2 | **Corpus "sessions" support** | 🔴 P0 | Medium | Index session transcripts in FTS5 and add `corpus="sessions"` filter |
| 3 | **Tool timeout + abort signal** | 🔴 P0 | Small | Add 15s deadline + AbortController pattern to search tools |
| 4 | **Cooldown manager** | 🔴 P0 | Small | Cache unavailable errors with 60s TTL |

### P1 — Search Quality

| # | Feature | Priority | Effort | Description |
|---|---------|----------|--------|-------------|
| 5 | **MMR diversity reranking** | 🟠 P1 | Medium | Implement Maximum Marginal Relevance to diversify top-K results |
| 6 | **Temporal decay scoring** | 🟠 P1 | Small | Apply time-based score decay (older = lower score) |
| 7 | **Hybrid search (FTS+vector)** | 🟠 P1 | Medium | Normalize scores from FTS and vector search, fuse with weighted average |
| 8 | **Session visibility filter** | 🟠 P1 | Medium | Filter search results by session-scope access rules |

### P2 — Embedding Providers

| # | Feature | Priority | Effort | Description |
|---|---------|----------|--------|-------------|
| 9 | **OpenAI embedding** | 🟡 P2 | Small | Add OpenAI embedding adapter |
| 10 | **Mistral embedding** | 🟡 P2 | Small | Add Mistral embedding adapter |
| 11 | **Amazon Bedrock** | 🟡 P2 | Small | Add Bedrock adapter |
| 12 | **LM Studio** | 🟡 P2 | Small | Add LM Studio adapter |
| 13 | **DeepInfra** | 🟡 P2 | Small | Add DeepInfra adapter |
| 14 | **Google embedding** | 🟡 P2 | Small | Add Google adapter |
| 15 | **Voyage embedding** | 🟡 P2 | Small | Add Voyage adapter |
| 16 | **Index identity** | 🟡 P2 | Medium | Track which embedding provider built the index, warn on mismatch |

### P3 — Infrastructure

| # | Feature | Priority | Effort | Description |
|---|---------|----------|--------|-------------|
| 17 | **REM extraction** | 🟢 P3 | Large | Rapid Evidence-based Memories from session transcripts |
| 18 | **File watcher** | 🟢 P3 | Medium | watch-pressure + watch-settle debouncing |
| 19 | **Flush plan resolver** | 🟢 P3 | Medium | Token-budget-aware context flush planning |
| 20 | **Atomic reindex** | 🟢 P3 | Medium | Safe swap of FTS indexes during rebuild |
| 21 | **QMD integration** | 🟢 P3 | Large | External QMD binary search integration |
| 22 | **Self-heal missing identity** | 🟢 P3 | Small | Auto-detect and repair missing embeddings |

---

## 4. 🎯 PROPOSED IMPROVEMENT PLAN

### Phase 1 — Memory-Slot Contract (P0, ~3 days)

```
Week 1:
├─ Day 1: Fix memory_search output format → match memory-core standard
├─ Day 2: Add corpus="sessions" + session transcript FTS indexing
├─ Day 3: Add tool timeout (15s) + cooldown manager (60s)
└─ Verify: memory_slot_contract tests pass
```

**Implementation files to create/modify:**
```python
# super_memory/
#   compat.py          → overhaul memory_search_compatible output format
#   compat_types.py    → NEW: MemorySearchHit standard schema
#   session_index.py   → NEW: session transcript FTS5 indexer
#   cooldown.py        → NEW: tool cooldown manager
#   bridge.py          → add timeout + cooldown to search/recall
```

### Phase 2 — Search Quality (P1, ~4 days)

```
Week 2:
├─ Day 1: MMR diversity reranker
├─ Day 2: Temporal decay scorer
├─ Day 3: Hybrid search (FTS + vector score fusion)
├─ Day 4: Session visibility filter
└─ Verify: recall quality improves 15%+ on benchmarks
```

**Implementation files to create/modify:**
```python
# super_memory/
#   mmr.py             → NEW: Maximum Marginal Relevance reranker
#   temporal_decay.py  → NEW: time-based score decay
#   hybrid_search.py   → NEW: FTS + vector score fusion
#   session_visibility.py → NEW: per-session access control
```

### Phase 3 — Embedding Providers (P2, ~3 days)

```
Week 3:
├─ Day 1: OpenAI + Mistral adapters
├─ Day 2: Amazon Bedrock + LM Studio + DeepInfra
├─ Day 3: Google + Voyage + index identity tracking
└─ Verify: all 8 providers work with `embedding_doctor()`
```

**Implementation files to create/modify:**
```python
# super_memory/
#   embeddings/
#     openai.py        → NEW
#     mistral.py       → NEW
#     bedrock.py       → NEW  
#     lm_studio.py     → NEW
#     deepinfra.py     → NEW
#     google.py        → NEW
#     voyage.py        → NEW
#     registry.py      → NEW: multi-provider registry
#   index_identity.py  → NEW: track which provider built index
```

### Phase 4 — Infrastructure (P3, ~5 days)

```
Week 4:
├─ Day 1: REM extraction pipeline
├─ Day 2: File watcher with debounce
├─ Day 3: Flush plan resolver
├─ Day 4: Atomic reindex
├─ Day 5: QMD integration (optional)
└─ Verify: all infrastructure modules operational
```

---

## 5. 📈 IMPACT ESTIMATE

### After All Phases Complete

| Metric | Before | After (est.) | Improvement |
|--------|--------|-------------|-------------|
| **memory_search format** | Custom | Standard | ✅ Full compat |
| **Search corpora** | 4 (no sessions) | 5 (+ sessions) | ✅ +25% |
| **Search quality** | Basic | Hybrid + MMR + temporal | ✅ +20-30% MAP |
| **Embedding providers** | 2 (Ollama + sqlite-vec) | 9 total | ✅ +350% |
| **Tool robustness** | No timeout/cooldown | 15s timeout + 60s cooldown | ✅ Production-ready |
| **Session search** | ❌ None | ✅ Full FTS | ✅ New capability |
| **File watching** | ❌ | ✅ Debounced | ✅ New capability |
| **REM extraction** | ❌ | ✅ REM pipeline | ✅ New capability |
| **Flush planning** | ❌ | ✅ Token-aware | ✅ New capability |
| **Memory-slot contract** | ⚠️ Partial | ✅ Full | ✅ Can replace builtin |

### LoC Impact

| Phase | New Files | New LoC | Modified Files |
|-------|-----------|---------|----------------|
| **P0: Memory-slot contract** | 3 | ~600 | 2 (compat, bridge) |
| **P1: Search quality** | 4 | ~800 | 1 (recall pipeline) |
| **P2: Embedding providers** | 9 | ~900 | 2 (embedding_doctor) |
| **P3: Infrastructure** | 5 | ~1,200 | 2 (bridge, service) |
| **Total** | **21 new files** | **~3,500 LoC** | **7 modified** |

---

## 6. 🔄 FULL WORKFLOW COMPARISON

### Save Flow

**memory-core:**
```
save(content)
  → write to MEMORY.md or memory/*.md
  → trigger file watcher (watch-pressure)
  → FTS index update (background)
  → vector embedding (background, optional)
  → cache invalidate
```

**Super Memory:**
```
remember(content)
  → normalize_memory_payload()
  → apply_quality_gate()
  → canonical-first: write .md file
  → project to mempalace (spatial drawer)
  → project to honcho (event log)
  → project to neural_memory (cognitive encode)
  → graph: neurons → synapses → fibers
  → autocomplete update
  → conflict detection
```

### Search Flow

**memory-core:**
```
search(query, corpus)
  → check cooldown → if error cached, return early
  → start 15s deadline + abort controller
  → expand query (QMD or built-in)
  → determine corpora: memory + wiki + sessions
  → for each corpus:
      run FTS search (sqlite-vec or sqlite FTS5)
      run vector search (if embeddings available)
      run QMD search (if external binary configured)
      merge results
  → apply temporal decay score penalty
  → apply MMR diversity reranking
  → clamp results by token budget
  → filter by session visibility
  → format with citations
  → record to short-term promotion tracker
  → return results
```

**Super Memory:**
```
recall(query, depth)
  → parse intent (depth?, temporal?, causal?, q?)
  → query expansion (synonyms, CJK trigrams)
  → spreading activation (cognitive graph)
  → multi-layer retrieval (mempalace + honcho + neural_memory)
  → fuse results across layers
  → confidence scoring (trust × fidelity × freshness)
  → rerank by confidence
  → arbitration (explain why layer X won)
  → format with provenance
```

### Dreaming Flow

**memory-core:**
```
dreaming (8 phases):
  1. Session corpus audit
  2. REM extraction from transcripts
  3. Grounded evidence generation
  4. Shadow trial validation
  5. Narrative generation
  6. Markdown compilation
  7. Phase scoring
  8. Promotion to durable
```

**Super Memory:**
```
dream (3 phases):
  1. Insight generation (cross-domain bridges)
  2. Weak tie reinforcement (strengthen graph)
  3. Pattern summary (repetitive content)
```

---

## 7. 🏆 STRATEGIC RECOMMENDATIONS

### Short-term (1 week) — "Become a valid memory-core replacement"

1. **Standardize memory_search output format** in `compat.py` to match memory-core exactly
2. **Add session transcript FTS indexing** (low hanging fruit — session .md files exist)
3. **Add 15s timeout + cooldown** to all search/recall tools
4. **Run memory_slot_contract tests** until green

### Medium-term (2 weeks) — "Exceed memory-core search quality"

5. **Implement MMR diversity reranker** (well-understood algorithm)
6. **Implement temporal decay scoring** (simple date-based penalty)
7. **Build hybrid search** (normalize FTS + vector scores)
8. **Register 6 additional embedding providers**

### Long-term (3-4 weeks) — "Full production readiness"

9. **Build REM extraction pipeline**
10. **Add file watcher with debounce**
11. **Implement flush plan resolver**
12. **Reach zero gap with memory-core** (22 total gaps → 0)

### What NOT to port from memory-core

Some features are already superior in Super Memory and should NOT be changed:

- Do NOT replace cognitive graph — it's unique value
- Do NOT replace Memory Palace — unique architecture
- Do NOT replace Honcho — peer modeling is differentiated
- Do NOT reduce to 2 tools — 186 tools is a strength
- Do NOT remove 4-layer projection — rich storage is better
- Do NOT remove quality gate / recall arbitration — these are differentiators

---

## 8. 📋 CONCLUSION

### Summary

| Dimension | Verdict |
|-----------|---------|
| **Search capability** | Super Memory needs MMR + temporal decay + hybrid to match |
| **Embedding providers** | Super Memory needs 7 more providers (2→9) |
| **Tool robustness** | Super Memory needs timeout + cooldown |
| **Session search** | Super Memory needs session FTS indexing |
| **Infrastructure** | Super Memory needs file watcher + flush plan |
| **cognitive graph** | Super Memory LEADS (no memory-core equivalent) |
| **Spatial memory** | Super Memory LEADS (Memory Palace) |
| **Peer modeling** | Super Memory LEADS (Honcho) |
| **Tool breadth** | Super Memory LEADS (186 vs 2 tools) |
| **Spaced repetition** | Super Memory LEADS (Leitner) |
| **Hypothesis engine** | Super Memory LEADS (Bayesian reasoning) |
| **Architecture depth** | Super Memory LEADS (4-layer + graph) |

### Verdict

> **Super Memory is architecturally superior but has 22 functional gaps vs OpenClaw memory-core.** 
> 
> With ~3,500 LoC of targeted improvements (21 new files, 7 modified), Super Memory can become a **full memory-core replacement** while retaining its unique differentiators. The key is P0: standardizing the search output format and adding session search — the rest builds on that foundation.

### Priority Order

```
P0 🔴  (3 days) → Memory-slot contract compliance
P1 🟠  (4 days) → Search quality (MMR, temporal, hybrid)
P2 🟡  (3 days) → 7 more embedding providers
P3 🟢  (5 days) → REM, watcher, flush plan, atomic reindex
```

---

*Report saved: reports/deep-compare-super-memory-vs-memory-core-20260623.md*
