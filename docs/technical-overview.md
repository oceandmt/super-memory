# Technical Overview: Super Memory Architecture

> **Version**: 2.2.0  
> **Release**: [v2.3.6 — Trust/Dream/Write-Contract hardening](https://github.com/oceandmt/super-memory/releases/tag/v2.3.6)  
> **License**: MIT

---

## Table of Contents

- [Architecture](#architecture)
- [The Four Memory Layers](#the-four-memory-layers)
- [Semantic Mode (sqlite-vec + Ollama)](#semantic-mode-sqlite-vec--ollama)
- [Cross-Agent & Cross-Session Memory](#cross-agent--cross-session-memory)
- [Workflow and Lifecycle](#workflow-and-lifecycle)
- [MCP Tool Architecture](#mcp-tool-architecture)
- [OpenClaw Integration](#openclaw-integration)
- [Data Flow Diagram](#data-flow-diagram)

---

## Architecture

Super Memory is a **canonical-first, multi-layer hybrid memory system** for AI agents running under [OpenClaw](https://openclaw.ai). It stores, retrieves, and synchronizes memories across four independent layers in a strict priority order.

```
                    ┌──────────────────────────────────────┐
                    │      SuperMemoryService (orchestrator)│
                    └────┬──────┬──────┬──────┬────────────┘
                         │      │      │      │
                    ┌────┘      │      │      └────┐
                    ▼           ▼      ▼            ▼
           ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
           │ Workspace  │ │ MemPalace│ │  Honcho  │ │ NeuralMemory │
           │  Markdown  │ │ (SQLite) │ │ (SQLite) │ │  (SQLite)    │
           │ (Filesystem)│ │          │ │          │ │              │
           └────────────┘ └──────────┘ └──────────┘ └──────────────┘
           Layer 1          Layer 2      Layer 3      Layer 4
           (Canonical)      (Spatial)    (Session)    (Graph)
```

### Design Principles

| Principle | Description |
|-----------|-------------|
| **Canonical-first** | Workspace Markdown is the single source of truth. SQLite layers are mirrors/adapters. |
| **Graceful degradation** | If Markdown write fails, downstream SQLite layers still save with `pending_canonical_sync=True`. |
| **Layer isolation** | Each layer is a pluggable `MemoryBackend` adapter. Add/remove layers without breaking others. |
| **Provenance tracking** | Every memory record carries `content_hash` (SHA-256) for cross-layer drift detection. |
| **Deterministic routing** | No heuristics, no ML gating. Memory routing follows explicit layer order and scope rules. |

---

## The Four Memory Layers

### Layer 1: Workspace Markdown *(Canonical)*

**Backend**: `WorkspaceMarkdownBackend`

The canonical truth layer. Memories are appended to daily notes or category-specific registers on the local filesystem.

- **Daily notes**: `memory/YYYY-MM-DD.md`
- **Long-term**: `MEMORY.md`
- **Registers**: `memory/registers/<category>.md`

```python
# Example: saving a decision memory
record = MemoryRecord(
    content="Decided to switch to sqlite-vec for vector recall",
    type=MemoryType.DECISION,
    scope=MemoryScope.SHARED,
    agent_id="lucas",
    project="super-memory",
    tags=["semantic", "architecture"]
)
service.save(record)
```

### Layer 2: MemPalace *(Spatial/Entity)*

**Backend**: `SQLiteLayerBackend` targeted at `palace_drawers`

A spatial memory metaphor: **Wings → Rooms → Halls → Drawers**. Each drawer contains structured memory items. Suitable for procedural knowledge, entity graphs, and organized reference hierarchies.

```sql
-- Schema: palace_drawers
CREATE TABLE palace_drawers (
    id TEXT PRIMARY KEY,
    wing TEXT, room TEXT, hall TEXT,
    content TEXT,
    tags_json TEXT,
    metadata_json TEXT,
    created_at TEXT
);
```

### Layer 3: Honcho *(Conversational/Session)*

**Backend**: `SQLiteLayerBackend` targeted at `honcho_events`

Stores conversation turn events with full provenance (observer/observed agent, session ID, workspace). Used for analyzing conversations, building peer models, and session timeline synthesis.

### Layer 4: Neural Memory *(Associative/Graph)*

**Backend**: `SQLiteLayerBackend` targeted at `cognitive_*` tables

A cognitive graph of neurons, synapses, fibers, and edges. Supports spreading activation recall, hypothesis/prediction tracking, Leitner spaced repetition, and memory lifecycle management.

```sql
-- Key tables
cognitive_neurons    -- Atomic knowledge units
cognitive_synapses   -- Weighted connections between neurons  
cognitive_fibers     -- Bundled memories (multi-neuron facts)
graph_edges          -- Legacy directed edges for backward compat
```

### Save Order and Fallback

```
1. Workspace Markdown ──┬── success → write SQLite mirror
                        │
                        └── fail → downstream layers save with
                                   pending_canonical_sync=True
2. MemPalace
3. Honcho
4. Neural Memory
```

When Markdown succeeds, a `workspace_markdown` row is **also written to the shared SQLite `memories` table** so all four layers are queryable through one unified SQL interface. This avoids requiring filesystem reads for every recall.

---

## Semantic Mode (sqlite-vec + Ollama)

Introduced in **v1.1.1** (recall integration) and fully packaged in **v1.1.2** (CLI commands, docs, standalone extras).

### Architecture

```
    [Memory Content]                [Query Text]
          │                              │
          ▼                              ▼
    ┌──────────┐                  ┌──────────┐
    │  Ollama  │                  │  Ollama  │
    │  Embed   │◄──── text ──────►│  Embed   │
    │  API     │                  │  API     │
    └────┬─────┘                  └────┬─────┘
         │ vector (768d)              │ vector (768d)
         ▼                            ▼
    ┌───────────────────────────────────────┐
    │         sqlite-vec (vec0)             │
    │  CREATE VIRTUAL TABLE embeddings      │
    │  USING vec0(memory_id TEXT PRIMARY    │
    │               KEY, embedding FLOAT[768]) │
    │                                        │
    │  SELECT memory_id, distance             │
    │  FROM embeddings                        │
    │  WHERE embedding MATCH ?                │
    │  ORDER BY distance                      │
    │  LIMIT ?                                │
    └────────────────┬──────────────────────┘
                     │ (memory_id, distance)
                     ▼
    ┌───────────────────────────────────────┐
    │      HybridRecall.cross_scope_recall  │
    │  1. Search Markdown (TF-IDF)          │
    │  2. Search Honcho events              │
    │  3. Search MemPalace drawers          │
    │  4. Search graph neurons              │
    │  5. Semantic rerank via sqlite-vec    │
    │  6. Dedup + score fusion              │
    │  7. Truncate to max_tokens            │
    └───────────────────────────────────────┘
```

### Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Embed single text | ~50 ms | Ollama `nomic-embed-text`, localhost |
| Insert embedding | ~60 ms | sqlite-vec INSERT OR REPLACE |
| KNN search (437 vecs) | <5 ms | SQL virtual table, full scan |
| Full recall pipeline | ~200 ms | TF-IDF + Honcho + Palace + semantic rerank |
| Batch index (8 docs) | ~500 ms | Parallel embedding requests |

### Key Files

| File | Purpose |
|------|---------|
| `super_memory/vector.py` | `VectorStore` abstraction over sqlite-vec |
| `super_memory/semantic.py` | CLI doctor/index/verify, embedding helpers |
| `super_memory/hybrid_recall.py` | Cross-layer recall orchestration + semantic rerank |
| `config/examples/super-memory.semantic.yaml` | Reference config for semantic mode |
| `docs/semantic-mode.md` | Installation and troubleshooting guide |

---

## Cross-Agent & Cross-Session Memory

### Memory Record Model

Every memory carries precise provenance to enable multi-agent, multi-session routing:

```python
class MemoryRecord(BaseModel):
    id: str           # UUID
    content: str      # The memory text
    type: MemoryType  # fact, decision, preference, todo, blocker, workflow, insight, context, doctrine, lesson, event
    scope: MemoryScope # session, agent-local, shared, project, cross-agent
    agent_id: str     # Which agent owns this: lucas, alex, max, isol
    session_id: str   # Which conversation session
    project: str      # Optional project namespace
    tags: list[str]   # Auto-prefixed with agent/scope/type/project
    source: str       # Provenance string
    trust_score: float # 0.0-1.0
    metadata: dict    # Arbitrary extra fields
```

### Cross-Agent Tools

| Tool | Description |
|------|-------------|
| `cross_agent_recall` | Query memories filtered by `agent_id` + keyword |
| `cross_agent_honcho_ask` | Query Honcho events by observer agent about a peer |
| `cross_agent_summary` | Per-agent memory/Honcho event counts and recency |
| `cross_agent_compare` | Compare two agents' knowledge overlap on a topic |
| `list_agents` | List all unique agent IDs in the database |

### Cross-Session Tools

| Tool | Description |
|------|-------------|
| `cross_scope_recall` | Recall across Markdown + Honcho + MemPalace + Graph, scoped by agent/session |
| `session_archive` | Compressed session timeline summaries |
| `session_timeline` | Session event sequences for analysis |
| `synthesis` | Cross-session evolution and insight extraction |

### Tag Normalization

Tags are auto-prefixed for reliable routing in multi-agent scenarios:

```
agent:lucas    scope:shared    type:decision    project:super-memory
agent:alex     scope:session   type:context
agent:max      scope:agent-local  type:insight
```

---

## Workflow and Lifecycle

### Memory Lifecycle Stages

```
Created ──► Active (default)
  │
  ├──► Superseded (new version replaces old via RESOLVED_BY synapse)
  │
  ├──► Expired (valid_until passed, lifecycle sweep marks expired)
  │
  └──► Deleted (soft delete via metadata.soft_deleted)
```

### Consolidation Pipeline

The `consolidate` action runs a deterministic maintenance sequence:

1. **Prune** — Remove synapses below weight threshold
2. **Merge** — Merge fibers with high Jaccard overlap
3. **Summarize** — Compress verbose fiber chains
4. **Mature** — Increment maturity counter, decay weight
5. **Infer** — Suggest new connections from co-occurrence
6. **Enrich** — Extract concepts, link new entities
7. **Dream** — Simulate missing edge inference
8. **Learn Habits** — Tool usage pattern detection
9. **Dedup** — Remove duplicate content by embedding similarity
10. **Semantic Link** — Cross-entity connection inference
11. **Compress** — Summarize long content into compact form
12. **Process Tool Events** — Ingest tool execution as memory
13. **Detect Drift** — Tag drift clusters for operator review

All consolidation steps are **non-destructive by default** (`dry_run=True`).

### Leitner Spaced Repetition

```schema
Box 1 (1 day) → Box 2 (3 days) → Box 3 (7 days) → Box 4 (14 days) → Box 5 (30 days)
```

Memories advance a box on successful recall, reset to Box 1 on failure. Box 5 is permanent.

---

## MCP Tool Architecture

Super Memory exposes **100+ MCP tools** organized by profile:

| Profile | Tools Included | Use Case |
|---------|---------------|----------|
| `normal` | 17 core tools | Day-to-day memory save/recall/status |
| `admin` | normal + 1 (`promote`) | Operator promotions |
| `advanced` | 70+ tools | Full cognitive feature surface |

### Core Tool Categories

```
save/remember ─► remember, remember_batch, todo, auto, normalize
recall/search ─► recall, memory_search, memory_get, context, prefetch,
                 recall_arbitrate, spreading_activation_recall, graph_recall
lifecycle ─────► consolidate, prune, cleanup, promote, pin, version
cross-agent ───► cross_agent_recall, cross_agent_compare, cross_agent_summary,
                 cross_agent_honcho_ask, list_agents
cross-session ─► cross_scope_recall, session_archive, session_timeline, synthesis
cognitive ─────► hypothesize, evidence_add, predict, verify_prediction, leitner
diagnostics ───► doctor, health, stats, status, migration_status
semantic ──────► (CLI only): semantic doctor, semantic index, semantic verify
```

---

## OpenClaw Integration

### Plugin Configuration

In `.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "super-memory": {
        "enabled": true,
        "config": {
          "mode": "admin",
          "apiBaseUrl": "http://127.0.0.1:8765",
          "autoSyncTurns": true,
          "autoFlush": true,
          "agentId": "lucas",
          "toolProfile": "admin"
        }
      }
    }
  }
}
```

### MCP Server

```json
{
  "mcp": {
    "servers": {
      "super-memory": {
        "command": "/path/to/super-memory-mcp",
        "args": ["--stdio", "--profile", "admin"],
        "env": {
          "SUPER_MEMORY_CONFIG": ".openclaw/super-memory.yaml",
          "SUPER_MEMORY_API_BASE_URL": "http://127.0.0.1:8765",
          "OPENCLAW_WORKSPACE_ROOT": "/home/oceandmt/.openclaw/workspace",
          "SUPER_MEMORY_AGENT_ID": "lucas"
        },
        "toolCallTimeoutMs": 90000
      }
    }
  }
}
```

### Honcho Integration

Super Memory synchronizes conversation turns to Honcho via the `honcho-auto-capture` plugin. This is configured through the `honcho` MCP server entry.

---

## Data Flow Diagram

```
[Agent Tool Call]            [CLI Command]              [REST API / HTTP]
       │                          │                           │
       ▼                          ▼                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     MCP Server (stdio transport)                 │
│               super-memory-mcp --stdio --profile admin           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                        HybridRecall                              │
│                                                                  │
│  cross_scope_recall(query, agent_scope, session_scope, layers):  │
│    1. query Markdown memories (TF-IDF keyword)                   │
│    2. query Honcho events (keyword)                              │
│    3. query MemPalace drawers (keyword)                          │
│    4. query Graph neurons (spreading activation)                 │
│    5. [vector_enabled] Semantic rerank via sqlite-vec KNN        │
│    6. Dedup + score fusion                                       │
│    7. Truncate to max_tokens                                     │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│ SQLite Database  │ │  Markdown   │ │  sqlite-vec      │
│ data/super-      │ │  Filesystem  │ │  data/vectors.   │
│ memory.sqlite3   │ │  memory/    │ │  sqlite3         │
└──────────────────┘ └──────────────┘ └──────────────────┘
```

---

## Runtime Status (2026-06-23)

| Metric | Value |
|--------|-------|
| Version | **v2.3.6** |
| Total memories | 697 |
| Auto Deep Grade | **A (90/100)** |
| Canonical Compliance | **99.9%** |
| MCP Tools | **254** |
| Autocomplete Prefixes | **17,090** |
| Tests Passing | **480/480** (Python 3.11 + 3.12) |
| CI/CD | ✅ Green — master + v2.3.6 tag |
| Deployment | ✅ release environment (6f72e14) |
| Deep Debug Problems | **0** |

### P0+P2 Module Health

| Module | Path | Status |
|--------|------|--------|
| MemoryEnvelope | `core/envelope.py` | ✅ |
| SourceAdapter | `ingest/__init__.py` | ✅ |
| Semantic Closets | `projections/closet.py` | ✅ |
| Recall Arbitration v3 | `recall/__init__.py` | ✅ |
| Recall Feedback | `recall/feedback.py` | ✅ |
| Drift Repair | `projections/drift_repair.py` | ✅ |
| Watcher Adapter | `watcher_adapter.py` | ✅ |
| Line Citations | `recall/line_citations.py` | ✅ |
| Dialectic | `recall/dialectic.py` | ✅ |
| Curriculum | `evals/curriculum.py` | ✅ |
| SKILLS | `SKILLS/` (8 files) | ✅ |

---

*Generated from code analysis and live runtime diagnostics — June 2026.*
