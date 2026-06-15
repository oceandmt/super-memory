# Cross-Agent & Cross-Session Memory Optimization Review

Date: 2026-06-14

## Scope

Reference public GitHub-visible patterns around NeuralMemory-style MCP memory, Honcho, and MemPalace, then compare them to the current Super-Memory implementation and propose optimizations.

## External Patterns Reviewed

### NeuralMemory-style / agent memory systems

Common patterns from public memory systems and GitHub discussions:

- multi-tier memory: working/session, long-term, archive/profile
- cross-session search using SQLite/FTS/vector indexes
- auto-compression and session lifecycle hooks
- confidence, decay, verification, provenance, and policy-aware retrieval
- graph or relationship-based recall for multi-hop continuity
- budget-aware retrieval to avoid prompt bloat

### Honcho

Useful patterns:

- peer-centric model: user/agent peers and per-peer memory
- session event capture and context injection
- profile / peer-card concept for durable user representation
- turn sync hooks and prefetch context

Observed pitfalls:

- startup/prefetch can block if remote/provider is slow
- excessive prompt injection can become stale and token-heavy
- polluted peer memory needs maintenance/wipe/curation controls

### MemPalace

Useful patterns:

- memory palace hierarchy: wing -> room -> hall -> drawer
- low wake-up context and progressive/on-demand loading
- operator-owned/local memory sovereignty
- shared store can support multi-agent cold-start handoff
- inspectable spatial structure is good for debugging and continuity

Observed limitations:

- mostly pull-based unless the runtime enforces hooks
- no strong native decay/conflict governance by default
- spatial organization improves navigation but is not enough by itself for truth/conflict handling

## Current Super-Memory State

Completed capabilities:

- Markdown-first canonical doctrine retained.
- MemPalace projection exists through palace drawers and search/load tools.
- Honcho local peer/event/conclusion tables exist.
- Phase A+B+C added 19 cross-agent/cross-session tools:
  - cross-agent recall/summary/compare/list
  - Honcho observer-agent ask
  - session timeline/list/evolution/search
  - capture event/turn
  - handoff bundle create/get/list/status
  - cross-session synthesis
  - shared recall / promote-to-shared
  - deterministic cross-agent conflict check
- VPS deployment and integration tests passed.

Gaps still visible:

- session capture is tool-based, not runtime-enforced everywhere
- cross-agent recall is mostly LIKE/metadata filtering, not hybrid ranked retrieval
- conflict detection is deterministic placeholder, not semantic/contradiction-aware
- no automatic graph rebuild schedule yet
- no replayable session archive compression pipeline yet
- limited dashboard/inspectability for cross-agent/session memory health
- shared-scope promotion is manual and lacks review/expiry workflow
- handoff bundles work but are not yet integrated into sessions_spawn / delegation lifecycle

## Optimization Proposal

### P0: Harden Capture and Lifecycle Hooks

Goal: make cross-session memory automatic, not optional.

Implement:

- post-turn hook: capture user + assistant turns into Honcho events
- session-start hook: load bounded startup context by session/peer/project
- session-end hook: summarize session and mark action items/blockers
- delegation hook: auto-create handoff bundle when spawning cross-agent work

Acceptance:

- real Discord/Telegram session ids appear in honcho_events
- no tool-only manual capture required for normal turns
- capture failures are non-fatal and logged

### P1: Hybrid Retrieval Router

Goal: combine canonical markdown, Honcho peer context, MemPalace spatial drawers, graph recall, and SQLite FTS.

Implement `super_memory_cross_scope_recall`:

Inputs:

- query
- agent_scope: current | agent:<id> | all | shared
- session_scope: current | session:<id> | recent | all
- source_layers: markdown | honcho | mempalace | graph | all
- max_tokens

Ranking:

- exact/FTS score
- recency
- trust_score
- scope match
- agent/session match
- source authority: markdown > verified shared > Honcho/MemPalace projection > synthetic benchmark

Acceptance:

- response includes provenance and why each item was selected
- no single layer silently dominates retrieval

### P2: Semantic Conflict and Belief Evolution

Goal: turn conflict detection into a reliable governance layer.

Implement:

- normalized claim extraction from memories/events
- contradiction groups by subject/predicate/object/time validity
- status: open | accepted_both | superseded | resolved
- resolution writes provenance and optional replacement memory
- agent-level comparison report: Lucas vs Alex vs Max vs Isol

Acceptance:

- conflict tool surfaces actual candidate pairs with reason
- user can resolve conflict without deleting raw history

### P3: Session Archive and Compression

Goal: make long-running threads resumable without token bloat.

Implement:

- per-session event summary after N turns or on session end
- archive table with compressed summaries and key decisions
- searchable FTS index over raw events + summaries
- timeline views: raw, summarized, decisions-only, blockers-only

Acceptance:

- session recall still works after raw event volume grows
- startup context remains bounded

### P4: Handoff Integration

Goal: make cross-agent work recoverable.

Implement:

- auto handoff bundle on sessions_spawn with objective, constraints, relevant memories, open files, validation gates
- receiving agent loads handoff by bundle_id
- bundle completion writes outcome back into Honcho and shared memory candidate queue

Acceptance:

- a child agent can cold-start from handoff without full transcript
- completed handoff produces durable summary and proof artifacts

### P5: Inspectability Dashboard / Reports

Goal: avoid memory becoming opaque.

Implement:

- `super_memory_cross_agent_report`
- `super_memory_session_health`
- `super_memory_memory_pollution_report`
- visual export: markdown/JSON graph of agents, sessions, topics, conflicts, handoffs

Acceptance:

- operator can answer: what does each agent know, what changed this week, what is stale/conflicting, what is shared

## Recommended Roadmap

1. Implement P0 hooks + P1 `cross_scope_recall` first.
2. Upgrade conflicts from placeholder to claim-based semantic groups.
3. Add scheduled graph/session summarization cron.
4. Integrate handoff into delegation workflow.
5. Add report/dashboard tools.

## Principle

Keep Super-Memory better than upstream clones by preserving its OpenClaw-native architecture:

- Markdown-first canonical truth
- Honcho = peer/session conversation intelligence
- MemPalace = spatial projection and cold-start navigation
- NeuralMemory/graph = associative recall and belief evolution
- Super-Memory = router/governance/provenance layer that arbitrates among them
