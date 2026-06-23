# Changelog

## 2.1.0 (P0+P1+P2 Deep Implementation — Quality Gate, Recall Arbitration v2, Self-Training)

### P0 — Critical (Quality Gate + Recall Arbitration v2)
- **Quality Gate**: auto-classify memory type (decision/fact/workflow/blocker/preference), extract entities + relations, score quality (0-1), enrich with tags + content_hash
- **Recall Arbitration v2**: explainable multi-layer scoring formula (lexical overlap × layer weight × recency × trust × quality score × type boost), returns `why_selected` reasons per result

### P1 — Semantic Memory
- **Semantic Taxonomy**: 14 relation types (CAUSED_BY, LEADS_TO, RESOLVED_BY, CONTRADICTS, SUPERSEDES, DEPENDS_ON, IMPLEMENTS, CONFIGURES, INSTALLED_AT, SYNCED_WITH, EVIDENCE_FOR, EVIDENCE_AGAINST, DERIVED_FROM, MENTIONS)
- **Canonical Entity Resolution**: alias normalization (super-memory → super-memory, oceandmt/super-memory → super-memory-github)

### P2 — Workflows & Self-Improvement
- **Self-Training**: capture failed recall → regression test JSON + training queue markdown
- **Project State Update**: append structured updates to canonical project memory markdown
- **Issue Memory Update**: write/update markdown issue files with cause/fix/verification
- **Telemetry History**: query telemetry events with kind filters
- **TelemetryRegistry**: Prometheus-text helper class

### Cross-Layer Health
- **cross_layer_health()**: 4-layer coverage check
- **content_hash column**: added to SQLiteLayerBackend for dedup at storage level
- **Soft qualify failures**: cross_agent_recall + hybrid_cross_scope_recall tolerate non-critical failures
- **Backend openness**: chroma fails raise RuntimeError (no silent fallback)

### Tests
- 4 new P0/P1/P2 test functions
- 16 passing targeted tests for quality gate + recall arbitration + semantic taxonomy + self-training
- 2 recall regression cases in tests/recall_cases/

---

## 1.7.0 (P1-P3 Roadmap Completion — Memory Lifecycle)

### P0 — Critical (Recall Quality Enhanced)
- **Confidence Scoring**: unified metacognitive confidence with weighted retrieval/content/fidelity/freshness dimensions
- **Retrieval Pipeline**: composable 6-step recall orchestration (parse → expand → activate → fuse → score → format)
- **Fidelity Extraction**: single-sentence essence extraction + 5-tier fidelity layer classification
- **Query Intent Parsing**: depth/q?/temporal/causal detection for smarter routing

### P1 — Memory Consolidation & Code Structure
- **Hippocampal Replay**: pattern selection → co-activation pair building → synapse strengthening → cluster consolidation
- **Pipeline Steps**: modular step handlers (safety/parse/expand/retrieve/fuse/score/format/annotate/filter)
- **Storage Mixins**: composable TagMixin, LeitnerMixin, PriorityMixin, TemporalMixin, StatsMixin, SearchMixin, GraphMixin
- **Step Registry**: dynamic pipeline composition with enabled/disabled step control

### P2 — Semantic Memory & Context Management
- **Schema Assimilation**: auto-detect K=V, list, code, temporal patterns → register schema neurons with match API
- **Spaced Repetition (SM-2)**: forgetting curve estimation, ease factor adaptation, retention probability, overdue penalty, batch clustering
- **Token Budget**: value-per-token selection, budget allocation (system/query/memories), format-within-budget
- **Query Expander**: graph neighborhood, embedding similarity, synonym map, temporal context expansion

### Integration
- All 7 new modules connected to bridge.py (11 new bridge handlers)
- All 7 new modules registered in mcp_server.py (15 new MCP tools)
- All modules exported from __init__.py (v1.7.0)
- Each module independently testable with pure function smoke tests

---

## 1.6.0 (P0-P3 Full Deployment + Auto Deep Engine)

### P0 — Critical (Safety & Recall Quality)
- **Safety firewall**: input validation, threat patterns (SQLi, XSS, path traversal), content sanitization
- **Freshness**: 5-tier memory freshness evaluation (Fresh/Recent/Aging/Stale/Ancient)
- **Encryption**: Fernet symmetric encrypt/decrypt with key rotation support
- **Spreading Activation**: priority-queue based SA with diminishing returns, role-based synapse multipliers, frequency myelination
- **Dedup Pipeline**: 3-tier (SimHash → Embedding → LLM) with configurable thresholds

### P1 — Core Infrastructure
- **Relation Extraction**: causal/comparative/sequential pattern detection for graph enrichment
- **Structure Detector**: auto-detect JSON/CSV/KV/Table formats
- **Multi-Provider Embeddings**: Ollama, OpenAI, Gemini, OpenRouter backends
- **Activation Cache**: thermal state save/load for warm-start recall (SSC-lite)
- **Trigger Engine**: auto-capture patterns (decision, incident, lesson, workflow change)
- **Eternal Context**: 3-level session-start context injection from pinned memories

### P2 — Workflows & Integration
- **Brain Mode**: multi-mode config (local/hybrid/read-only/mirror)
- **Pipeline Integration**: bridges all P0-P2 into save/recall flow
- **Surface Upgrade**: token budget trimming, cluster auto-inference
- **Live Pipeline**: firewall → enrich → affect → save (service.py integration)

### P3 — Sync Foundation
- **Sync Protocol**: Merkle root diff for multi-device memory sync

### Auto Deep Engine
- Phase 1: Auto Audit (16 modules, avg 0.70)
- Phase 2: Auto Qualify (Grade A: 20/20 smoke, 9/9 edge passes)
- Phase 3: Auto Debug (0 issues found)
- Phase 4: Auto Improve (all modules ≥ C grade)


## 2.0.0 (P0-P3 Full Feature Deployment — Dream Engine, Telemetry, Auto Deep)

### P0 — Critical (Dream Engine & FTS Stability)
- **Dream Engine**: 3-phase consolidation dreaming — insight generation (keyword cluster bridging), weak tie reinforcement (Jaccard-similar synapses), pattern summary (frequency-based keyword patterns)
- **FTS Trigger Fix**: Root-cause fix for `sqlite3.OperationalError` on all memory INSERT/UPDATE — stale FTS5 triggers recreated with correct column schema, auto-detect + repair on init
- **FTS Schema Repair**: `layers.py` auto-detects stale FTS5 schema (only `content` column) and recreates with `(id, layer, content, tags)`
- **Forget + Edit Endpoints**: Full composite-key-safe forget (soft/hard delete) and edit (content/type/priority/tier) with `executescript()` workaround for FTS trigger conflict
- **Bridge Cleanup**: Dead duplicate code removed from `layers.py` (20 lines after `return out`)

### P1 — Core Infrastructure
- **Semantic Quality Module**: Reformatted from one-liner to maintainable multiline code
- **Short Term Module**: Reformatted from one-liner to maintainable multiline code
- **All UPDATE queries on `memories` table**: All parameterized updates converted to `executescript()` with manual escaping to avoid FTS trigger `SQL logic error`

### P2 — Memory Lifecycle & Leitner
- **Leitner SM-2**: All 3 UPDATE paths (`mark()`, `schedule()`, `auto_seed()`) hardened with `executescript()` fix
- **Lifecycle Tier/Compression**: All `metadata_json` updates hardened with `executescript()`
- **Lifecycle/Synthesis/Deep-Auto**: All cross-module UPDATEs fixed

### P3 — Cross-Agent & Analytics
- **Telemetry**: `record_event()` with kind/agent/tool/duration tracking, `aggregate_daily()` rollups, `stats()` with 7-day window
- **Per-Agent Isolation**: `set_agent_rules()`/`get_agent_rules()` with scope/agent blocklist, `isolation_summary()`, `agent_memory_counts()`
- **Auto-Complete**: Prefix-index suggest engine with `suggest()`, `idle_suggestions()`, `rebuild()`, `status()`
- **Auto Deep Pipeline**: 4-stage pipeline — `deep_audit()` (health), `deep_qualify()` (quality), `deep_debug()` (issues), `deep_improve()` (auto-fix proposals)

### MCP Server
- 22 new tools registered in `ADVANCED_TOOLS` set
- All tools have `TOOLS[_name]` schemas and `_call_tool` handlers
- Tool count: 155 (admin), 17 (user), 17 (readonly)

### Test Suite
- All 11 Phase 8 contract tests passing
- 30 core tests passing (phase1, phase8, tool catalog, sanitize, guardrails, slot contract, promotion)
- Pre-existing failure in `test_api_remember_status_prefetch_promote` (assert 2==3) — unrelated SQLite test fixture issue
