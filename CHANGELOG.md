# Changelog

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

