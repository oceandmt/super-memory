# Super Memory: Development Roadmap

> **Current release**: v2.4.3 (live runtime operations + cron hygiene + layer parity hardening)  
> **Status**: [GitHub](https://github.com/oceandmt/super-memory) • **Last updated**: 2026-07-17

---

## Legend

| Icon | Meaning |
|------|---------|
| ✅ | Done (released) |
| 🏗️ | In progress |
| 📋 | Planned |
| 💡 | Proposed / under evaluation |

---

## ✅ Phase 0 — Foundation (v0.x – v1.0)

- [x] SQLite schema: `memories`, `honcho_events`, `session_archives`, `handoff_bundles`
- [x] Canonical-first layered save: Markdown → MemPalace → Honcho → NeuralMemory
- [x] Graceful Markdown-fail fallback with `pending_canonical_sync`
- [x] MCP server with stdio transport
- [x] Cross-agent recall (`cross_agent_recall`, `cross_agent_compare`, `cross_agent_summary`)
- [x] Cross-session recall (`cross_scope_recall`, `session_archive`, `synthesis`)
- [x] MemPalace spatial memory metaphor (Wings → Rooms → Halls → Drawers)
- [x] Honcho event capture and turn analysis
- [x] Cognitive graph: neurons, synapses, fibers
- [x] OpenClaw plugin integration

## ✅ Phase 1 — Semantic Mode (v1.1.x)

- [x] sqlite-vec virtual table and KNN search
- [x] Ollama embedding integration (`nomic-embed-text`, 768d)
- [x] `VectorStore` abstraction with graceful degradation
- [x] Semantic rerank in `hybrid_recall.cross_scope_recall`
- [x] CLI commands: `semantic doctor`, `semantic index`, `semantic verify`
- [x] Standalone install: `pip install super-memory[semantic]`
- [x] Reference config: `config/examples/super-memory.semantic.yaml`
- [x] Documentation: `docs/semantic-mode.md`

## ✅ Phase 1.x — Quality Gate + Cross-Agent + Self-Training (v2.0 – v2.1.x)

- [x] Quality Gate: auto-classify memory type, extract entities + relations, score quality (0-1)
- [x] Recall Arbitration v2: explainable multi-layer scoring with `why_selected`
- [x] Semantic Taxonomy: 14 relation types (CAUSED_BY, LEADS_TO, CONTRADICTS, SUPERSEDES, etc.)
- [x] Canonical Entity Resolution: alias normalization
- [x] Self-Training: failed recall → regression test JSON + training queue
- [x] Telemetry: `record_event()`, `aggregate_daily()`, `stats()` with 7-day window
- [x] Per-Agent Isolation: `set_agent_rules()`, `isolation_summary()`, `agent_memory_counts()`
- [x] Auto-Complete: prefix-index suggest engine, 17,090 prefixes
- [x] Auto Deep Pipeline: 4-stage pipeline (audit → qualify → debug → improve)
- [x] Dream Engine: weak-tie insight generation
- [x] Memory Lifecycle: Leitner SM-2, tier promotion (HOT/WARM/COLD), compression
- [x] FTS Trigger Fix: stale FTS5 triggers recreated with correct schema
- [x] Forget + Edit Endpoints: soft/hard delete, content/type/priority/tier edit
- [x] MCP Tools: 155 tools (v2.0), expanded to 254 (v2.2)

## ✅ Phase 2 — P0+P2 Modules (v2.2.0)

### P0 — MemoryEnvelope + SourceAdapter + Semantic Closets + Recall v3

- [x] **MemoryEnvelope v1** (`core/envelope.py`): quality/trust/provenance/lifecycle contract
- [x] **SourceAdapter Manifest** (`ingest/__init__.py`): ChatTurnAdapter, FileAdapter, URLAdapter
- [x] **Semantic Closets/Drawers** (`projections/closet.py`): verbatim-preserving pointer layer
- [x] **Recall Arbitration v4/v3** (`recall/__init__.py`): unified scoring with `why_selected`, `layer_votes`
- [x] **Recall Feedback Loop** (`recall/feedback.py`): correction → training case pipeline

### P2 — Drift Repair + Watcher + Citations + Dialectic + Curriculum

- [x] **Projection Drift Repair** (`projections/drift_repair.py`): audit orphan projections + auto-repair
- [x] **Adapter-driven Watcher** (`watcher_adapter.py`): file changes → SourceAdapter ingest
- [x] **Line Citations + Neighbor Expansion** (`recall/line_citations.py`): source-verbatim ±N line context
- [x] **Agentic Dialectic Mode** (`recall/dialectic.py`): deterministic format + LLM-ready synthesis
- [x] **Self-Education Curriculum** (`evals/curriculum.py`): failed recall → training → pytest benchmarks

### SKILLS/

- [x] 8 agent skills: onboarding, basic-usage, quality-ingest, recall-arbitration, cross-agent, auto-deep, self-improve, lifecycle
- [x] Skills ship in `SKILLS/` directory with agent mode mapping

### CI/CD

- [x] CI matrix: Python 3.11 + 3.12, 859/859 local tests
- [x] Hard deps: numpy, cryptography
- [x] Grade A (90/100) qualify, 99.9% canonical compliance
- [x] 254 MCP tools, 17,090 autocomplete prefixes
- [x] Deployment to `release` environment: success

## ✅ Phase 3 — Trust, Dream Quality, Write-Contract Hardening (v2.4.2)

### Recall Quality

- [x] **Source/type-aware trust scoring** (`data_improvement.py::_compute_trust`): raw `openclaw.turn`/`event` captures capped at 0.4 so curated memory always outranks turn-dumps in arbitration; durable types (`doctrine`/`preference`/`blocker`/`lesson`) and curated sources get bonuses.
- [x] **Recall Feedback Loop activated**: `bridge.recall()` now calls `record_recall_event()` on every arbitration pass — the table/API existed since Phase 2 but had zero callers.
- [x] **Injection self-contamination fix** (`sanitize.py`): `is_injection_content` drops on a single high-confidence signature instead of requiring ≥2, closing a leak where a single-mention turn could pollute the canonical store.
- [x] **Semantic-closet hydration fix** (`bridge.py`): fold `drawer_id`/`closet_id` into `metadata` at recall-channel build time instead of falling back to the memory UUID, which produced empty hydrated content for every closet hit.

### Dream Engine Quality

- [x] **Stop persisting token-frequency "insights"**: pattern-summary phase (`dream.py`) reported counts like `"'license' appears in 40 memories"` as `insight` memories with no signal; now reported for observability only, never saved.
- [x] **Shared noise/injection guard** (`_is_dream_noise()`): rejects bridge-insight/pattern candidates whose only shared signal is an ambient token (license, copyright, software...) or that echo prompt-injection text, in both `dream.py` and `dream_engine.py`.

### Write-Contract / Data Integrity

- [x] **`content_hash` gap closed** (`handoff.py`): `complete_handoff_with_outcome` bypassed the canonical save and never computed `content_hash`, leaving NULL-hash rows that silently break hash-based dedup/joins (SQL `NOT IN` NULL trap). Fixed at the write path; all alive rows now carry a full 64-char sha256 hash.
- [x] **Dead embed-job cleanup**: cancelled 274 jobs targeting soft-deleted/orphaned memories (reversible status flip); live embed backlog confirmed at 0.
- [x] **Cron hygiene**: `super-memory-daily-hygiene` extended with dead-embed-job auto-cancel + layer-drift check.
- [x] Regression suite `tests/test_injection_and_hydration_regression.py` (16 tests) locking in all of the above.

---

## ✅ Phase 3.1 — Live Runtime Operations Pack (v2.4.3)

- [x] Live operations runbook: MCP/plugin health, readiness checks, and deep-audit workflow.
- [x] Deep-operations skill: repeatable procedures for audit, hygiene, layer parity repair, and release verification.
- [x] Cron templates: exported daily hygiene/live runtime jobs under `ops/cron/`.
- [x] Deep debug hygiene cleanup: diagnostic artifacts separated from runtime readiness scoring.
- [x] Plugin metadata refreshed to v1.7.3.

---

## 📋 Phase 3 — Incremental Sync & Offline Resilience

**Goal**: Eliminate full-rebuild requirement, robust to network/machine failures.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Incremental vector index** — Embed only new/changed memories since last index | High | Medium | 📋 |
| **sqlite-vec WAL mode** — Enable `PRAGMA journal_mode=WAL` for concurrent reads | High | Small | 📋 |
| **Pending sync dashboard** — CLI to list/show/resolve `pending_canonical_sync` records | Medium | Small | 📋 |
| **Delayed write queue** — Buffer failed Markdown writes, retry on next save | Medium | Medium | 📋 |
| **Integrity auto-heal** — `doctor` auto-fixes missing tables, broken indexes | Medium | Medium | 📋 |
| **Cross-machine database merge** — Merge two databases with conflict resolution | Low | Large | 💡 |

---

## 📋 Phase 4 — Multi-Agent Memory Routing

**Goal**: Route memories automatically to correct agent/lane without manual tagging.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Context-aware auto-routing** — Auto-set `agent_id`, `scope`, `project` from context | High | Medium | 📋 |
| **Per-agent vector indexes** — Agent-scoped semantic search | High | Medium | 📋 |
| **Memory boundary enforcement** — Agent A can't see Agent B's `agent-local` | High | Medium | 📋 |
| **Routing rules engine** — Extensible YAML rules | Medium | Medium | 💡 |
| **Shared memory broadcast** — `scope=SHARED` → push to all agents | Medium | Medium | 💡 |

---

## 📋 Phase 5 — Memory Palace 2.0

**Goal**: Powerful spatial memory metaphor for large knowledge.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Auto-extract entities** — Detect entities, place in correct wing/room/hall | High | Medium | 📋 |
| **Hierarchical entity resolution** — Deduplicate aliases across sessions | High | Medium | 📋 |
| **Palace visualization** — Export as JSON/HTML/Mermaid | Medium | Medium | 📋 |
| **Cross-palace links** — Link drawers across wings/rooms | Medium | Small | 📋 |
| **Palace import/export** — Portable `.palace.json` | Low | Small | 💡 |

---

## 📋 Phase 6 — Honcho Deep Integration

**Goal**: Full sync Honcho conversations with Super Memory layers.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Bidirectional Honcho ↔ Markdown sync** | High | Large | 📋 |
| **Turn embedding + semantic sync** | High | Medium | 📋 |
| **Cross-session peer model** | Medium | Medium | 💡 |
| **Honcho event pruning** — Retention policy | Medium | Medium | 📋 |
| **Dialectic analysis persistence** | Low | Small | 💡 |

---

## 📋 Phase 7 — Performance & Observability

**Goal**: Understand latency, memory usage, database size.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Query benchmark suite** | High | Medium | 📋 |
| **Token budget enforcement** | High | Small | 📋 |
| **Database size tracking** | Medium | Small | 📋 |
| **Caching layer** — In-memory LRU | Medium | Medium | 💡 |
| **Query logging** | Medium | Small | 📋 |
| **Content compression analytics** | Low | Small | 💡 |

---

## 📋 Phase 8 — CLI and DX

**Goal**: Pleasant, productive CLI.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Interactive recall** — Pagination, fzf-style filtering | High | Medium | 📋 |
| **Auto-completion** — Shell completion (bash/zsh/fish) | Medium | Small | 📋 |
| **jq-style format filters** — `--format '{{.content}}'` | Medium | Small | 💡 |
| **Watch mode** — `status --watch` | Low | Small | 💡 |
| **Memory diff** — Diff two memories | Low | Medium | 💡 |

---

## 💡 Phase 9 — Advanced Cognitive Features

**Goal**: Hypothesis-driven memory with verification, self-correction, learning.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **LLM summarization** — Compress long memories | Medium | Medium | 💡 |
| **Automatic hypothesis generation** — Detect contradiction patterns | Medium | Large | 💡 |
| **Memory graph visualization** — D3/vis.js export | Low | Medium | 💡 |
| **Reinforcement learning from usage** | Low | Large | 💡 |

---

## 💡 Phase 10 — External Integration

**Goal**: Plug into the broader AI ecosystem.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Obsidian vault import** | Medium | Medium | 💡 |
| **Notion API integration** | Low | Large | 💡 |
| **LangChain/LlamaIndex adapter** | Medium | Medium | 💡 |
| **OpenAPI spec for REST API** | Low | Medium | 💡 |
| **PostgreSQL backend** | Low | Large | 💡 |

---

## Timeline (Proposed)

```
Q3 2026
├── Phase 3 — Incremental Sync & Offline Resilience  (Aug)
├── Phase 4 — Multi-Agent Memory Routing              (Sep)
└── Phase 5 — Memory Palace 2.0                       (Oct)

Q4 2026
├── Phase 6 — Honcho Deep Integration                  (Nov)
├── Phase 7 — Performance & Observability              (Nov)
├── Phase 8 — CLI and DX                              (Dec)

2027
├── Phase 9 — Advanced Cognitive Features              (Q1)
└── Phase 10 — External Integration                    (Q2)
```

---

## Quick Start For Each Phase

```bash
# After each phase is released:
pip install --upgrade super-memory

# Run doctor to validate upgrade
super-memory doctor --no-benchmark --json-out

# Auto Deep health check
super-memory auto-deep
```

---

*Proposed roadmap based on v2.2.0 completion. Priorities may shift based on operator feedback and upstream OpenClaw changes.*
