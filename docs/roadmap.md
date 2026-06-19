# Super Memory: Development Roadmap

> **Current release**: v1.1.2 (Semantic Mode)  
> **Status**: [GitHub](https://github.com/oceandmt/super-memory) • **Last updated**: 2026-06-19

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
- [x] Version bump to v1.1.2, GitHub release with tag

---

## 📋 Phase 2 — Incremental Sync & Offline Resilience

**Goal**: Eliminate full-rebuild requirement and make the system robust to network/machine failures.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Incremental vector index** — Embed only new/changed memories since last index, not all 440 | High | Medium | 📋 |
| **sqlite-vec WAL mode** — Enable `PRAGMA journal_mode=WAL` for concurrent reads during index update (known limitation of vec0 tables) | High | Small | 📋 |
| **Pending sync dashboard** — CLI command to list/show/resolve `pending_canonical_sync` records | Medium | Small | 📋 |
| **Delayed write queue** — Buffer failed Markdown writes in SQLite, retry on next save/timer | Medium | Medium | 📋 |
| **Integrity auto-heal** — `doctor` should auto-fix missing tables, broken indexes, wrong dimension | Medium | Medium | 📋 |
| **Cross-machine database merge** — Merge two `super-memory.sqlite3` databases with conflict resolution | Low | Large | 💡 |

---

## 📋 Phase 3 — Multi-Agent Memory Routing

**Goal**: Route memories automatically to the correct agent/lane without manual tagging.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Context-aware auto-routing** — When saving a memory, detect channel/session context and auto-set `agent_id`, `scope`, `project` | High | Medium | 📋 |
| **Per-agent vector indexes** — Separate sqlite-vec tables (or `agent_id` column filter) for agent-scoped semantic search | High | Medium | 📋 |
| **Memory boundary enforcement** — Agent A should not see Agent B's `agent-local` memories by default | High | Medium | 📋 |
| **Routing rules engine** — Extensible rules (YAML/JSON) defining where a memory type goes based on channel, project, or content | Medium | Medium | 💡 |
| **Shared memory broadcast** — Mark a memory as `scope=SHARED` and push to all agent memories | Medium | Medium | 💡 |

---

## 📋 Phase 4 — Memory Palace 2.0

**Goal**: Make the spatial memory metaphor genuinely powerful for organizing large knowledge.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Auto-extract entities** — From memories, auto-detect entities and place them in correct wing/room/hall | High | Medium | 📋 |
| **Hierarchical entity resolution** — De-duplicate and merge entity aliases across sessions | High | Medium | 📋 |
| **Palace visualization** — Export palace as JSON/HTML/Mermaid for browsing | Medium | Medium | 📋 |
| **Cross-palace links** — Link drawers across different wings/rooms (weak references) | Medium | Small | 📋 |
| **Palace import/export** — Import/export palace subset as portable `.palace.json` | Low | Small | 💡 |

---

## 📋 Phase 5 — Honcho Deep Integration

**Goal**: Fully synchronize Honcho conversation memories with Super Memory layers for richer recall.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Bidirectional Honcho ↔ Markdown sync** — Honcho events → daily notes AND daily notes → Honcho peer model | High | Large | 📋 |
| **Turn embedding + semantic sync** — Each Honcho turn gets embedded and indexed in sqlite-vec | High | Medium | 📋 |
| **Cross-session peer model** — Build a durable peer model across all sessions for a participant | Medium | Medium | 💡 |
| **Honcho event pruning** — Retention policy: keep N days, prune older events to summaries | Medium | Medium | 📋 |
| **Dialectic analysis persistence** — Keep dialectic analysis results as `INISIGHT` type memories | Low | Small | 💡 |

---

## 📋 Phase 6 — Performance & Observability

**Goal**: Understand and optimize query latency, memory usage, and database size.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Query benchmark suite** — `benchmark-cross-agent` extended with recall latency by layer | High | Medium | 📋 |
| **Token budget enforcement** — Respect `max_tokens` consistently across all recall paths (currently partial) | High | Small | 📋 |
| **Database size tracking** — Track `super-memory.sqlite3` and `vectors.sqlite3` growth over time | Medium | Small | 📋 |
| **Caching layer** — In-memory LRU cache for frequent recall queries (e.g., same query within 5 min) | Medium | Medium | 💡 |
| **Query logging** — Log every recall query + result count + latency for analysis | Medium | Small | 📋 |
| **Content compression analytics** — Track compression ratio and quality for compressed memories | Low | Small | 💡 |

---

## 📋 Phase 7 — CLI and DX

**Goal**: Make the CLI pleasant and productive for daily operator use.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Interactive recall** — `super-memory recall` with pagination, fzf-style filtering | High | Medium | 📋 |
| **Auto-completion** — Shell completion for `super-memory` CLI (bash/zsh/fish) | Medium | Small | 📋 |
| **jq-style format filters** — `--format '{{.content}}'` for piping into shell pipelines | Medium | Small | 💡 |
| **Watch mode** — `super-memory status --watch` showing live memory count changes | Low | Small | 💡 |
| **Memory diff** — Compare two memories side-by-side (`super-memory diff <id1> <id2>`) | Low | Medium | 💡 |

---

## 📋 Phase 8 — Testing & Quality Gates

**Goal**: Reliable CI/CD with contract testing.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Unit test suite** — Core modules: `models.py`, `vector.py`, `storage.py` (factored out of `__init__`) | High | Large | 📋 |
| **Integration tests** — Full pipeline: save → index → recall → promote → cleanup | High | Large | 📋 |
| **MCP contract testing** — Verify all 100+ tools advertise correct schemas | High | Medium | 📋 |
| **Cross-layer consistency tests** — Same query across all 4 layers should return no contradicting results | High | Medium | 📋 |
| **Performance regression CI** — Failing benchmark threshold = PR blocked | Medium | Small | 💡 |
| **Test fixtures** — Pre-populated SQLite databases for deterministic test scenarios | Medium | Medium | 📋 |
| **Property-based fuzz testing** — Random save/recall/delete sequences to find edge cases | Low | Large | 💡 |

---

## 💡 Phase 9 — Advanced Cognitive Features

**Goal**: Hypothesis-driven memory with verification, self-correction, and learning.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **LLM summarization** — Compress long memories into stable summaries (requires configurable LLM endpoint) | Medium | Medium | 💡 |
| **Automatic hypothesis generation** — Detect contradiction patterns and auto-create hypotheses | Medium | Large | 💡 |
| **Memory graph visualization** — Export `cognitive_neurons` + `cognitive_synapses` as D3/vis.js | Low | Medium | 💡 |
| **Memory quality scoring** — Score memories by recency, access frequency, trust, and source reliability | Low | Medium | 💡 |
| **Reinforcement learning from usage** — Promote memories that were relevant in past recalls | Low | Large | 💡 |

---

## 💡 Phase 10 — External Integration

**Goal**: Plug into the broader AI ecosystem.

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| **Obsidian vault import** — Import `.md` files from Obsidian vault as memories | Medium | Medium | 💡 |
| **Notion API integration** — Sync database pages as Super Memory records | Low | Large | 💡 |
| **LangChain/LlamaIndex adapter** — Super Memory as a `VectorStore` for LlamaIndex | Medium | Medium | 💡 |
| **REST API documentation** — OpenAPI spec for REST API | Low | Medium | 💡 |
| **PostgreSQL backend** — Experimental `db_backend: postgres` for production deployments | Low | Large | 💡 |

---

## Timeline (Proposed)

```
Q3 2026
├── Phase 2 — Incremental Sync & Offline Resilience  (Aug)
├── Phase 3 — Multi-Agent Memory Routing              (Sep)
└── Phase 4 — Memory Palace 2.0                       (Oct)

Q4 2026
├── Phase 5 — Honcho Deep Integration                  (Nov)
├── Phase 6 — Performance & Observability              (Nov)
├── Phase 7 — CLI and DX                              (Dec)
└── Phase 8 — Testing & Quality Gates                  (Dec)

2027
├── Phase 9 — Advanced Cognitive Features              (Q1)
└── Phase 10 — External Integration                    (Q2)
```

---

## Quick Start For Each Phase

```bash
# After each phase is released:
pip install --upgrade "super-memory[semantic] @ git+https://github.com/oceandmt/super-memory.git@vX.Y.Z"

# Run doctor to validate upgrade
super-memory semantic doctor --config .openclaw/super-memory.yaml

# Reindex vector store
super-memory semantic index --config .openclaw/super-memory.yaml --rebuild
```

---

*Proposed roadmap based on v1.1.2 semantic mode completion. Priorities may shift based on operator feedback and upstream OpenClaw changes.*
