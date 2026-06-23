# Deep Research — Super Memory v2.1.0

**Date:** 2026-06-23 24:30 ICT  
**Commit:** `d73ec48`

---

## 1. Cross-Agent Memory + Cross-Session Memory

### 1.1 Core Mechanisms

| Mechanism | Module(s) | Tools | Status |
|-----------|-----------|-------|--------|
| **Agent-scoped memories** | `memory_core.py`, `bridge.py` | `agent_id` column, `agent:<id>` tags | ✅ Active (lucas/alex/max/isol) |
| **Session-scoped memories** | `session_index.py`, `session_archive.py` | `session_id` column, FTS5 session index | ✅ Active |
| **Shared/project scopes** | `models.py` (MemoryScope) | `scope=shared/project/agent-local/session` | ✅ Active |
| **Cross-agent recall** | `cross_agent.py` (CrossAgentTools) | `super_memory_cross_agent_recall`, `_compare`, `_summary`, `_report`, `_honcho_ask`, `_conflicts` | ✅ Active (6 tools) |
| **Cross-session recall** | `recall_arbitration.py` | `cross_scope_recall(agent_scope, session_scope, source_layers)` | ✅ Active |
| **Session timeline/search** | `session_timeline.py` | `super_memory_session_timeline`, `_search`, `_list`, `_health`, `_evolution` | ✅ Active |
| **Session archives + summaries** | `session_archive.py` (SessionArchive) | `create_session_summary`, `get_session_summary`, `search_session_archives`, `list_session_summaries`, `sync_archive_to_honcho` | ✅ Active |
| **Handoff bundles** | `handoff.py` (HandoffManager) | `create_handoff`, `get_handoff`, `list_handoffs`, `update_handoff_status`, `load_current_handoff`, `complete_handoff_with_outcome`, `auto_handoff_on_spawn` | ✅ Active |
| **Honcho participant/session** | `honcho/tools.py` (HonchoTools) | `honcho_profile`, `honcho_ask`, `honcho_context`, `honcho_conclude`, `honcho_search`, `honcho_analyze_turn`, `honcho_sessions` | ✅ Active |
| **Agent isolation** | `agent_isolation.py`, `isolation.py` | `isolation_set_rules`, `_get_rules`, `_summary`, `_agent_counts` | ✅ Active |
| **Cross-session synthesis** | `session_timeline.py` | `super_memory_cross_session_synthesis`, `_session_end_summary` | ✅ Active |
| **Session visibility boost** | `session_visibility.py` | `boost_current_session()`, `annotate_session_info()` | ✅ Active |
| **Claim extraction + contradiction** | `claim_extractor.py` | `extract_claims`, `find_contradictions`, `resolve_contradiction` | ✅ Active |

### 1.2 Data Model (Agent + Session Columns)

```sql
memories: id, layer, content, type, scope, agent_id, session_id, project, tags_json, ...
honcho_events: id, memory_id, workspace, session_id, observer_peer_id, observed_peer_id, ...
handoff_bundles: id, from_agent, to_agent, session_id, title, summary, status, ...
cognitive_neurons: source_memory_id -> memory_id cross-table
palace_drawers: memory_id reference, agent_id, wing, room, drawer
```

### 1.3 MemoryScope Enum

```python
class MemoryScope(str, Enum):
    SESSION = "session"        # Temporary turn/session context
    AGENT_LOCAL = "agent-local" # One agent's private work context
    SHARED = "shared"          # Doctrine/preferences/decisions for all agents
    PROJECT = "project"        # Project-level implementation context
    CROSS_AGENT = "cross-agent" # Handoffs, comparisons, inter-agent artifacts
```

### 1.4 Key Flows

**Save with agent + session context:**
```
remember(content, scope="shared", agent_id="lucas", session_id="discord:xxx")
  → Bridge → Service.save(record)
    → SAVE_ORDER: workspace_markdown → mempalace → honcho → neural_memory
    → All 4 layers store agent_id, session_id, scope
    → Graph projection: cognitive_neurons + synapses
```

**Cross-agent recall:**
```
cross_agent_recall(query="plugin config", agent_id="alex")
  → SQL: WHERE (agent_id='alex' OR tags LIKE '%agent:alex%') AND content LIKE '%plugin config%'
  → Returns memories scoped to that agent
```

**Cross-session recall:**
```
cross_scope_recall(query="canonical markdown", agent_scope="all", session_scope="recent", source_layers=["markdown","honcho","mempalace","graph"])
  → Multi-layer parallel search
  → Merge results with layer arbitration weights
```

---

## 2. Tool/Layer Cooperation — Thống Nhất, Xuyên Suốt

### 2.1 Layer Architecture (ADR-001, ADR-002)

```
Canonical-first authority chain:
  1. Workspace Markdown (canonical local truth) ← memory/YYYY-MM-DD.md files
  2. MemPalace (structured procedural/project memory) ← palace_drawers SQLite
  3. Honcho (conversation/participant/session memory) ← honcho_events SQLite
  4. NeuralMemory-style (associative/graph memory) ← cognitive_neurons + synapses

Three surfaces:
  - OpenClaw plugin tools (index.js → HTTP API)
  - MCP stdio tools (mcp_server.py → bridge.py)
  - HTTP REST API (api.py → bridge.py)
```

### 2.2 Save Order (SAVE_ORDER)

```python
SAVE_ORDER = [
    MemoryLayer.WORKSPACE_MARKDOWN,  # 1st: canonical
    MemoryLayer.MEMPALACE,            # 2nd: structured projection
    MemoryLayer.HONCHO,               # 3rd: conversational projection
    MemoryLayer.NEURAL_MEMORY,        # 4th: associative projection
]
```

- If workspace_markdown fails AND `require_canonical_first=true` → skip downstream
- If workspace_markdown fails AND `require_canonical_first=false` → downstream saves with `pending_canonical_sync=True`
- `flush_pending()` replays pending records into Markdown

### 2.3 Layer Separation + Weights

| Layer | Role | Arbitration weight | 
|-------|------|-------------------|
| workspace_markdown | Exact durable truth | 1.0 (wins for exact facts) |
| mempalace | Procedural/project | 0.82 (wins for workflows/procedures) |
| honcho | Social/conversation | 0.78 (wins for participants/sessions) |
| neural_memory | Associative patterns | 0.88 (wins for cross-time patterns) |

### 2.4 Cognitive Layer Arbitration (Phase 6)

```python
def recall_arbitrate(query, limit=10):
    layered = recall(query)   # Parallel recall across all 4 layers
    from .recall_arbitration import arbitrate
    return arbitrate(query, layered, limit=limit)
```

Default arbitration rules (in `recall_arbitration.py`):
- Exact command/path/config/date/quote: Workspace Markdown or source file wins
- Workflow/procedure: MemPalace gets higher weight
- Participant/session/preference: Honcho gets higher weight
- Pattern/association/repeated blocker: NeuralMemory gets higher weight
- Conflict: preserve all candidates, mark conflict, prefer canonical until resolved

### 2.5 All Tools by Layer Access

| Layer | MCP Tools | Plugin Tools | CLI Commands |
|-------|-----------|-------------|-------------|
| All layers | `remember`, `recall`, `context`, `show`, `stats`, `health`, `sync_turn` | Same via plugin | Same via CLI |
| Workspace Markdown | `memory_search`, `memory_get`, `prefetch`, `search_compatible`, `get_compatible` | Legacy shims (exclusive mode) | `super-memory search` |
| MemPalace | `palace_search`, `palace_wings`, `palace_rooms`, `palace_halls`, `palace_drawers`, `palace_load_layer`, `palace_summary`, `palace_extract`, `palace_startup_context` | Same | `super-memory palace` |
| Honcho | `honcho_ask`, `honcho_context`, `honcho_profile`, `honcho_conclude`, `honcho_search`, `honcho_analyze_turn`, `honcho_sessions` | `capture_event`, `capture_turn` | `super-memory honcho` |
| NeuralMemory | `graph_recall`, `spreading_activation_recall`, `graph_neighbors`, `graph_stats`, `graph_rebuild`, `graph_rebuild_incremental`, `graph_cleanup_orphans` | Same | `super-memory graph` |
| Cross-agent | `cross_agent_recall`, `cross_agent_compare`, `cross_agent_summary`, `cross_agent_report`, `cross_agent_honcho_ask`, `cross_agent_conflicts` | Same (+ `cross_scope_recall`) | `super-memory cross-agent` |
| Cross-session | `session_timeline`, `session_search`, `session_list`, `session_health`, `session_evolution`, `session_end_summary`, `cross_session_synthesis` | Same (+ `session_index`) | `super-memory session` |
| Agent isolation | `isolation_set_rules`, `isolation_get_rules`, `isolation_summary`, `isolation_agent_counts` | Same | `super-memory isolation` |

### 2.6 Bridge.py — The Unified Entrypoint

`bridge.py` is the **single orchestration layer** for all tool surfaces:
- 90+ exposed functions
- Every function normalizes input, calls canonical-first service, projects to all 4 layers
- Every function returns `{"ok": True/False, ...}` with layer-specific results

```python
def remember(payload) → {"record": ..., "results": [4-layer results], "graph_projection": ...}
def recall(query, limit) → {"workspace_markdown": [...], "mempalace": [...], "honcho": [...], "neural_memory": [...]}
def sync_turn(payload) → {"results": [4-layer projection results]}
```

---

## 3. Workflows + Lifecycle

### 3.1 Memory Lifecycle

```
User Input → Sanitize → Quality Gate → Normalize → 
  Attention Score → Route Memory → 
  save(SAVE_ORDER) → 
    Workspace Markdown (canonical) ✓→ 
      MemPalace → Honcho → NeuralMemory →
        Graph Projection → 
          Consolidation Cycle (dedup/mature/enrich/dream/compress) →
            Leitner Review → Promotion Candidates →
              Promote to MEMORY.md / Registers
```

### 3.2 Consolidation Lifecycle

| Phase | Function | When | Strategy |
|-------|----------|------|----------|
| **Prune** | `intelligence.consolidate(strategy="prune")` | Background | Remove synapses <0.05 weight |
| **Merge** | `intelligence.consolidate(strategy="merge")` | Background | Merge Jaccard >0.5 fibers |
| **Summarize** | `intelligence.consolidate(strategy="summarize")` | Background | Create compressed summaries |
| **Mature** | `intelligence.consolidate(strategy="mature")` | Background | Promote stable truths |
| **Enrich** | `intelligence.consolidate(strategy="enrich")` | Periodic | Add semantic links |
| **Dream** | `dream_engine.run_dream_cycle()` | Periodic | Pattern detection + insight generation |
| **Dedup** | `intelligence.consolidate(strategy="dedup")` | Periodic | Remove duplicates |
| **Compress** | `lifecycle.compression()` | Periodic | Compress cold memories |
| **Leitner** | `leitner.queue/mark/schedule` | On review | 5-box spaced repetition |

### 3.3 Cognitive Workflows (Phase 6)

```python
# 1. Working Memory (short-lived task/session state)
working_memory_set({"current_task": "deep-research", "active_project": "super-memory"})
working_memory_get("default")

# 2. Attention Scoring
attention_score(payload) → {"attention_score": 0.85, "salience": "high", "routes": [...], "ttl": "durable"}

# 3. Route Memory
route_memory(payload) → {"route": {"routes": ["workspace_markdown", "mempalace", "honcho", "neural"]}}

# 4. Parallel Save
parallel_save(payload) → {"ok": True, "layers": {...}}

# 5. Recall Arbitrate
recall_arbitrate(query) → {"answer_context": [...], "layer_votes": {...}, "conflicts": [...]}

# 6. Consolidation Cycle
consolidation_cycle(strategy="light") → {"dedup": ..., "compress": ..., "promote": ...}

# 7. Hypothesis → Evidence → Prediction → Verify
hypothesis_create("Memory leak in FTS5")
evidence_add(hypothesis_id, "Confirmed: FTS5 triggers fail on UPDATE")
prediction_create("Fix FTS5 triggers → no more leaks", hypothesis_id=hypothesis_id)
verify_prediction(prediction_id, outcome="correct")

# 8. Feedback Learning
feedback_outcome(memory_id, success=True, outcome="FTS5 fix verified")
```

### 3.4 Dream Engine (Background Pattern Detection)

```python
# Detect patterns in existing memories
run_dream_cycle() → {"patterns": [...], "insights": [...], "weak_ties": [...]}

# Generate insight narrative
generate_narrative(max_insights=10) → {"sections": ["Patterns", "Weak Ties", "Insights"]}
```

### 3.5 Lifecycle Functions

| Tool | What It Does |
|------|-------------|
| `leitner_queue(limit=50)` | Memories due for review |
| `leitner_mark(fiber_id, success=True)` | Review result → box++ or reset |
| `leitner_schedule(fiber_id, box=3)` | Manual box assignment |
| `leitner_stats()` | Distribution + review stats |
| `leitner_auto_seed(limit=100)` | Assign box 0 to unreviewed |
| `lifecycle_review(limit=500)` | Score and prioritize compression candidates |
| `lifecycle_cache(action="status")` | Activation cache stats |
| `lifecycle_tier(action="evaluate")` | Auto-tier hot/warm/cold |
| `lifecycle_compression(action="review")` | Find compression candidates |
| `reflex_status()` | List pinned reflex neurons |

---

## 4. Install Guide + Config for OpenClaw

### 4.1 Quick Install

```bash
# Install from GitHub
pip install 'git+https://github.com/oceandmt/super-memory.git'

# Basic setup wizard
super-memory setup \
  --workspace-root "$HOME/.openclaw/workspace" \
  --output "$HOME/.openclaw/super-memory.yaml" \
  --overwrite

# Run API (always-on for OpenClaw plugin)
super-memory-api --host 127.0.0.1 --port 8765

# Verify
super-memory doctor --no-benchmark --json-out
curl -fsS http://127.0.0.1:8765/health
```

### 4.2 Systemd Service (Production)

```ini
[Unit]
Description=Super Memory API
After=network.target

[Service]
Type=simple
User=oceandmt
WorkingDirectory=%h/.openclaw/workspace
ExecStart=%h/.openclaw/venvs/super-memory-cli/bin/super-memory-api --host 127.0.0.1 --port 8765
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

### 4.3 OpenClaw Plugin Install

```bash
# From repo clone
git clone https://github.com/oceandmt/super-memory.git
cd super-memory

# Stage 1: safe mode (additive tools only)
bash scripts/install-openclaw-plugin.sh --mode safe

# Stage 2: admin mode (recommended — keeps memory-core intact)
bash scripts/install-openclaw-plugin.sh --mode admin

# Stage 3: exclusive slot (only after qualification)
bash scripts/install-openclaw-plugin.sh --mode exclusive

# Verify
bash scripts/openclaw_plugin_doctor.sh
```

### 4.4 OpenClaw Config Modes

#### Mode: `safe` — Additive tools only

```json
{
  "plugins": {
    "super-memory": {
      "mode": "safe",
      "apiBaseUrl": "http://127.0.0.1:8765",
      "registerExclusiveMemoryCapability": false,
      "registerLegacyMemoryShims": false
    }
  }
}
```

**What's enabled:** `super_memory_remember`, `_recall`, `_search_compatible`, `_get_compatible`, `_prefetch`, `_sync_turn`, `_promote`, `_status`, `_remember_batch`, `_show`, `_context`, `_todo`, `_auto`, `_stats`, `_health`, `_conflicts`, `_provenance`, `_pin`, `_consolidate`, `_situation`, `_boundaries`

#### Mode: `admin` — Recommended for cross-agent/cross-session (keeps memory-core)

```json
{
  "plugins": {
    "super-memory": {
      "mode": "admin",
      "apiBaseUrl": "http://127.0.0.1:8765",
      "autoSyncTurns": true,
      "autoContext": false,
      "autoFlush": true,
      "startupConsolidation": false,
      "agentId": "lucas",
      "toolProfile": "admin",
      "registerExclusiveMemoryCapability": false,
      "registerLegacyMemoryShims": false
    }
  }
}
```

**What's additionally enabled:** Turn hooks (`autoSyncTurns`), auto-flush, all cross-agent/session tools, MemPalace tools, Honcho tools, graph tools, cognitive tools, lifecycle tools, isolation tools

#### Mode: `exclusive` — Memory-slot replacement (cutover)

```json
{
  "plugins": {
    "slots": { "memory": "super-memory" },
    "super-memory": {
      "mode": "exclusive",
      "apiBaseUrl": "http://127.0.0.1:8765",
      "registerExclusiveMemoryCapability": true,
      "registerLegacyMemoryShims": true,
      "autoSyncTurns": true,
      "autoContext": true,
      "autoFlush": true
    }
  }
}
```

**What's additionally enabled:** OpenClaw memory slot ownership, `memory_search`/`memory_get` legacy shims, auto-context injection

### 4.5 MCP Profiles (Non-OpenClaw Agents)

```bash
# Normal: daily-safe tools only
super-memory-mcp --stdio --profile normal

# Admin: all tools including cross-agent/session
super-memory-mcp --stdio --profile admin

# Via env var
SUPER_MEMORY_MCP_PROFILE=admin super-memory-mcp --stdio
```

### 4.6 Full Config Reference

Full `super-memory.yaml`:

```yaml
workspace_root: /home/oceandmt/.openclaw/workspace
sqlite_path: data/super-memory.sqlite3
daily_memory_dir: memory
long_term_file: MEMORY.md
registers_dir: memory/registers
require_canonical_first: true
enabled_layers:
  - workspace_markdown
  - mempalace
  - honcho
  - neural_memory
api_token: ""                         # Bearer token for HTTP API
db_backend: sqlite                    # sqlite (only supported)
vector_enabled: true                  # Enable vector embeddings
embedding_provider: ollama            # Provider: ollama|sentence_transformers|lm_studio|openai|mistral|...
embedding_model: nomic-embed-text     # Model name
embedding_endpoint: http://127.0.0.1:11434/api/embed  # Endpoint URL
embedding_dimension: 768              # Must match model
```

### 4.7 MCP Client Config (For Claude Code / Cursor / Windsurf)

```json
{
  "mcpServers": {
    "super-memory": {
      "command": "/path/to/super-memory-venv/bin/super-memory-mcp",
      "args": ["--stdio", "--profile", "admin"],
      "env": {
        "SUPER_MEMORY_WORKSPACE_ROOT": "/home/oceandmt/.openclaw/workspace",
        "SUPER_MEMORY_SQLITE_PATH": "/home/oceandmt/.openclaw/workspace/data/super-memory.sqlite3",
        "SUPER_MEMORY_MCP_PROFILE": "admin"
      }
    }
  }
}
```

---

## 5. Deep Analysis Results

### 5.1 Deep-Qualify

| Metric | Value | Grade |
|--------|-------|-------|
| Durable ratio | 64.0% | ✅ A |
| Trust coverage | 95.8% | ✅ A |
| Avg content length | 1,025 chars | ✅ A |
| Canonical compliance | 78.3% | ✅ A |
| **Overall** | **Grade A (100/100)** | 🏆 |

### 5.2 Deep-Audit

| Metric | Value |
|--------|-------|
| **Modules** | 188 total, 188 importable (100%) |
| **Failed imports** | 0 |
| **Missing `__all__`** | 144 (internal/support modules) |
| **Missing docstring** | 40 (tools/bridge modules) |

### 5.3 Deep-Test (42/42 PASS)

Core modules → embeddings (12 providers) → REM → watcher → flush → reindex → identity → self-heal → prompt → narrative → QMD → preflight → sync → quality → dedup → confidence → safety → MCP tools (225) → consolidation → cognitive → graph → honcho → mempalace → dream → hypothesis → leitner → lifecycle → telemetry → isolation → brain mode → storage → service → bridge

### 5.4 Deep-Debug

| Category | Count |
|----------|-------|
| Issues found | 0 |
| Auto-fixes applied | 0 |

### 5.5 Live State (as of 2026-06-23)

| Component | Count |
|-----------|-------|
| Total memories | 2,002 |
| workspace_markdown | 775 |
| mempalace | 393 |
| honcho | 417 |
| neural_memory | 417 |
| cognitive_neurons | 5,655 |
| cognitive_synapses | 13,078 |
| cognitive_fibers | 894 |
| palace_drawers | 695 |
| honcho_events | 943 |
| MCP tools | 225 |

---

## 6. Summary

### Mạnh (Strengths)
1. **Canonical-first layered architecture** — Workspace Markdown is always the source of truth; derived layers enrich recall
2. **Full cross-agent/session support** — agent_id, session_id, scope=SHARED/PROJECT/AGENT_LOCAL, Honcho sessions, handoff bundles, session archive/synthesis
3. **225 MCP tools** — Comprehensive coverage across all 4 layers + cognitive + lifecycle
4. **3 OpenClaw deployment modes** — safe (additive) → admin (cross-agent/cross-session) → exclusive (memory-slot cutover)
5. **42/42 tests pass** — Grade A qualify, 0 debug issues
6. **SAVE_ORDER invariant** — canonical markdown → mempalace → honcho → neural_memory
7. **Phase 6 cognitive orchestration** — working memory, attention scoring, parallel save, recall arbitration
8. **Phase 7 lifecycle** — Leitner 5-box, tier hot/warm/cold, compression, dream engine

### Cần Cải Thiện (Improvement Areas)
1. **144 modules missing `__all__`** — Boilerplate but trivial to add
2. **40 modules missing docstrings** — Bridge/tools modules could use docstrings
3. **No live OpenClaw gateway hook validation yet** — Pre-prompt/post-agent hooks still need sandbox validation
4. **Phase 4 heavy features disabled-safe** — train/import/index/watch/sync/telegram/visualize/store = stubs
5. **Cross-agent recall uses SQLite LIKE** — Not semantic embedding by default (but available via admin tools)
6. **Caveat: safe MCP profile** does not expose cross-agent/session tools — must use `admin`

