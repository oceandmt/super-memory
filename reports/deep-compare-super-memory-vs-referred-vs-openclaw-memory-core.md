# Deep Research + Review + Compare: Super-Memory vs Referred-Memory vs OpenClaw Memory-Core

**Date:** 2026-06-22  
**Author:** Lucas (agent)  
**Scope:** Full architectural deep-research, deep-review, deep-compare giữa 3 hệ thống memory.  
**Target:** Phân tích 3 projects, đề xuất optimization cho super-memory-github.

---

## 1️⃣ Tổng Quan Kiến Trúc

| Dimension | **Super-Memory v1.7.4** | **Referred-Memory** | **OpenClaw Memory-Core v2026.6.1** |
|-----------|:---:|:---:|:---:|
| **Language** | Python (163 src files) | Python (1,047 src files) | TypeScript (bundled dist/) |
| **Upstream versions** | Self-contained | Neural-Memory v4.58 + Honcho v3.0.9 + MemPalace v3.4.1 | Built-in, per-agent SQLite |
| **Memory model** | **4-layer canonical-first** 🏆 | 3 independent libraries | Flat markdown (MEMORY.md + daily/) |
| **Cross-agent** | ✅ **5 methods, unique** | ❌ Not designed | ❌ Single-agent only |
| **Cross-session** | ✅ Handoff + Archive | ⚠️ Honcho partial | ⚠️ Via plugin |
| **Cognitive graph** | ✅ 5.4K neurons, 12.4K synapses | ✅ Full 441-file engine | ❌ No graph |
| **OpenClaw plugin** | ✅ Slot adapter | ❌ Not integrated | N/A (builtin) |
| **Multi-backend vector** | ❌ SQLite-only | ✅ Chroma/Qdrant/PGVector | ❌ SQLite-only |
| **CJK support** | ❌ No | ❌ No | ✅ **Trigram FTS5** |
| **Active memory** | ❌ No | ❌ No | ✅ **Plugin** |
| **Agent isolation** | ❌ Single DB | ✅ Per-session DB | ✅ **Per-agent DB** |
| **Hypotheses/Predict** | ⚠️ 2 hyps / 0 preds | ✅ Full engine | ❌ No |
| **Dream consolidation** | ❌ Missing | ✅ **Full dreamer** | ❌ No |
| **Handoff bundles** | ✅ **8 methods, unique** | ❌ No | ❌ No |
| **Telemetry/Metrics** | ❌ No | ✅ Sentry + Prometheus | ❌ No |
| **Codebase index** | ⚠️ Basic | ✅ **Full symbol index** | ❌ No |
| **Backups** | ❌ No | ✅ Automated | ❌ No |
| **Webhook support** | ❌ No | ✅ Yes | ❌ No |
| **MCP Server** | ✅ stdio + HTTP | ✅ MemPalace has | ✅ Native |

---

## 2️⃣ Codebase Scale Comparison

```
Super-Memory (v1.7.4)                  Referred-Memory (3 upstreams)
┌─────────────────────────────┐        ┌───────────────────────────────────┐
│ super_memory/               │        │ neural-memory (v4.58.0)          │
│ ├── 17 core .py files       │        │ ├── 441 source files             │
│ ├── honcho/       6 files   │        │ ├── engine/   (42 files)         │
│ ├── mempalace/   17 files   │        │ ├── core/     (14 files)         │
│ ├── handlers/     8 files   │        │ ├── cli/      (28 files)         │
│ ├── bridge.py    (175 funcs)│        │ ├── cache/    (6 files)          │
│ ├── scripts/      2 files   │        │ ├── sync/     (6 files)          │
│ ├── docs/        38 files   │        │ └── 423 scripts/benchmarks       │
│ └── ~163 total .py files    │        │                                   │
└─────────────────────────────┘        │ honcho (v3.0.9)                  │
                                       │ ├── 120 source files             │
OpenClaw Memory-Core (v2026.6.1)       │ ├── crud/     (7 files)          │
┌─────────────────────────────┐        │ ├── llm/      (14 files)         │
│ TypeScript (bundled dist/)  │        │ ├── deriver/  (async queue)      │
│ Per-agent SQLite DB         │        │ ├── dreamer/  (dream engine)     │
│ FTS5 + BM25 + vector search │        │ ├── dialectic/(peer model)      │
│ Active memory plugin        │        │ └── telemetry/(Sentry+Prom)     │
│ 9 embedding providers       │        │                                   │
└─────────────────────────────┘        │ mempalace (v3.4.1)               │
                                       │ ├── 63 core source files         │
                                       │ ├── 5 backends (Chroma/Qdrant/   │
                                       │ │   PGVector/SQLite-exact/Sidecar)│
                                       │ ├── hooks/ CLI/ integrations     │
                                       │ ├── 63 tests                     │
                                       │ └── 5 AI IDE plugins             │
                                       └───────────────────────────────────┘
```

---

## 3️⃣ Super-Memory UNIQUE MOATS (Không Đối Thủ)

### Moat #1: Canonical-first 4-layer Save Architecture 🏆
```
Save Flow:
  user_input → workspace_markdown (canonical truth, append-only)
             → mempalace       (structured spatial memory)
             → honcho          (conversational events)
             → neural_memory   (associative graph + semantic)
             → graph_projection (cognitive fiber projection)
```
- **Không hệ thống nào khác** có cơ chế 4-layer đồng thời
- `require_canonical_first=true`: nếu markdown fail, toàn bộ downstream bị skip
- Workspace markdown append-only → không bao giờ mất dữ liệu gốc

### Moat #2: Cross-agent Memory Sharing 🏆
```
Methods: 5 unique tools
├── cross_agent_recall()       — FTS5-first + LIKE fallback search across agents
├── cross_agent_compare()       — Compare knowledge between 2 agents on a topic
├── cross_agent_summary()       — Per-agent memory/event activity summary
├── agent_belief_report()       — Claims held by agent on a topic
└── cross_agent_honcho_ask()    — Search honcho events by observer agent
```
- Referred-Memory: ❌ Không có khái niệm multi-agent
- OpenClaw Core: ❌ Single-agent design

### Moat #3: Handoff Bundles 🏆
```
Methods: 8 tools
├── create_handoff()              — Create agent handoff bundle
├── get_handoff()                 — Retrieve handoff by ID
├── list_handoffs()               — List handoffs with filters
├── complete_handoff_with_outcome() — Record completion + artifacts
├── update_handoff_status()       — Update lifecycle status
├── auto_handoff_on_spawn()       — Auto-create handoff on sub-agent spawn
├── delegation_handoff()          — Create delegation bundle
└── load_current_handoff()        — Load latest open handoff
```
- Referred-Memory: ❌ Không có handoff mechanism
- OpenClaw Core: ❌ Không có handoff mechanism

### Moat #4: Handler-per-tool Registry 🏆
```
163 handler functions, O(1) dictionary lookup
201 MCP tools (admin profile)
12 class dispatchers covering 82+ additional tools
```
- Mỗi tool là 1 function riêng: `handler_map["super_memory_remember"] = fn`
- Không cần if-else chain
- Dễ dàng thêm/bớt tool mà không ảnh hưởng đến registry

### Moat #5: OpenClaw Slot Adapter 🏆
```
Replace memory-core through slot mechanism:
$super_memory_memory_search → intercepts native memory_search
$super_memory_memory_get    → intercepts native memory_get
3 profiles: safe (parallel), admin (all tools), exclusive (full slot)
```

---

## 4️⃣ Referred-Memory Advantages (Super-Memory Có Thể Học Hỏi)

### 4.1 Từ Neural-Memory v4.58.0

| # | Tính năng | Mô tả | Super-Memory hiện tại | Priority |
|---|-----------|-------|----------------------|:--------:|
| 1 | **Cognitive workflow đầy đủ** | Hypothesis → Predictions → Evidence → Verify | 2 hypotheses, **0 predictions, 0 evidence** | **P0** |
| 2 | **Dream consolidation engine** | Surprisal scoring + dream scheduler + specialists | ❌ Hoàn toàn missing | **P0** |
| 3 | **Cluster-based dedup** | Jaccard similarity + tf-idf clustering | Content_hash exact match (~94 hash-duplicates) | P1 |
| 4 | **Multi-backend vector** | Chroma/Qdrant/PGVector abstraction layer | SQLite-only (sqlite-vec) | P1 |
| 5 | **Brain evolution tracking** | Maturity scores, plasticity, coherence tracking | ❌ Missing | P2 |
| 6 | **Brain store** | Community brain sharing (.brain files) | ❌ Missing | P2 |
| 7 | **Synaptic pruning** | Weight decay + stale synapse cleanup (configurable) | 12,456 synapses, no decay | P2 |
| 8 | **Codebase indexing** | Full symbol/import/relationship extraction | ⚠️ Basic scan only | P2 |
| 9 | **Hypothesis schema evolution** | SUPERSEDES chain with version history | Single-shot only | P2 |
| 10 | **Spaced repetition** | Leitner 5-box review system | ✅ Already implemented | - |

### 4.2 Từ Honcho v3.0.9

| # | Tính năng | Mô tả | Priority |
|---|-----------|-------|:--------:|
| 11 | **Async enrichment deriver** | Non-blocking queue cho post-save enrichment | P2 |
| 12 | **Multi-LLM backend** | Anthropic, Gemini, OpenAI registry pattern | P2 |
| 13 | **Webhook support** | Event-driven notifications khi memory thay đổi | P3 |
| 14 | **Telemetry/Metrics** | Sentry error tracking + Prometheus metrics | P3 |
| 15 | **Dream tree structures** | RP-tree, LSH, CoverTree for similarity search | P2 |

### 4.3 Từ MemPalace v3.4.1

| # | Tính năng | Mô tả | Priority |
|---|-----------|-------|:--------:|
| 16 | **Conversation mining** | Auto-extract memories từ raw chat logs (FTS5 + entity) | **P1** |
| 17 | **Backend abstraction** | 5 vector backends với registry pattern | P1 |
| 18 | **Plugin integrations** | Claude, Cursor, Codex, Antigravity hooks | P2 |
| 19 | **Backup/Repair tools** | Automated backup, repair, migration utilities | P3 |
| 20 | **i18n support** | Multi-language UI/CLI | P3 |

### 4.4 Từ OpenClaw Memory-Core v2026.6.1

| # | Tính năng | Mô tả | Priority |
|---|-----------|-------|:--------:|
| 21 | **CJK trigram FTS5** | `tokenize=trigram` cho Chinese/Japanese/Korean | **P2** |
| 22 | **Active memory plugin** | Pre-reply context injection sub-agent | P2 |
| 23 | **Per-agent SQLite isolation** | Mỗi agent có database riêng | P3 |
| 24 | **9 embedding providers** | Bedrock, DeepInfra, Gemini, GitHub Copilot, Local, Mistral, Ollama, OpenAI, Voyage | P2 |
| 25 | **QMD sidecar support** | External search sidecar (BM25 + vector + reranking) | P3 |

---

## 5️⃣ TOP 10 Optimization Recommendations

```
Priority: P0=Critical  P1=High  P2=Medium  P3=Low
Effort:   🟢=Days  🟡=Weeks  🔴=Months
Impact:   ⭐⭐⭐=Transformative ⭐⭐=Significant ⭐=Incremental
```

| # | Prio | Effort | Impact | Recommendation | Current State | Target State |
|:--:|:----:|:------:|:------:|----------------|---------------|--------------|
| 1 | **P0** | 🟢 | ⭐⭐⭐ | **Activate cognitive workflow** — Wire hypothesis_create → prediction_create → evidence_add → verify_prediction into maintenance_run() auto-cycle | 2 hypotheses, **0 predictions, 0 evidence** | Full auto hypothesis→predict→evidence→verify cycle |
| 2 | **P0** | 🔴 | ⭐⭐⭐ | **Dream consolidation engine** — Surprisal-based dreaming during idle. Merge with current maintenance/sleep cycle. Reference Neural-Memory v4.58 dreamer/ | ❌ Hoàn toàn missing | Rest consolidation + forgetting curve + surprisal pruning |
| 3 | **P1** | 🟡 | ⭐⭐ | **Conversation mining** — Auto-extract memories từ raw Honcho events. Dùng MemPalace v3.4.1 convo_miner.py pattern (FTS5 pattern matching + entity extraction) | ❌ No auto-extraction | Auto memory creation from chat logs |
| 4 | **P1** | 🟡 | ⭐⭐ | **Cluster-based dedup** — Jaccard/tf-idf clustering thay vì content_hash exact match. ~94 hash-duplicate rows trong DB hiện tại | Content hash exact only | Semantic clustering with configurable threshold |
| 5 | **P1** | 🔴 | ⭐⭐⭐ | **Multi-backend vector storage** — Chroma/Qdrant/PGVector abstraction + registry pattern. Tham khảo MemPalace backends/ | SQLite-only (sqlite-vec) | Production-grade vector search with multiple backends |
| 6 | **P2** | 🟢 | ⭐ | **CJK trigram FTS5** — Add `tokenize=trigram` cho FTS5 tables. Quan trọng cho Vietnamese/Chinese/Japanese/Korean users | ❌ No CJK support | Multi-language FTS5 search |
| 7 | **P2** | 🟡 | ⭐⭐ | **Async enrichment deriver** — Queue-based post-save entity extraction + summarization + relation detection. Non-blocking pipeline | Synchronous save only | Non-blocking enrichment pipeline |
| 8 | **P2** | 🟡 | ⭐ | **Synaptic pruning with weight decay** — Implement decay algorithm cho 12,456 synapses. Configurable thresholds + dry-run mode | No decay, no pruning | Configurable weight-based pruning |
| 9 | **P3** | 🟡 | ⭐ | **Telemetry/Metrics dashboard** — Prometheus counters per tool + usage dashboard + error tracking | ❌ None | Per-tool usage, latency, error rates |
| 10 | **P3** | 🟡 | ⭐ | **Per-agent DB isolation** — Optional split per-agent SQLite databases. Improve concurrency for multi-agent deployments | Single shared DB | Multi-agent concurrency with isolation |

---

## 6️⃣ Impact vs Effort Matrix

```
Effort →
  🔴 High     [Dream Engine]          [Multi-Backend Vector]
              ⭐⭐⭐                    ⭐⭐⭐
  
  🟡 Medium   [Conversation Mining]   [Async Enrichment Deriver]
              ⭐⭐                     ⭐⭐
              [Cluster-based Dedup]   [10+ embedding providers]
              ⭐⭐                     ⭐⭐
  
  🟢 Low      [Cognitive Workflow]    [CJK Trigram FTS5]
              ⭐⭐⭐                    ⭐
              [Active Memory Plugin]  [Per-agent isolation]
              ⭐⭐                     ⭐
              
              🟢 Low Impact            ⭐⭐ High Impact
                                                   Impact →
```

**Recommendations by quadrant:**

| Quadrant | Recommendation | Action |
|----------|---------------|--------|
| 🔴 High Effort + ⭐⭐⭐ High Impact | Dream engine + Multi-backend vector | **Plan** — Roadmap items |
| 🟡 Med Effort + ⭐⭐ Med-High Impact | Conversation mining + Cluster dedup + Async deriver | **Do next** — Sprint items |
| 🟢 Low Effort + ⭐⭐⭐ High Impact | Cognitive workflow activation | **Do now** — This week |
| 🟢 Low Effort + ⭐ Low Impact | CJK FTS5 + Per-agent isolation | **Nice to have** |

---

## 7️⃣ So Sánh Chi Tiết Tools Mapping

| MCP Tool Category | Super-Memory | Referred-Memory | OpenClaw Core |
|-------------------|:------------:|:---------------:|:-------------:|
| Basic CRUD | ✅ remember/recall | ✅ | ✅ memory_set/get |
| Search | ✅ memory_search (FTS5+LIKE) | ✅ semantic/BM25 | ✅ Hybrid (BM25+vector) |
| Cross-agent | ✅ **5 methods** | ❌ | ❌ |
| Cross-session | ✅ **4 methods** | ⚠️ Honcho only | ⚠️ Via plugin |
| Handoff | ✅ **8 methods** | ❌ | ❌ |
| Hypotheses | ⚠️ 2 unconnected (tools exist) | ✅ Full engine | ❌ |
| Predictions | ❌ 0 used (tools exist) | ✅ Full engine | ❌ |
| Evidence | ❌ 0 (tools exist) | ✅ Full engine | ❌ |
| Dream | ❌ | ✅ Dreamer (trees, scheduler) | ❌ |
| Graph recall | ✅ Spreading activation | ✅ Full graph traversal | ❌ |
| Codebase index | ⚠️ Basic scan | ✅ Full symbol/import/relation | ❌ |
| Backup | ❌ | ✅ Automated (Telegram) | ❌ |
| CJK search | ❌ | ❌ | ✅ Trigram FTS5 |
| Active memory | ❌ | ❌ | ✅ Plugin |
| Telemetry | ❌ | ✅ Sentry + Prometheus | ❌ |
| Multi-LLM | ❌ (Ollama only) | ✅ Anthropic/Gemini/OpenAI | ❌ |
| Multi-backend | ❌ (SQLite-only) | ✅ Chroma/Qdrant/PGVector | ❌ (SQLite-only) |
| Webhook | ❌ | ✅ Yes | ❌ |
| Per-agent isolation | ❌ (shared DB) | ✅ Per-session DB | ✅ Per-agent DB |

---

## 8️⃣ Lộ Trình Thực Thi

### 🟢 Ngay bây giờ (P0, Low Effort)
```
1. Activate cognitive workflow
   - Add auto-cycle vào maintenance_run()
   - hypothesis_create → prediction_create → evidence_add → verify_prediction
   - 0 dòng code mới, chỉ wiring
```

### 🟡 Tuần này (P1, Medium Effort)
```
2. Conversation mining
   - Port/extract convo_miner.py pattern từ MemPalace v3.4.1
   - Auto-extract memories từ Honcho events
   
3. Cluster-based dedup
   - Thay content_hash exact match bằng Jaccard/tf-idf clustering
   - Giảm ~94+ hash-duplicate rows
```

### 🟡🔴 Tháng này (P1-P2)
```
4. Dream engine architecture
   - Tham khảo Neural-Memory v4.58 dreamer/surprisal
   - Merge với maintenance/sleep cycle hiện tại
   
5. CJK trigram FTS5
   - Thêm tokenizer=trigram cho FTS5 tables
   - Enable Vietnamese/Chinese/Japanese search
```

### 🟡 Quý này (P2-P3)
```
6. Async enrichment deriver
7. Multi-backend vector storage
8. Synaptic pruning with weight decay
9. Telemetry/Metrics dashboard
10. Per-agent DB isolation
```

---

## 9️⃣ Appendices

### A. Methodology
- Source code analysis of all 3 projects
- Live system diagnostics (super-memory DB: 1,536 memories, 5,456 neurons, 12,456 synapses)
- Real data audit (cross-layer health, quality metrics, agent activity)
- Architecture documentation review

### B. Data Sources
| Source | Path |
|--------|------|
| Super-Memory | `/home/oceandmt/.openclaw/workspace/projects/super-memory-github/` |
| Referred-Memory | `/home/oceandmt/.openclaw/workspace/projects/referred-memory/` |
| OpenClaw Memory-Core | `/home/oceandmt/.npm-global/lib/node_modules/openclaw/docs/concepts/` |
| Super-Memory DB | `/home/oceandmt/.openclaw/workspace/data/super-memory.sqlite3` |

### C. Key Files Referenced
- `super-memory-github/super_memory/bridge.py` — 175 functions
- `super-memory-github/super_memory/reports.py` — session_health, memory_pollution_report
- `referred-memory/neural-memory/src/neural_memory/engine/` — 42 files (cognitive, dream, etc.)
- `referred-memory/honcho/src/` — 120 files (crud, deriver, dreamer, dialectic)
- `referred-memory/mempalace/mempalace/` — 63 files (backends, searcher, miner)

### D. Live System Metrics (super-memory DB)
```
Memories:    1,536  (workspace_md=721, mempalace=281, honcho=268, neural_memory=270)
Agents:      5      (lucas=1,466, isol=32, alex=18, max=16, test=12)
Types:       event(692), fact(457), context(172), decision(93), insight(72)
Graph:       5,456 neurons, 768 fibers, 12,456 synapses
Hypotheses:  2      (0 predictions, 0 evidence)
Cross-layer: 0 orphans, 0 drift, 0 pending sync
```

---

*Report generated by Lucas (agent) on 2026-06-22. v1.7.4.*
