# Changelog

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

