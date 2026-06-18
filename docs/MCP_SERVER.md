# Super Memory MCP Server

Super Memory includes a local stdio MCP server so MCP-compatible agents can use it directly, similar in spirit to `neural-memory` MCP tooling, while still preserving Super Memory's canonical-first design.

## Important guardrail

This is **project development only**. Do not apply/register this MCP server into this machine's active OpenClaw config unless Boss explicitly gives a later instruction.

## Run

From the project virtualenv:

```bash
super-memory-mcp --stdio
```

Safe default profile:

```bash
super-memory-mcp --stdio --profile normal
```

Admin/development profile:

```bash
super-memory-mcp --stdio --profile admin
```

Environment equivalent:

```bash
SUPER_MEMORY_MCP_PROFILE=admin super-memory-mcp --stdio
```

Equivalent module form:

```bash
python -m super_memory.mcp_server --stdio
```

The server speaks newline-delimited JSON-RPC over stdio.

## MCP methods

Supported protocol methods:

- `initialize`
- `notifications/initialized`
- `ping`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`

## Tools

Super Memory follows the NeuralMemory MCP lesson: expose a narrow daily-core tool surface by default and keep structural/admin actions behind an explicit profile.

Profiles:

- `normal` default: remember, remember-batch, show, context, todo, auto, stats, health, sanitize-prompt, sanitize-auto-capture, normalize-memory, recall, prefetch, sync-turn, memory-search, memory-get, status
- `admin`: normal tools plus promotion
- `all`: every implemented tool

Admin/development profile also exposes the Phase 3 advanced intelligence tools, Phase 4 disabled-safe optional skeletons, Phase 6 cognitive orchestration tools, Phase 7 graph/reasoning/lifecycle/safe-flow tools, Phase 8 diagnostics/contract/supervised-smoke tools, and cross-agent/cross-session memory tools. These stay out of the safe normal profile to avoid surprising operators.

For a concrete cross-agent/cross-session installation and operation guide, see `docs/CROSS_AGENT_SESSION_MEMORY_SETUP.md`.

### `super_memory_remember`

Save memory through Super Memory canonical-first layer order.

Args include:

- `content` required
- `type`
- `scope`
- `agent_id`
- `session_id`
- `project`
- `tags`
- `source`
- `trust_score`
- `metadata`
- `config_path`

### `super_memory_recall`

Recall from all Super Memory layers.

Args:

- `query` required
- `limit`
- `config_path`

### `super_memory_remember_batch`

Save up to 20 memories through the same canonical-first layer order. Each item returns its own per-layer result so partial failure does not hide which layer failed.

Args:

- `memories` required array of memory objects using the same fields as `super_memory_remember`
- `config_path`

### `super_memory_show`

Show a memory by id across derived Super Memory layers. This is read-only and does not promote or mutate canonical markdown.

Args:

- `memory_id` required
- `config_path`

### `super_memory_context`

Return query-relevant or recent context from the merged Super Memory view.

Args:

- `query` optional; empty means recent records
- `limit`
- `config_path`

### `super_memory_todo`

Save a TODO memory through canonical-first layer order.

Args:

- `task` required
- `priority`
- `config_path`

### `super_memory_auto`

Extract simple memory candidates from text and optionally save them through canonical-first order. This baseline is deterministic and intentionally conservative; it does not require an embedded LLM.

Args:

- `text` required
- `save` default false
- `config_path`

### `super_memory_stats`

NeuralMemory-style stats alias for status.

Args:

- `config_path`

### `super_memory_health`

Check Super Memory consistency guardrails: canonical-first enabled and workspace markdown enabled.

Args:

- `config_path`

### `super_memory_sanitize_prompt`

Sanitize recall/prompt text by removing control characters, normalizing whitespace, redacting common secret shapes, and enforcing a length cap.

Args:

- `text` required

### `super_memory_sanitize_auto_capture`

Sanitize text before it can become a stored auto-capture memory. This uses the same deterministic safety path as prompt sanitization with a memory-sized cap.

Args:

- `text` required

### `super_memory_normalize_memory`

Normalize an external memory payload without saving it. This folds schema aliases such as `agentId` → `agent_id`, `sessionId` → `session_id`, `memoryType` → `type`, and `memoryScope` → `scope`; canonicalizes `type`/`scope`; sanitizes content/tags/metadata; clamps trust score; and moves unknown top-level keys into `metadata.dropped_fields` for auditability.

Args:

- `memory` required object
- `auto_capture` default false

### `super_memory_prefetch`

Merged/deduped prompt prefetch recall.

Args:

- `query` required
- `limit`
- `config_path`

### `super_memory_sync_turn`

Save compact multi-agent conversation turn memory.

Args:

- `agent_id`
- `session_id`
- `user_message`
- `assistant_message`
- `project`
- `metadata`
- `config_path`

### `super_memory_memory_search`

OpenClaw `memory_search`-compatible result payload.

Args:

- `query` required
- `max_results`
- `min_score`
- `corpus`
- `config_path`

### `super_memory_memory_get`

OpenClaw `memory_get`-compatible read from virtual Super Memory paths or workspace markdown files.

Args:

- `path` required
- `from_line`
- `lines`
- `corpus`
- `config_path`

### `super_memory_promote`

Promote an item into `MEMORY.md` and matching register.

Profile: `admin` / `all` only.

Args:

- `memory_id` required
- `config_path`

### `super_memory_status`

Return local status and counts.

Args:

- `config_path`

## Phase 3 advanced intelligence tools

Available in `admin` / `all` MCP profiles:

- `super_memory_conflicts`
- `super_memory_provenance`
- `super_memory_source`
- `super_memory_version`
- `super_memory_pin`
- `super_memory_consolidate`
- `super_memory_gaps`
- `super_memory_explain`
- `super_memory_situation`
- `super_memory_reflex`
- `super_memory_boundaries`

These tools currently provide deterministic baseline behavior and safe event/audit records. They do not pretend to run a heavyweight contradiction model or destructive consolidation pass unless those backends are explicitly added later.

## Phase 4 optional/heavy skeletons

Available in `admin` / `all` MCP profiles as disabled-safe stubs:

- `super_memory_train`
- `super_memory_import`
- `super_memory_index`
- `super_memory_sync`
- `super_memory_telegram_backup`
- `super_memory_visualize`
- `super_memory_store`
- `super_memory_watch`

They return `enabled=false` until explicitly configured so project development does not start daemons, cloud sync, imports, backups, or community-store actions by accident.

## Resource

### `super-memory://status`

Returns Super Memory status as JSON.

## Example JSON-RPC

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
```

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"super_memory_status","arguments":{}}}
```

## Design notes

- No Docker.
- No embedded LLM required for baseline remember/recall.
- Tools route through `super_memory.bridge`, so API/CLI/MCP behavior stays aligned.
- `config_path` allows isolated test configs without touching the active workspace DB.

## Phase 6 cognitive orchestration tools

Admin/all profiles expose the deterministic Phase 6 cognitive orchestration baseline:

- `super_memory_working_memory_get` / `super_memory_working_memory_set` — read and merge short-lived working-memory state.
- `super_memory_attention_score` — score salience, TTL, promotion candidacy, and layer routing.
- `super_memory_route_memory` — produce a normalized routed memory payload with attention metadata.
- `super_memory_parallel_save` — update working memory and, when attention warrants durable storage, run canonical-first save/projection.
- `super_memory_recall_arbitrate` — recall from layers and explain layer vote/winner policy.
- `super_memory_consolidation_cycle` — produce a bounded deterministic consolidation report; dry-run by default.
- `super_memory_conflict_resolve` — record a conflict-resolution event.
- `super_memory_promotion_candidates` — list deterministic promotion candidates.
- `super_memory_feedback_outcome` — record task/memory outcome feedback and optionally save a linked lesson/blocker.

These tools implement the Phase 6 brain-like controller model while preserving the core invariant: Workspace Markdown remains canonical truth and derived layers only enrich recall.


## Phase 7 Layer 4 completion tools

Admin/all profiles also expose a safer NeuralMemory-inspired Layer 4 baseline. These tools are still deterministic and project-local; they do not enable real external sync, cloud store, background daemons, or active OpenClaw runtime hooks.

Graph maturity:

- `super_memory_graph_stats` — count derived neurons, synapses, and fibers.
- `super_memory_graph_neighbors` — inspect graph neighbors for a neuron or memory id.
- `super_memory_graph_recall` — recall matching cognitive fibers.
- `super_memory_graph_rebuild` — rebuild the derived graph from existing SQLite memory rows.

Cognitive workflow:

- `super_memory_hypothesis_create` / `super_memory_hypothesis_get` / `super_memory_hypothesis_list`
- `super_memory_evidence_add`
- `super_memory_prediction_create` / `super_memory_prediction_list`
- `super_memory_verify_prediction`

Lifecycle hygiene:

- `super_memory_lifecycle_review`
- `super_memory_lifecycle_cache`
- `super_memory_lifecycle_tier`
- `super_memory_lifecycle_compression`
- `super_memory_reflex_status`

Safe local flows:

- `super_memory_train_local` — train from `.md` / `.txt` under `workspace_root` only.
- `super_memory_import_local` — import `.md` / `.txt` / `.json` / `.jsonl` under `workspace_root` only.
- `super_memory_watch_scan` — one-shot scan manifest; no daemon.
- `super_memory_sync_status` — status-only; cloud sync disabled.
- `super_memory_store_status` — status-only; community store disabled.

Invariant: Workspace Markdown remains canonical truth. Phase 7 graph/cognitive/lifecycle/store outputs are derived projections or audit/status surfaces unless they call the same canonical-first save path.

### Phase 8 live-readiness tools

Admin/all profiles expose Phase 8 qualification helpers:

- `super_memory_diagnostics` — returns a JSON dashboard for canonical-first health, sqlite state, graph projection availability, lifecycle review, safe optional feature status, watch/ingest manifest counts, and warnings.
- `super_memory_memory_slot_contract` — runs a no-live-config memory-slot contract: save → canonical reference → memory_search → memory_get → show → graph projection/recall.
- `super_memory_mcp_contract` — verifies the MCP tool exposure contract for the selected profile.
- `super_memory_supervised_runtime_smoke` — local supervised runtime smoke that checks API/MCP/plugin syntax/contracts without writing active OpenClaw config.

These tools are project-local qualification aids. They do not apply Super Memory to the live OpenClaw runtime.
