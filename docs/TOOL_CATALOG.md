# Super-Memory Tool Catalog

**Total Tools:** 138
**Generated:** 2026-06-15
**Version:** 0.1.1

## Tools by Category

### Cognitive (7 tools)

#### `super_memory_evidence_add`

**Description:** Add evidence for/against a hypothesis.

**Profiles:** admin

**Parameters:**
- ✅ `hypothesis_id` (string): 
- ✅ `content` (string): 
- ⚪ `direction` (string): 
- ⚪ `weight` (number): 
- ⚪ `config_path` (string): 

---

#### `super_memory_hypothesis_create`

**Description:** Create a deterministic cognitive hypothesis.

**Profiles:** admin

**Parameters:**
- ✅ `content` (string): 
- ⚪ `confidence` (number): 
- ⚪ `tags` (array): 
- ⚪ `config_path` (string): 

---

#### `super_memory_hypothesis_get`

**Description:** Get hypothesis detail with evidence/predictions.

**Profiles:** admin

**Parameters:**
- ✅ `hypothesis_id` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_hypothesis_list`

**Description:** List hypotheses.

**Profiles:** admin

**Parameters:**
- ⚪ `status` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_prediction_create`

**Description:** Create a falsifiable prediction.

**Profiles:** admin

**Parameters:**
- ✅ `content` (string): 
- ⚪ `confidence` (number): 
- ⚪ `hypothesis_id` (string): 
- ⚪ `deadline` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_prediction_list`

**Description:** List predictions.

**Profiles:** admin

**Parameters:**
- ⚪ `status` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_verify_prediction`

**Description:** Verify a prediction as correct/wrong.

**Profiles:** admin

**Parameters:**
- ✅ `prediction_id` (string): 
- ✅ `outcome` (string): 
- ⚪ `content` (string): 
- ⚪ `config_path` (string): 

---

### Core (22 tools)

#### `super_memory_auto`

**Description:** Extract simple memory candidates from text and optionally save them canonical-first.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `text` (string): 
- ⚪ `save` (boolean): 
- ⚪ `config_path` (string): 

---

#### `super_memory_auto_handoff_on_spawn`

**Description:** Create a spawn handoff with extra context

**Profiles:** admin

**Parameters:**
- ✅ `from_agent` (string): 
- ✅ `to_agent` (string): 
- ✅ `objective` (string): 
- ⚪ `constraints` (object): 
- ⚪ `session_id` (string): 
- ⚪ `context_files` (array): 
- ⚪ `memory_limit` (integer): 

---

#### `super_memory_context`

**Description:** Get recent or query-relevant Super Memory context from the merged layer view.

**Profiles:** user, admin, readonly

**Parameters:**
- ⚪ `query` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_diagnostics`

**Description:** Phase 8 diagnostics dashboard for canonical-first, sqlite, graph, lifecycle, and safe optional states.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_health`

**Description:** Check Super Memory consistency guardrails: canonical-first and workspace markdown enabled.

**Profiles:** user, admin, readonly

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_memory_get`

**Description:** OpenClaw memory_get-compatible read from Super Memory virtual paths or workspace files.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `path` (string): 
- ⚪ `from_line` (integer): 
- ⚪ `lines` (integer): 
- ⚪ `corpus` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_memory_search`

**Description:** OpenClaw memory_search-compatible recall payload from Super Memory.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `query` (string): 
- ⚪ `max_results` (integer): 
- ⚪ `min_score` (number): 
- ⚪ `corpus` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_normalize_memory`

**Description:** Normalize a memory payload schema without saving it.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `memory` (object): 
- ⚪ `auto_capture` (boolean): 

---

#### `super_memory_prefetch`

**Description:** Merged/deduped Super Memory recall for prompt prefetch.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `query` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_promote`

**Description:** Promote a memory to MEMORY.md and the matching register.

**Profiles:** admin

**Parameters:**
- ✅ `memory_id` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_promote_to_shared`

**Description:** Promote a memory to shared scope

**Profiles:** admin

**Parameters:**
- ✅ `memory_id` (string): 

---
#### `super_memory_recall`

**Description:** Recall memories from Super Memory layers.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `query` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_recall_arbitrate`

**Description:** Recall from layers and explain layer arbitration.

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_remember`

**Description:** Save a memory through Super Memory canonical-first layer order.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `content` (string): 
- ⚪ `type` (string): 
- ⚪ `scope` (string): 
- ⚪ `agent_id` (string): 
- ⚪ `session_id` (string): 
- ⚪ `project` (string): 
- ⚪ `tags` (array): 
- ⚪ `source` (string): 
- ⚪ `trust_score` (number): 
- ⚪ `metadata` (object): 
- ⚪ `config_path` (string): 

---

#### `super_memory_remember_batch`

**Description:** Save multiple memories through the same canonical-first layer order; partial failures stay per item.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `memories` (array): 
- ⚪ `config_path` (string): 

---

#### `super_memory_sanitize_auto_capture`

**Description:** Sanitize text before auto-capture storage.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `text` (string): 

---

#### `super_memory_sanitize_prompt`

**Description:** Sanitize recall/prompt text by redacting common secrets and normalizing whitespace/control characters.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `text` (string): 

---

#### `super_memory_show`

**Description:** Show a memory by id across derived Super Memory layers without changing canonical markdown.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `memory_id` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_stats`

**Description:** Alias of status for neural-memory-style stats consumers.

**Profiles:** user, admin, readonly

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_status`

**Description:** Show Super Memory local status.

**Profiles:** user, admin, readonly

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_sync_turn`

**Description:** Save a compact multi-agent conversation turn event.

**Profiles:** user, admin, readonly

**Parameters:**
- ⚪ `agent_id` (string): 
- ⚪ `session_id` (string): 
- ⚪ `user_message` (string): 
- ⚪ `assistant_message` (string): 
- ⚪ `project` (string): 
- ⚪ `metadata` (object): 
- ⚪ `config_path` (string): 

---

#### `super_memory_todo`

**Description:** Save a TODO memory through canonical-first layer order.

**Profiles:** user, admin, readonly

**Parameters:**
- ✅ `task` (string): 
- ⚪ `priority` (integer): 
- ⚪ `config_path` (string): 

---

### Cross Agent (6 tools)

#### `super_memory_cross_agent_compare`

**Description:** Compare two agents' knowledge

**Profiles:** admin

**Parameters:**
- ✅ `agent_a` (string): 
- ✅ `agent_b` (string): 
- ✅ `query` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_cross_agent_conflicts`

**Description:** List/check/resolve cross-agent conflicts

**Profiles:** admin

**Parameters:**
- ⚪ `action` (string): 
- ⚪ `topic` (string): 
- ⚪ `limit` (integer): 
- ⚪ `conflict_id` (string): 
- ⚪ `resolution` (string): 

---

#### `super_memory_cross_agent_honcho_ask`

**Description:** Query Honcho events by observer agent

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ✅ `observer_agent` (string): 
- ⚪ `about_peer` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_cross_agent_recall`

**Description:** Query memories by agent

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ✅ `agent_id` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_cross_agent_report`

**Description:** Per-agent activity report

**Profiles:** admin

**Parameters:**
- ⚪ `days` (integer): 

---

#### `super_memory_cross_agent_summary`

**Description:** Agent activity summary

**Profiles:** admin

**Parameters:**
- ⚪ `agent_id` (string): 
- ⚪ `days` (integer): 

---

### Cross Session (5 tools)

#### `super_memory_capture_event`

**Description:** Capture a Honcho event

**Profiles:** admin

**Parameters:**
- ✅ `content` (string): 
- ⚪ `session_id` (string): 
- ⚪ `observer_peer_id` (string): 
- ⚪ `observed_peer_id` (string): 
- ⚪ `workspace` (string): 
- ⚪ `source` (string): 
- ⚪ `metadata` (object): 
- ⚪ `analyze` (boolean): 

---

#### `super_memory_capture_turn`

**Description:** Capture a user/assistant turn

**Profiles:** admin

**Parameters:**
- ✅ `user_message` (string): 
- ⚪ `assistant_message` (string): 
- ⚪ `session_id` (string): 
- ⚪ `observer_peer_id` (string): 
- ⚪ `observed_peer_id` (string): 
- ⚪ `analyze` (boolean): 

---

#### `super_memory_cross_session_synthesis`

**Description:** Synthesize Honcho events across sessions

**Profiles:** admin

**Parameters:**
- ⚪ `peer_id` (string): 
- ⚪ `window_days` (integer): 
- ⚪ `depth` (integer): 

---

#### `super_memory_list_agents`

**Description:** List all agent IDs

**Profiles:** admin

---

#### `super_memory_shared_recall`

**Description:** Recall shared-scope memories

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `limit` (integer): 

---

### Graph (5 tools)

#### `super_memory_graph_neighbors`

**Description:** List graph neighbors for a neuron or memory id.

**Profiles:** admin

**Parameters:**
- ✅ `id` (string): 
- ⚪ `direction` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_graph_rebuild`

**Description:** Rebuild derived Layer 4 graph from SQLite memories.

**Profiles:** admin

**Parameters:**
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_graph_recall`

**Description:** Recall cognitive fibers from Layer 4 graph.

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_graph_stats`

**Description:** Show Layer 4 neuron/synapse/fiber counts.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_spreading_activation_recall`

**Description:** Neural-memory-style spreading activation recall through the cognitive graph.

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `depth` (integer): 
- ⚪ `top_k` (integer): 
- ⚪ `seed_limit` (integer): 
- ⚪ `config_path` (string): 

---

### Honcho (7 tools)

#### `super_memory_honcho_analyze_turn`

**Description:** Run dialectic analysis on a turn and optionally update peer model

**Profiles:** admin

**Parameters:**
- ✅ `user_message` (string): 
- ⚪ `assistant_message` (string): 
- ⚪ `peer_id` (string): 
- ⚪ `session_id` (string): 
- ⚪ `depth` (integer): 
- ⚪ `save` (boolean): 

---

#### `super_memory_honcho_ask`

**Description:** Ask about a peer using local Honcho peer model, conclusions, and messages

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `about_peer` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_honcho_conclude`

**Description:** Create/list/delete conclusions about a peer

**Profiles:** admin

**Parameters:**
- ⚪ `content` (string): 
- ⚪ `about_peer` (string): 
- ⚪ `delete_id` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_honcho_context`

**Description:** Build Honcho-style session context block

**Profiles:** admin

**Parameters:**
- ⚪ `session_id` (string): 
- ⚪ `peer_id` (string): 
- ⚪ `max_tokens` (integer): 

---

#### `super_memory_honcho_profile`

**Description:** Read or update local Honcho peer profile

**Profiles:** admin

**Parameters:**
- ⚪ `peer_id` (string): 
- ⚪ `role` (string): 
- ⚪ `facts` (array): 
- ⚪ `merge` (boolean): 

---

#### `super_memory_honcho_search`

**Description:** Search local Honcho messages and conclusions

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `peer_id` (string): 
- ⚪ `session_id` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_honcho_sessions`

**Description:** List Honcho sessions with event counts

**Profiles:** admin

**Parameters:**
- ⚪ `workspace` (string): 
- ⚪ `limit` (integer): 

---

### Knowledge Mgmt (28 tools)

#### `super_memory_boundaries`

**Description:** List or save domain boundary memory.

**Profiles:** admin

**Parameters:**
- ⚪ `domain` (string): 
- ⚪ `content` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_conflicts`

**Description:** Detect/list deterministic conflict candidates.

**Profiles:** admin

**Parameters:**
- ⚪ `content` (string): 
- ⚪ `memory_id` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_consolidate`

**Description:** Record a safe non-destructive consolidation event.

**Profiles:** admin

**Parameters:**
- ⚪ `strategy` (string): 
- ⚪ `dry_run` (boolean): 
- ⚪ `config_path` (string): 

---

#### `super_memory_explain`

**Description:** Explain relationship by merged recall path.

**Profiles:** admin

**Parameters:**
- ⚪ `from_entity` (string): 
- ⚪ `to_entity` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_gaps`

**Description:** Detect/record a knowledge gap event.

**Profiles:** admin

**Parameters:**
- ⚪ `topic` (string): 
- ⚪ `action` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_import`

**Description:** Phase 4 optional/heavy import skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_import_local`

**Description:** Import local markdown/text/json/jsonl under workspace only.

**Profiles:** admin

**Parameters:**
- ✅ `path` (string): 
- ⚪ `source_name` (string): 
- ⚪ `recursive` (boolean): 
- ⚪ `limit` (integer): 
- ⚪ `save` (boolean): 
- ⚪ `config_path` (string): 

---

#### `super_memory_index`

**Description:** Phase 4 optional/heavy index skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_index_local`

**Description:** Index code symbols/imports under workspace only.

**Profiles:** admin

**Parameters:**
- ✅ `path` (string): 
- ⚪ `extensions` (array): 
- ⚪ `recursive` (boolean): 
- ⚪ `limit` (integer): 
- ⚪ `save` (boolean): 
- ⚪ `config_path` (string): 

---

#### `super_memory_index_status`

**Description:** Show local code index manifest status.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_pin`

**Description:** Record pin/unpin intent for a memory.

**Profiles:** admin

**Parameters:**
- ⚪ `memory_id` (string): 
- ⚪ `action` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_provenance`

**Description:** Trace/verify/approve memory provenance.

**Profiles:** admin

**Parameters:**
- ⚪ `memory_id` (string): 
- ⚪ `action` (string): 
- ⚪ `actor` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_reflex`

**Description:** Record reflex pin/unpin intent for a memory.

**Profiles:** admin

**Parameters:**
- ⚪ `memory_id` (string): 
- ⚪ `action` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_reflex_status`

**Description:** Show reflex audit events and missing refs.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_situation`

**Description:** Return current memory situation summary.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_source`

**Description:** Register an external source metadata record.

**Profiles:** admin

**Parameters:**
- ⚪ `name` (string): 
- ⚪ `source_type` (string): 
- ⚪ `version` (string): 
- ⚪ `status` (string): 
- ⚪ `metadata` (object): 
- ⚪ `config_path` (string): 

---

#### `super_memory_store`

**Description:** Phase 4 optional/heavy store skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_store_status`

**Description:** Show store status only; community store disabled.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_sync`

**Description:** Phase 4 optional/heavy sync skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_sync_archive_to_honcho`

**Description:** Sync a session archive's decisions/blockers as Honcho conclusions

**Profiles:** admin

**Parameters:**
- ✅ `session_id` (string): 
- ⚪ `observer_peer_id` (string): 

---

#### `super_memory_sync_status`

**Description:** Show sync status only; cloud disabled.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_telegram_backup`

**Description:** Phase 4 optional/heavy telegram_backup skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_train`

**Description:** Phase 4 optional/heavy train skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_train_local`

**Description:** Train from local text/rich docs under workspace only.

**Profiles:** admin

**Parameters:**
- ✅ `path` (string): 
- ⚪ `domain_tag` (string): 
- ⚪ `recursive` (boolean): 
- ⚪ `limit` (integer): 
- ⚪ `save` (boolean): 
- ⚪ `config_path` (string): 

---

#### `super_memory_version`

**Description:** Create/list lightweight memory version snapshots.

**Profiles:** admin

**Parameters:**
- ⚪ `action` (string): 
- ⚪ `name` (string): 
- ⚪ `description` (string): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_visualize`

**Description:** Phase 4 optional/heavy visualize skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_watch`

**Description:** Phase 4 optional/heavy watch skeleton; disabled unless explicitly configured.

**Profiles:** admin

**Parameters:**
- ⚪ `params` (object): 

---

#### `super_memory_watch_scan`

**Description:** One-shot file watch scan; no daemon.

**Profiles:** admin

**Parameters:**
- ✅ `directory` (string): 
- ⚪ `recursive` (boolean): 
- ⚪ `limit` (integer): 
- ⚪ `save` (boolean): 
- ⚪ `config_path` (string): 

---

### Lifecycle (4 tools)

#### `super_memory_lifecycle_cache`

**Description:** Manage local activation cache status/save/load/clear.

**Profiles:** admin

**Parameters:**
- ⚪ `action` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_lifecycle_compression`

**Description:** Review/mark compression candidates without truncating content.

**Profiles:** admin

**Parameters:**
- ⚪ `action` (string): 
- ⚪ `dry_run` (boolean): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_lifecycle_review`

**Description:** Review lifecycle hygiene.

**Profiles:** admin

**Parameters:**
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_lifecycle_tier`

**Description:** Evaluate/apply deterministic memory tiers.

**Profiles:** admin

**Parameters:**
- ⚪ `action` (string): 
- ⚪ `dry_run` (boolean): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

### Mempalace (9 tools)

#### `super_memory_palace_drawers`

**Description:** List palace drawers with optional spatial filters

**Profiles:** admin

**Parameters:**
- ⚪ `wing` (string): 
- ⚪ `room` (string): 
- ⚪ `hall` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_palace_extract`

**Description:** Extract entities, concepts, domains, and relationships from text

**Profiles:** admin

**Parameters:**
- ✅ `text` (string): 

---

#### `super_memory_palace_halls`

**Description:** List palace halls, optionally filtered by wing/room

**Profiles:** admin

**Parameters:**
- ⚪ `wing` (string): 
- ⚪ `room` (string): 

---

#### `super_memory_palace_load_layer`

**Description:** Load a specific memory layer (1=verbatim, 2=structured, 3=spatial, 4=compressed)

**Profiles:** admin

**Parameters:**
- ✅ `layer` (integer): 
- ⚪ `query` (string): 
- ⚪ `wing` (string): 
- ⚪ `room` (string): 
- ⚪ `hall` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_palace_rooms`

**Description:** List palace rooms, optionally filtered by wing

**Profiles:** admin

**Parameters:**
- ⚪ `wing` (string): 

---

#### `super_memory_palace_search`

**Description:** Search memories within spatial scope (wing/room/hall)

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): Search query
- ⚪ `wing` (string): Filter by palace wing
- ⚪ `room` (string): Filter by room
- ⚪ `hall` (string): Filter by hall
- ⚪ `limit` (integer): 

---

#### `super_memory_palace_startup_context`

**Description:** Generate minimal startup context (target ≤200 tokens)

**Profiles:** admin

**Parameters:**
- ⚪ `max_tokens` (integer): 

---

#### `super_memory_palace_summary`

**Description:** Quick spatial overview (wings/rooms/halls/drawers counts)

**Profiles:** admin

---

#### `super_memory_palace_wings`

**Description:** List all palace wings with memory counts

**Profiles:** admin

---

### Neural Passthrough (1 tools)

#### `nmem_recall`

**Description:** Compatibility alias: neural-memory-style spreading activation recall.

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `depth` (integer): 
- ⚪ `top_k` (integer): 
- ⚪ `seed_limit` (integer): 
- ⚪ `config_path` (string): 

---

### Other (14 tools)

#### `super_memory_backfill_markdown_sqlite`

**Description:** Admin repair: backfill missing workspace_markdown SQLite rows from existing derived-layer records.

**Profiles:** admin

**Parameters:**
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_cleanup`

**Description:** Official safe SQLite cleanup: migrations, derived views, FTS rebuilds, transactions, optional VACUUM.

**Profiles:** user, admin, readonly

**Parameters:**
- ⚪ `config_path` (string): 
- ⚪ `vacuum` (boolean): 
- ⚪ `integrity_check` (boolean): 

---

#### `super_memory_complete_handoff_with_outcome`

**Description:** Complete handoff and record outcome

**Profiles:** admin

**Parameters:**
- ✅ `bundle_id` (string): 
- ✅ `outcome_summary` (string): 
- ⚪ `created_artifacts_json` (any): 
- ⚪ `proof_status` (string): 

---

#### `super_memory_create_handoff`

**Description:** Create an agent handoff bundle

**Profiles:** admin

**Parameters:**
- ✅ `from_agent` (string): 
- ✅ `to_agent` (string): 
- ✅ `title` (string): 
- ✅ `summary` (string): 
- ⚪ `session_id` (string): 
- ⚪ `query` (string): 
- ⚪ `memory_limit` (integer): 
- ⚪ `context` (object): 

---

#### `super_memory_cross_layer_health`

**Description:** Audit cross-layer consistency: canonical markdown rows, projection orphans, content drift, and pending sync.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_get_handoff`

**Description:** Retrieve a handoff bundle

**Profiles:** admin

**Parameters:**
- ✅ `bundle_id` (string): 

---

#### `super_memory_leitner`

**Description:** Leitner 5-box: queue|mark|schedule|stats|auto_seed.

**Profiles:** admin

**Parameters:**
- ⚪ `action` (string): 
- ⚪ `memory_id` (string): 
- ⚪ `success` (boolean): 
- ⚪ `box` (integer): 
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_leitner_due`

**Description:** Return count of Leitner-due memories without loading full queue.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_list_handoffs`

**Description:** List handoff bundles

**Profiles:** admin

**Parameters:**
- ⚪ `to_agent` (string): 
- ⚪ `status` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_load_current_handoff`

**Description:** Load latest open handoff for an agent

**Profiles:** admin

**Parameters:**
- ✅ `agent_id` (string): 

---

#### `super_memory_mcp_contract`

**Description:** Verify MCP stdio tools/list exposure for required Super Memory tools.

**Profiles:** admin

**Parameters:**
- ⚪ `profile` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_memory_slot_contract`

**Description:** Run Phase 8 memory-slot replacement contract: save/search/get/show/graph projection.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_supervised_runtime_smoke`

**Description:** Run local supervised no-live-config Phase 8 runtime smoke.

**Profiles:** admin

**Parameters:**
- ⚪ `config_path` (string): 

---

#### `super_memory_update_handoff_status`

**Description:** Update handoff status

**Profiles:** admin

**Parameters:**
- ✅ `bundle_id` (string): 
- ✅ `status` (string): 

---

### P0 P5 (13 tools)

#### `super_memory_agent_belief_report`

**Description:** List claims held by an agent on a topic

**Profiles:** admin

**Parameters:**
- ✅ `agent_id` (string): 
- ⚪ `topic` (string): 
- ⚪ `limit` (integer): 
- ⚪ `offset` (integer): 

---

#### `super_memory_create_session_summary`

**Description:** Create a compressed session archive

**Profiles:** admin

**Parameters:**
- ✅ `session_id` (string): 
- ⚪ `max_events` (integer): 

---

#### `super_memory_cross_scope_recall`

**Description:** Hybrid recall across markdown, Honcho, MemPalace, and graph layers

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `agent_scope` (string): 
- ⚪ `session_scope` (string): 
- ⚪ `source_layers` (array): 
- ⚪ `max_tokens` (integer): 
- ⚪ `limit` (integer): 

---

#### `super_memory_delegation_handoff`

**Description:** Create a delegation handoff bundle

**Profiles:** admin

**Parameters:**
- ✅ `from_agent` (string): 
- ✅ `to_agent` (string): 
- ✅ `objective` (string): 
- ⚪ `constraints` (object): 
- ✅ `session_id` (string): 

---

#### `super_memory_export_memory_graph`

**Description:** Export memory graph

**Profiles:** admin

**Parameters:**
- ⚪ `format` (string): 

---

#### `super_memory_extract_claims`

**Description:** Extract subject-predicate-object claims from a memory

**Profiles:** admin

**Parameters:**
- ✅ `memory_id` (string): 

---

#### `super_memory_find_contradictions`

**Description:** Find opposing claims across agents

**Profiles:** admin

**Parameters:**
- ✅ `topic` (string): 
- ⚪ `limit` (integer): 
- ⚪ `offset` (integer): 

---

#### `super_memory_get_session_summary`

**Description:** Get one session archive summary

**Profiles:** admin

**Parameters:**
- ✅ `session_id` (string): 

---

#### `super_memory_list_session_summaries`

**Description:** List recent session summaries

**Profiles:** admin

**Parameters:**
- ⚪ `agent_id` (string): 
- ⚪ `limit` (integer): 
- ⚪ `offset` (integer): 

---

#### `super_memory_memory_pollution_report`

**Description:** Memory pollution and quality report

**Profiles:** admin

---

#### `super_memory_post_turn_capture`

**Description:** Capture a completed turn into Honcho events

**Profiles:** admin

**Parameters:**
- ✅ `user_message` (string): 
- ✅ `assistant_message` (string): 
- ✅ `session_id` (string): 
- ✅ `agent_id` (string): 
- ✅ `workspace` (string): 

---

#### `super_memory_resolve_contradiction`

**Description:** Resolve a claim contradiction

**Profiles:** admin

**Parameters:**
- ✅ `claim_a_id` (string): 
- ✅ `claim_b_id` (string): 
- ✅ `resolution` (string): 

---

#### `super_memory_search_session_archives`

**Description:** Search archived session summaries

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `limit` (integer): 
- ⚪ `offset` (integer): 

---

### Routing (9 tools)

#### `super_memory_attention_score`

**Description:** Score memory salience and routing signals.

**Profiles:** admin

**Parameters:**
- ✅ `payload` (object): 
- ⚪ `config_path` (string): 

---

#### `super_memory_conflict_resolve`

**Description:** Record a Phase 6 conflict resolution event.

**Profiles:** admin

**Parameters:**
- ✅ `conflict_id` (string): 
- ✅ `resolution` (string): 
- ⚪ `reason` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_consolidation_cycle`

**Description:** Run a bounded deterministic Phase 6 consolidation report.

**Profiles:** admin

**Parameters:**
- ⚪ `strategy` (string): 
- ⚪ `dry_run` (boolean): 
- ⚪ `config_path` (string): 

---

#### `super_memory_feedback_outcome`

**Description:** Record task/memory outcome feedback for learning.

**Profiles:** admin

**Parameters:**
- ⚪ `memory_id` (string): 
- ⚪ `success` (boolean): 
- ⚪ `outcome` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_parallel_save`

**Description:** Run Phase 6 working-memory plus canonical-first save/projection flow.

**Profiles:** admin

**Parameters:**
- ✅ `payload` (object): 
- ⚪ `config_path` (string): 

---

#### `super_memory_promotion_candidates`

**Description:** List deterministic promotion candidates.

**Profiles:** admin

**Parameters:**
- ⚪ `limit` (integer): 
- ⚪ `config_path` (string): 

---

#### `super_memory_route_memory`

**Description:** Route a memory payload using deterministic Phase 6 attention policy.

**Profiles:** admin

**Parameters:**
- ✅ `payload` (object): 
- ⚪ `config_path` (string): 

---

#### `super_memory_working_memory_get`

**Description:** Get Phase 6 short-lived working memory state.

**Profiles:** admin

**Parameters:**
- ⚪ `key` (string): 
- ⚪ `config_path` (string): 

---

#### `super_memory_working_memory_set`

**Description:** Set/merge Phase 6 short-lived working memory state.

**Profiles:** admin

**Parameters:**
- ⚪ `key` (string): 
- ✅ `payload` (object): 
- ⚪ `ttl_seconds` (integer): 
- ⚪ `config_path` (string): 

---

### Session (8 tools)

#### `super_memory_session_end_summary`

**Description:** Summarize and close a session

**Profiles:** admin

**Parameters:**
- ✅ `session_id` (string): 
- ✅ `agent_id` (string): 

---

#### `super_memory_session_evolution`

**Description:** Peer evolution across sessions

**Profiles:** admin

**Parameters:**
- ⚪ `peer_id` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_session_health`

**Description:** Session health report

**Profiles:** admin

---

#### `super_memory_session_list`

**Description:** List Honcho sessions

**Profiles:** admin

**Parameters:**
- ⚪ `workspace` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_session_search`

**Description:** Search Honcho session events

**Profiles:** admin

**Parameters:**
- ✅ `query` (string): 
- ⚪ `session_id` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_session_start_context`

**Description:** Load bounded startup context

**Profiles:** admin

**Parameters:**
- ✅ `session_id` (string): 
- ✅ `agent_id` (string): 
- ✅ `peer_id` (string): 
- ⚪ `max_tokens` (integer): 

---

#### `super_memory_session_timeline`

**Description:** Timeline of Honcho events for a session

**Profiles:** admin

**Parameters:**
- ✅ `session_id` (string): 
- ⚪ `limit` (integer): 

---

#### `super_memory_session_timeline_view`

**Description:** View session as raw, summary, decisions, or blockers

**Profiles:** admin

**Parameters:**
- ✅ `session_id` (string): 
- ⚪ `mode` (string): 

---

