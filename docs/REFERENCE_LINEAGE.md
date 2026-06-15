# Reference Lineage

This document maps super-memory features to their upstream sources in the referred-memory collection:
- `projects/referred-memory/neural-memory` (v4.58.0)
- `projects/referred-memory/honcho` (v3.0.9)
- `projects/referred-memory/mempalace` (v3.4.1)

**Status Legend:**
- ✅ **implemented** - feature implemented, full parity with upstream
- 🟡 **partial** - feature implemented, simplified/adapted for OpenClaw
- 📋 **planned** - feature identified for future implementation
- ❌ **rejected** - feature explicitly not planned for super-memory

---

## Core Memory Operations (22 tools)

### super_memory/storage.py
- **Inspired by:** `neural-memory/src/neural_memory/core/brain.py`
- **Status:** 🟡 partial
- **Decision:** SQLite-native memory storage, no multi-brain support
- **Upstream features used:** basic CRUD, memory record model
- **Upstream features omitted:** brain modes, brain switching, cloud sync

### super_memory/models.py
- **Inspired by:** `neural-memory/src/neural_memory/core/neuron.py`, `fiber.py`, `memory_types.py`
- **Status:** 🟡 partial
- **Decision:** Simplified memory types enum, no full neuron/fiber/synapse graph
- **Upstream features used:** memory type classification (fact/decision/preference/etc)
- **Upstream features omitted:** neuron activation, synapse weights, fiber maturation

### super_memory/db.py
- **Inspired by:** `neural-memory` DB helpers, `mempalace/backends/sqlite_exact.py`
- **Status:** ✅ implemented
- **Decision:** DBMixin pattern for shared connection/validation
- **Upstream features used:** connection pooling, input validation, safety guards
- **Upstream features omitted:** multi-backend abstraction

### super_memory/migrations.py
- **Inspired by:** `neural-memory` migrations, `honcho` Alembic migrations
- **Status:** 🟡 partial
- **Decision:** Simple schema.sql + additive ALTER migrations, no full Alembic
- **Upstream features used:** idempotent migrations, column addition
- **Upstream features omitted:** migration versioning, rollback, branching

---

## Honcho-Inspired Features (7 tools)

### super_memory/honcho/session.py
- **Inspired by:** `honcho/src/crud/session.py`
- **Status:** 🟡 partial
- **Decision:** SQLite session tracking, no PostgreSQL/multi-tenant
- **Upstream features used:** session lifecycle, workspace context
- **Upstream features omitted:** JWT auth, workspace isolation, rate limiting

### super_memory/honcho/peer.py
- **Inspired by:** `honcho/src/crud/peer_card.py`
- **Status:** 🟡 partial
- **Decision:** Basic peer card/profile, no representation clustering
- **Upstream features used:** peer facts, profile storage
- **Upstream features omitted:** representation vectors, dream clustering, surprisal detection

### super_memory/honcho/dialectic.py
- **Inspired by:** `honcho` dialectic reasoning system
- **Status:** 🟡 partial
- **Decision:** Simplified multi-pass synthesis, no full reasoning-level infrastructure
- **Upstream features used:** context synthesis, conclusion generation
- **Upstream features omitted:** reasoning traces, telemetry, cost tracking

### super_memory/honcho/insights.py
- **Inspired by:** `honcho` insights/conclusions
- **Status:** 🟡 partial
- **Decision:** Basic conclusion storage, no evidence graph
- **Upstream features used:** conclusion CRUD, confidence scoring
- **Upstream features omitted:** times_derived, deduplication, evidence links

### super_memory/honcho/tools.py
- **Inspired by:** `honcho` examples (zo, crewai)
- **Status:** 🟡 partial
- **Decision:** MCP tool wrappers for Honcho features
- **Upstream features used:** ask/context/profile/conclude pattern
- **Upstream features omitted:** full Honcho API client integration

---

## MemPalace-Inspired Features (9 tools)

### super_memory/mempalace/spatial.py
- **Inspired by:** `mempalace/mempalace/layers.py`, `hallways.py`
- **Status:** 🟡 partial
- **Decision:** Wing/room/hall/drawer hierarchy, SQLite-only
- **Upstream features used:** spatial placement, hierarchical navigation
- **Upstream features omitted:** multi-backend (Chroma/Qdrant/pgvector), embedding search

### super_memory/mempalace/loader.py
- **Inspired by:** `mempalace` startup/onboarding
- **Status:** 🟡 partial
- **Decision:** Basic layer loading for startup context
- **Upstream features used:** layer initialization
- **Upstream features omitted:** full onboarding wizard, migration tools

### super_memory/mempalace/extractor.py
- **Inspired by:** `mempalace/mempalace/general_extractor.py`, `entity_detector.py`
- **Status:** 🟡 partial
- **Decision:** Pattern-based entity/concept extraction
- **Upstream features used:** keyword extraction, entity detection
- **Upstream features omitted:** LLM refinement, knowledge graph, entity registry

### super_memory/mempalace/compressor.py
- **Inspired by:** `mempalace` compression/dedup
- **Status:** 🟡 partial
- **Decision:** Basic summarization, no full compression pipeline
- **Upstream features used:** content summarization
- **Upstream features omitted:** collision scan, repair, normalization

### super_memory/mempalace/tools.py
- **Inspired by:** `mempalace/mempalace/mcp_server.py`
- **Status:** 🟡 partial
- **Decision:** MCP tool wrappers for MemPalace features
- **Upstream features used:** search/navigate/extract pattern
- **Upstream features omitted:** full CLI integration, hooks, sweeper

---

## NeuralMemory Passthrough (1 tool)

### nmem_recall in super_memory/mcp_server.py
- **Inspired by:** `neural-memory` full MCP server
- **Status:** ✅ implemented (passthrough)
- **Decision:** Delegate to external NeuralMemory MCP server when available
- **Upstream features used:** full recall API via passthrough
- **Upstream features omitted:** none (full delegation)

---

## Cross-Agent Features (6 tools)

### super_memory/cross_agent.py
- **Inspired by:** `neural-memory` multi-brain concepts, `honcho` workspace/peer
- **Status:** 🟡 partial
- **Decision:** Cross-agent recall/summary for Lucas/Alex/Max/Isol
- **Upstream features used:** agent-scoped memory, cross-agent queries
- **Upstream features omitted:** workspace isolation, full multi-tenant

---

## Session Management (8 tools)

### super_memory/session_timeline.py
- **Inspired by:** `honcho` session history, `neural-memory` eternal context
- **Status:** 🟡 partial
- **Decision:** Timeline view for session events
- **Upstream features used:** chronological event log
- **Upstream features omitted:** full event sourcing, replay

### super_memory/session_archive.py
- **Inspired by:** `honcho` session summarization
- **Status:** 🟡 partial
- **Decision:** TF-IDF semantic summary picker
- **Upstream features used:** summarization, archive storage
- **Upstream features omitted:** LLM-based summarization, dream-based synthesis

---

## Handoff & Delegation (5 tools)

### super_memory/handoff.py
- **Inspired by:** `neural-memory` handoff concepts, OpenClaw native delegation
- **Status:** ✅ implemented
- **Decision:** Handoff bundle for agent-to-agent task delegation
- **Upstream features used:** context bundling, status tracking
- **Upstream features omitted:** none (custom OpenClaw implementation)

---

## Graph & Recall (5 tools)

### super_memory/graph.py
- **Inspired by:** `neural-memory/src/neural_memory/recall/spreading_activation.py`
- **Status:** 🟡 partial
- **Decision:** Basic graph edges, no full spreading activation yet
- **Upstream features used:** memory edges, neighbor traversal
- **Upstream features omitted:** weighted activation, depth traversal, confidence scoring

### super_memory/hybrid_recall.py
- **Inspired by:** `neural-memory` hybrid recall, `mempalace` search
- **Status:** 🟡 partial
- **Decision:** Multi-layer recall with token budget
- **Upstream features used:** layer merging, budget selection
- **Upstream features omitted:** spreading activation paths, full graph traversal

---

## Cognitive Tools (7 tools)

### super_memory/cognitive.py (hypotheses/predictions/evidence)
- **Inspired by:** `neural-memory` hypothesis/prediction/evidence tools
- **Status:** 🟡 partial
- **Decision:** Bayesian confidence tracking, simplified cognitive workflow
- **Upstream features used:** hypothesis creation, evidence addition, verification
- **Upstream features omitted:** auto-resolve thresholds, causal chains, milestone tracking

---

## Knowledge Management (27 tools)

### super_memory/reasoning.py (conflicts/contradictions)
- **Inspired by:** `neural-memory` conflict detection, `honcho` deduplication
- **Status:** 🟡 partial
- **Decision:** Contradiction detection, resolution tracking
- **Upstream features used:** conflict candidates, resolution
- **Upstream features omitted:** evidence-backed resolution, times_derived

### super_memory/claim_extractor.py
- **Inspired by:** `neural-memory` extraction, `mempalace` entity detector
- **Status:** 🟡 partial
- **Decision:** Pattern-based claim extraction (preferences/decisions/workflows)
- **Upstream features used:** regex patterns, deduplication
- **Upstream features omitted:** LLM extraction, entity linking

---

## Synthesis & Cross-Session (5 tools)

### super_memory/synthesis.py
- **Inspired by:** `honcho` cross-session synthesis, `neural-memory` consolidation
- **Status:** 🟡 partial
- **Decision:** Pattern-based insight generation, shared memory promotion
- **Upstream features used:** cross-session patterns, shared scope
- **Upstream features omitted:** LLM synthesis, dream-based discovery

---

## Lifecycle & Consolidation (4 tools)

### Consolidation features
- **Inspired by:** `neural-memory` consolidation cycle (prune/merge/summarize/mature/dream)
- **Status:** 📋 planned
- **Decision:** Defer to Sprint 5 - basic dedup/promotion for now
- **Upstream features used:** none yet
- **Upstream features omitted:** full consolidation (prune/merge/summarize/mature/infer/enrich/dream/learn_habits/dedup/semantic_link/compress)

---

## Import & Training (3 tools)

### Import features
- **Inspired by:** `neural-memory` import from ChromaDB/Mem0/Cognee/Graphiti/LlamaIndex
- **Status:** 📋 planned
- **Decision:** Defer migration/import tools
- **Upstream features used:** none yet
- **Upstream features omitted:** external adapter integration

---

## Rejected Features

### Multi-Backend Abstraction
- **Source:** `mempalace/backends/` (Chroma/Qdrant/pgvector)
- **Status:** ❌ rejected
- **Reason:** SQLite+WAL sufficient for current scale; multi-backend adds complexity without clear need

### Full Alembic Migrations
- **Source:** `honcho` Alembic migration infrastructure
- **Status:** ❌ rejected
- **Reason:** schema.sql + additive migrations simpler for single-DB system

### JWT Auth / Multi-Tenant
- **Source:** `honcho` security/auth system
- **Status:** ❌ rejected
- **Reason:** OpenClaw handles auth; super-memory is single-tenant per instance

### Dream Scheduler / Clustering
- **Source:** `honcho/src/dreamer/` LSH/covertree clustering
- **Status:** ❌ rejected (for now)
- **Reason:** Interesting but not critical for P0-P5 workflows; consider for future

### Full Dashboard UI
- **Source:** `neural-memory/dashboard/`
- **Status:** ❌ rejected
- **Reason:** MCP tools + CLI sufficient; OpenClaw has no built-in UI layer

### Telemetry / Metrics Infrastructure
- **Source:** `honcho/src/telemetry/` Prometheus/Sentry
- **Status:** ❌ rejected (for now)
- **Reason:** Basic diagnostics tools sufficient; full telemetry is overkill for current scale

---

## Upgrade Path Recommendations

When considering adopting more upstream features, prioritize:

1. **Sprint 2 candidates:**
   - `neural-memory` spreading activation (lightweight SQLite version)
   - `neural-memory` activation path explanation

2. **Sprint 3 candidates:**
   - `honcho` peer card v2 with evidence
   - `honcho` session digest improvements

3. **Sprint 4 candidates:**
   - `mempalace` auto-place hierarchy
   - `mempalace` conversation/project mining

4. **Sprint 5 candidates:**
   - `neural-memory` consolidation (dedup/merge/promote)
   - Basic observability/health reporting

---

**Maintenance Note:**
When upstream repos (neural-memory/honcho/mempalace) release significant updates, review this lineage doc and evaluate:
- New features worth adopting
- Breaking changes affecting inspired implementations
- Bug fixes that should be backported

Last updated: 2026-06-15 (Sprint 1 - Documentation Hardening)
