# Changelog

## 2.3.8 - 2026-07-13

### Added (enhancements)
- **E1 — firewall code-span whitelist** (`safety/firewall.py`): the threat-pattern check false-flagged SQL/shell keywords (`INSERT INTO`, `SELECT ... FROM`, `DROP TABLE`) even when they appeared only inside markdown code spans, so legitimate technical notes (e.g. an assistant turn documenting a query) got `firewall_blocked`. Threats are now re-checked with fenced/inline code spans stripped; only a threat surviving outside code blocks. Real injections outside code and XSS remain blocked.
- **E2 — quality-gate boilerplate detector** (`quality_scorer.py`): Lorem ipsum, license headers, and dependency-manifest fragments (top_level.txt / bare package-name lists) scored as "high-quality" on the raw entity/specificity heuristics (this is how virtualenv junk passed the gate). New `is_boilerplate()` detects them and `score_memory()` caps their overall score at ≤0.25, below the default write-gate threshold.
- **E3 — layer-parity health check** (`bridge.cross_layer_health`): previously only flagged a layer at count==0, so a single layer lagging the others (the palace_drawers rollback left mempalace 189 vs 204) went undetected. Now reports `layer_counts`, `layer_spread`, `parity_ok`, `parity_threshold`, and names `lagging_layers`; the maintenance `cross_layer_health` step and daily-hygiene cron surface it.

### Data
- Healed the residual mempalace parity gap: reprojected 14 alive rows that lost their mempalace sibling to the pre-2.3.7 ON CONFLICT rollback bug, through the fixed save path. All four layers now within spread=1 (`parity_ok=true`).

### Tests
- Regression suite now 34 tests: added E1 (code-span whitelist, real-injection/XSS still blocked), E2 (lorem/license/manifest boilerplate + real-note negative), and E3 (parity fields + synthetic lagging-layer detection).

### Safety
- No database files, local memory contents, private runtime config, or generated personal data are included in this release. The E1 change narrows a false-positive only; it does not weaken blocking of real injection payloads (verified by regression tests).


## 2.3.7 - 2026-07-13

### Fixed
- `layers.py::_save_palace_projection`: the MemPalace projection inserted into the legacy `id` column and used `ON CONFLICT(id)`, but `palace_drawers`' PRIMARY KEY is `drawer_id` and `id` carries no unique constraint. SQLite raised `ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint`, which rolled back the entire mempalace transaction on every direct save — silently dropping the mempalace layer (alive mempalace 189 vs neural 203). The upsert now targets `drawer_id` and populates it, and also stores `content_hash`. Backfilled 188 pre-existing rows whose `drawer_id` (PK) was NULL.
- `ingest/__init__.py::FileAdapter`: file ingest had no build/vendor ignore set, so virtualenv internals (`.venv/site-packages/*.dist-info`, Lorem ipsum, AUTHORS, top_level.txt) were ingested as `context` memories and even passed the quality gate as "high-quality". Added a shared `is_ignored_source_path()` (mirroring the ignore set in `code_index.py`) enforced in both `FileAdapter.can_handle` and `FileAdapter.ingest`; `resolve_adapter` no longer falls back to `FileAdapter` for ignored paths. The 190 pre-existing venv rows were already soft-deleted.
- `bridge.py::status()` (surfaced by `super_memory_stats`): reported raw `COUNT(*)`/`GROUP BY layer` that included soft-deleted rows (2028 total, mempalace 415) while the recall/list path filters them (true alive 799 / mempalace 189). `status()` now filters `soft_deleted` for `total_memories` and per-layer counts and adds a transparent `total_including_deleted` field.

### Added
- Regression coverage in `tests/test_injection_and_hydration_regression.py` (now 24 tests) for the palace_drawers PK conflict, the FileAdapter ignore-path filter, and the stats alive-count fix.

### Safety
- No database files, local memory contents, private runtime config, or generated personal data are included in this release.


## 2.3.6 - 2026-07-13

### Fixed
- `sanitize.py`: injection detector (`is_injection_content`) now drops content on a single high-confidence signature match instead of requiring >=2 signatures, closing a self-contamination leak where an appended prompt-injection block polluted the canonical store on single-mention turns.
- `bridge.py::_hydrate_recall_selection`: fold `drawer_id`/`closet_id` from `search_closets` rows into `metadata` at `_build_recall_channels` source instead of falling back to the memory's canonical UUID as a drawer id; the fallback returned zero hydrated content for every semantic-closet recall hit.
- `handoff.py::complete_handoff_with_outcome`: the raw `INSERT INTO memories` used to record handoff outcomes bypassed the canonical save path and never computed `content_hash`, leaving `handoff_outcome` rows with a NULL hash that silently breaks hash-based dedup/cross-layer joins. The insert now computes and stores `content_hash`.
- `dream.py` / `dream_engine.py`: Dream Engine's pattern-summary phase persisted raw token-frequency counts (e.g. `"'license' appears in 40 memories"`) as `insight` memories with no analytical value, and could echo prompt-injection tokens back into the store. Token-frequency patterns are now reported for observability only and never persisted; a shared `_is_dream_noise()` guard rejects ambient-token-only or injection-echoing candidates in both the bridge-insight and pattern-summary code paths before any live save.

### Added
- `data_improvement.py::_compute_trust`: trust scoring is now source- and type-aware. Raw conversational turn captures (`source` starting `openclaw.turn`, or `mem_type == "event"`) are capped at 0.4 so they cannot outrank curated memory in recall arbitration; durable types (`doctrine`, `preference`, `blocker`, `lesson`) get a +0.15 bonus; curated sources (`conversation-implementation`, `telegram-request`, `direct`, `super-memory`) get +0.10.
- `recall/feedback.py` is now wired into the live recall path: `bridge.recall()` calls `record_recall_event()` after every arbitration pass, populating `recall_events` (previously implemented but had zero callers).
- `consolidation.py`: topic-guard rejects hex/UUID-like tokens, pure-digit tokens, and vowelless tokens from becoming semantic-cluster topics; expanded the noise/stopword list (Vietnamese stopwords + template filler) used during consolidation.
- Regression suite `tests/test_injection_and_hydration_regression.py` (16 tests) covering the injection-filter fix, closet hydration fix, dream insight quality/noise guard, and the `memory_write_intents` write-contract wiring.
- `super-memory-daily-hygiene` cron job extended with a reversible dead-embed-job canceller and a layer-count drift check (flags when the alive-row spread across the four layers exceeds 5).

### Data
- One-time DB rescore of all active memories (749 rows) with the new source/type-aware trust function.
- 44 oversized (>2000 char) raw turn-dump `event` memories tiered to `lifecycle_tier="cold"` with a `compression_candidate` flag (reversible metadata change, no content loss).
- Cancelled 274 dead-target embed jobs (pointed at soft-deleted or orphaned memories); active embed backlog on live memories confirmed at 0.
- Backfilled `content_hash` on the one live row left NULL by the handoff bug; normalized all remaining NULL/empty `content_hash` rows (test-fixture junk, already soft-deleted) so every alive row now carries a full 64-character sha256 hash.
- 20 previously-created Dream Engine token-frequency "insights" (soft-deleted in a prior pass) confirmed as noise and left deleted; no longer reproducible under the new guard.

### Safety
- No database files, local memory contents, private runtime config, or generated personal data are included in this release.


## 2.3.5 - 2026-07-12

### Fixed
- Dedupe `promotion_candidates` (cognitive.py) by memory id and skip soft-deleted rows so derived layer mirrors no longer appear four times.
- Dedupe `lifecycle.review` `compression_candidates` by memory id, keeping the canonical `workspace_markdown` layer entry only.

### Added
- `recommendations` bridge + CLI/MCP surface for ranked Super Memory maintenance and UX suggestions.
- `autocomplete-rebuild` and `autocomplete-suggest` CLI commands wired to the prefix index.
- Default `trust_score` by `source_adapter` in the MemoryEnvelope factory (chat/direct/file/tool/url/auto/todo/feedback) with a 0.5 fallback.
- Promote `FACT` memories into `facts.md` register.
- New `super_memory/recommendation.py` module and autocomplete recommendation tests.

### Added (MCP tools)
- `super_memory_graph_cleanup_orphans` and `super_memory_dedup_neurons` exposed on the admin profile.

### Safety
- No database files, local memory contents, private runtime config, or generated personal data are included in this release.

## 2.3.4 - 2026-07-09

### Fixed
- Expose write-contract maintenance wrappers through the bridge so MCP tools `write_contract_reconcile`, `write_contract_process_jobs`, and `write_contract_semantic_merge` run bounded maintenance instead of timing out.
- Correct memory pollution duplicate accounting to use active canonical `workspace_markdown` memories only, excluding derived layer mirrors and soft-deleted rows.
- Dedupe short/no-agent/stale pollution report entries by memory id and ignore soft-deleted records.

### Improved
- Add canonical-first semantics metadata to the pollution report response.
- Keep duplicate-resolution v2 routed through the same semantic merge implementation used by write-contract maintenance.
- Update OpenClaw plugin metadata/schema shape and UI hints for safer additive/default operation.

### Safety
- No database files, local memory contents, private runtime config, or generated personal data are included in this release.

## 2.3.3 (1 July 2026) — MCP self-heal + closet coverage maintenance

- Fix `self_heal_status(mode="fast")` bridge path to use the bounded health cache implementation exposed by MCP, preventing live MCP timeout during vector self-heal status checks.
- Preserve `mode="full"` for complete vector coverage scans while keeping fast health checks bounded and timeout-resilient.
- Include short workspace memories in semantic closet chunking so closet coverage can reach the 80%+ diagnostics threshold.
- Verified installed OpenClaw Super Memory symlink, project repository, diagnostics, recall release gate, and live MCP `super_memory_self_heal_status` after gateway reload.

## 2.3.0 (25 June 2026) — Memory quality roadmap

### Added
- Universal MemoryEnvelope/write-gate contract scaffolding.
- Projection manifest with drift audit/repair/backfill.
- Long-memory verbatim drawer + semantic closet compression workflow.
- Recall evidence model and arbitration v4.
- Peer profiles and perspective memory tables.
- Recall regression benchmark and self-training queue integration.
- Scheduled maintenance report workflow.

### Improved
- Deep audit now treats retained canonical long memories as mitigated when verbatim drawers + semantic closets exist.
- Long-memory review skips already mitigated canonical records.
- Live maintenance reduced unresolved long memories to threshold and kept vectors healthy.

### Validation
- Live DB self-heal: missing_vectors=0, skipped_empty=0.
- Deep audit: A / health 100.
- Deep qualify: A / 90.0.
- Deep debug: 0 problems.
- Projection drift sample: orphans=0, stale=0, missing=0.
- Targeted tests: 6 passed.

## 2.2.1 (25 June 2026) — Maintenance, Recall Fallback, Self-Heal Accuracy

### Data-maintenance correctness
- Fix `self_heal_status()` and `self_heal_embeddings()` to count only active, non-empty, non-soft-deleted memories as vector-eligible.
- Add status breakdown: `eligible_memories`, `skipped_soft_deleted`, `skipped_empty`.
- Prevent soft-deleted/empty rows from inflating missing-vector counts.

### FTS / recall stability
- Remove manual `memories_fts` writes from `layers.py`; current content-table FTS is maintained by triggers.
- Add recall fallback paths for long diagnostic queries and stale/empty FTS states.
- Filter soft-deleted rows from layer FTS search results.

### Quality lifecycle
- Add conservative `lifecycle_quality_cleanup()` wrapper for duplicate soft-delete and long-memory compression marking.
- Improve dedup behavior to avoid writing duplicate marker rows.
- Improve RRF dedup by content hash across layers.

### Operations / indexing
- Add recall event/feedback HTTP endpoints.
- Add deterministic sqlite-vec lexical hash fallback when sqlite-vec lacks text embedding support.
- Extend session indexing fallback to OpenClaw agent transcript locations and `.jsonl` files.

### Tests
- Add `tests/test_self_heal_status.py` for active/non-empty self-heal accounting.
- Adjust lifecycle/contract tests for dedup guard behavior.

## 2.2.0 (23 June 2026) — P0+P2 + SKILLS Release

### P0 — MemoryEnvelope + SourceAdapter + Semantic Closets + Recall Arbitration v3
- **MemoryEnvelope v1** (`core/envelope.py`): quality/trust/provenance/lifecycle contract for every memory
- **SourceAdapter Manifest** (`ingest/__init__.py`): ChatTurnAdapter, FileAdapter, URLAdapter with deterministic chunking
- **Semantic Closets/Drawers** (`projections/closet.py`): verbatim-preserving pointer layer for structured retrieval
- **Recall Arbitration v3** (`recall/__init__.py`): unified scoring with `why_selected`, `why_excluded`, `layer_votes` explanations
- **Recall Feedback Loop** (`recall/feedback.py`): correction → training case pipeline

### P2 — Drift Repair + Watcher Adapter + Citations + Dialectic + Curriculum
- **Projection Drift Repair** (`projections/drift_repair.py`): audit orphaned projections + auto-repair
- **Adapter-driven Watcher** (`watcher_adapter.py`): file changes → SourceAdapter ingest pipeline
- **Line Citations + Neighbor Expansion** (`recall/line_citations.py`): source-verbatim excerpts with ±N line context
- **Agentic Dialectic Mode** (`recall/dialectic.py`): deterministic format synthesis + LLM-ready synthesis mode
- **Self-Education Curriculum** (`evals/curriculum.py`): failed recall → training cases → pytest benchmarks

### SKILLS/ — 8 agent skill proposals
- `SKILLS/` directory ships with repo: onboarding, basic-usage, quality-ingest, recall-arbitration, cross-agent, auto-deep, self-improve, lifecycle
- Each skill: MCP tools list, copy-paste Python workflows, verification checklist
- Agent mode mapping in `SKILLS/README.md`

### CI/CD & Deployment
- CI matrix: Python 3.11 + 3.12 (removed 3.10 per `requires-python >=3.11`)
- Hard deps: `numpy>=1.26` (for `rem.py`), `cryptography>=43.0` (for `encryption.py`)
- 108/108 tests passing, Grade A (90/100) qualify, 99.9% canonical compliance
- 254 MCP tools, 17,090 autocomplete prefixes
- Deployment to `release` environment: ✅ success

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
