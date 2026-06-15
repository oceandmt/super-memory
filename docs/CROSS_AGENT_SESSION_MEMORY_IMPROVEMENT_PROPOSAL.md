# Cross-Agent & Cross-Session Memory Improvement Proposal

Created: 2026-06-14  
Project: Super-Memory

## Current Gaps

### Cross-agent memory
- Provenance exists through `agent_id`, `agent:*` tags, and Honcho `observer_peer_id`.
- Missing easy cross-agent query routes, for example “what did Alex remember about X?”.
- Missing structured handoff bundles between Lucas/Alex/Max/Isol.
- Missing cross-agent contradiction/conflict detection.

### Cross-session memory
- Honcho tables exist, but real work sessions are not yet consistently captured.
- Boss peer model is sparse compared with the amount of existing durable memory.
- No timeline/evolution queries across sessions yet.
- No scheduled cross-session dialectic synthesis.

## Recommended Roadmap

## Phase A — Quick wins

### A1. Auto-capture real sessions into Honcho
Hook the Super-Memory save path so every durable Boss-facing turn can also create Honcho events and optionally run shallow dialectic analysis.

Expected result:
- `honcho_events` grows from real work, not only tests.
- Boss peer model improves automatically over time.
- Cross-session context becomes useful without manual migration.

Suggested tool/API behavior:
- `super_memory_honcho_capture_turn(user_message, assistant_message, session_id, peer_id='boss', agent_id='lucas')`
- Internally saves user/agent events and runs `honcho_analyze_turn(depth=1, save=True)` when enabled.

### A2. Backfill Boss peer profile from existing memory
One-time migration from `MEMORY.md`, daily memory, and registers into Honcho peer facts.

Expected result:
- Boss peer profile becomes useful immediately.
- `honcho_ask` can answer preference/workflow questions based on existing canon.

## Phase B — Cross-agent/session query layer

### B1. Cross-agent recall API
Add queries filtered by agent provenance.

Suggested tools:
- `super_memory_cross_agent_recall(query, agent_id, limit=10)`
- `super_memory_cross_agent_honcho_ask(query, observer_agent, about_peer='boss')`
- `super_memory_cross_agent_summary(agent_id, days=30)`

Expected result:
- Lucas can ask what Alex/Max/Isol remembered or concluded.
- Provenance remains explicit and auditable.

### B2. Session timeline and evolution tools
Add temporal queries over Honcho events and memory records.

Suggested tools:
- `super_memory_session_timeline(peer_id='boss', days=30, limit=20)`
- `super_memory_session_evolution(query, peer_id='boss', sessions=5)`
- `super_memory_session_compare(session_a, session_b, query=None)`

Expected result:
- Can answer how preferences, blockers, and decisions changed across sessions.

### B3. Cross-agent handoff bundles
Create a structured memory handoff object for delegation.

Suggested tools:
- `super_memory_handoff_create(to_agent, task, query=None, memory_ids=None)`
- `super_memory_handoff_receive(bundle_id)`
- `super_memory_handoff_status(bundle_id)`

Expected result:
- Delegated agents receive compact relevant context.
- Handoff provenance is stored in Honcho and the canonical memory layer.

## Phase C — Consolidation intelligence

### C1. Shared knowledge tier
Implement a stronger `scope:shared` query path.

Expected result:
- Shared Boss preferences/doctrine can be read by all agents.
- Avoids duplicating the same memory under Lucas/Alex/Max/Isol.

### C2. Cross-agent conflict detection
During consolidation, detect likely contradictions across agents.

Suggested tool:
- `super_memory_cross_agent_conflicts(action='list|check|resolve')`

Expected result:
- If Lucas and Alex remember contradictory facts, the system flags it.

### C3. Scheduled cross-session synthesis
Run weekly or on-demand dialectic synthesis across Honcho events.

Suggested tool:
- `super_memory_cross_session_synthesis(peer_id='boss', window_days=30, depth=3)`

Expected result:
- High-confidence stable preferences and evolving priorities are distilled into conclusions.

## Priority Recommendation

1. Implement A1 auto-capture.
2. Implement A2 Boss profile backfill.
3. Implement B1 cross-agent recall.
4. Implement B2 session timeline/evolution.
5. Implement B3 handoff bundles.
6. Implement C1 shared scope query.
7. Implement C3 scheduled synthesis.
8. Implement C2 conflict detection.

## Suggested Implementation Order

### Sprint 1
- `cross_agent.py` query helpers.
- `session_timeline.py` helpers.
- new MCP tools for cross-agent recall and session timeline.
- backfill script for Boss profile.

### Sprint 2
- capture hook integration.
- handoff bundle table and tools.
- basic end-to-end tests.

### Sprint 3
- shared scope recall policy.
- scheduled synthesis and conflict checks.
- benchmark additions for cross-agent recall/session evolution.

## Success Metrics

- Boss peer profile has at least 20 high-confidence facts/preferences after backfill.
- Real Honcho sessions grow on each durable Boss-facing turn.
- Cross-agent recall can filter Lucas/Alex/Max/Isol correctly.
- Session timeline returns chronological summaries across at least 5 real sessions.
- Handoff bundle can be created and consumed without losing provenance.
- Shared scope recall includes shared doctrine while preserving agent-local boundaries.
