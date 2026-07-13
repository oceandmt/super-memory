# Changelog

## 2.3.20 - 2026-07-13

### Fixed (E20 — report tools inflated by forgotten memories)
- **`Reports.cross_agent_report` and `Reports.session_health`'s duplicate-content query (both live MCP tools: `super_memory_cross_agent_report`, `super_memory_session_health`) counted/grouped soft-deleted memories with no guard.** 1038 soft-deleted rows inflated per-agent activity counts in `cross_agent_report`; 1019 soft-deleted rows could surface in the duplicate-content report in `session_health`. Same wrong-value class as E3/E7. Added the canonical soft-delete guard to both queries.

### Tests
- Regression suite now 55: added `TestReportsSoftDeleteRegression` (source-level guard on both functions).

### Safety
- No database files, memory contents, or private runtime config included. Change only narrows what these reports count/return.


## 2.3.19 - 2026-07-13

### Fixed (E19 — handoff outcome tool always crashed)
- **`HandoffTools.complete_handoff_with_outcome` (live MCP tool `super_memory_complete_handoff_with_outcome`) called `hashlib.sha256(...)` but `handoff.py` never imported `hashlib`.** Every call raised `NameError` — a live MCP tool that always crashed on invocation, with no test coverage catching it. Added the missing `import hashlib`.

### Tests
- Regression suite now 54: added `TestHandoffOutcomeRegression` (functional round-trip: create a handoff, complete it with an outcome, assert no crash and a memory/event were recorded).

### Safety
- No database files, memory contents, or private runtime config included. Fixes a crash only; no behavior change beyond making the tool actually work.


## 2.3.18 - 2026-07-13

### Fixed (E17, E18 — SynthesisTools: leak + always-crashing tool)

**E17 — `shared_recall` (live MCP tool `super_memory_shared_recall`) queried memories with no soft-delete guard.** Forgotten shared-scope memories could leak back into recall — same class as E4/E8/E15/E16. Added the canonical `COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1` guard.

**E18 — `promote_to_shared` (live MCP tool `super_memory_promote_to_shared`) referenced an undefined local `cur` in its return statement.** `conn.executescript(...)` doesn't return a cursor with `.rowcount`, so **every single call raised `NameError`** — a live MCP tool that always crashed on invocation, with no test coverage catching it. It also built the UPDATE via manual quote-escaping + `executescript` instead of a parameterized query (fragile, and generically risky for future edits). Rewrote as a parameterized `UPDATE ... WHERE id=?`, reading `rowcount` from the actual cursor `execute()` returns.

### Tests
- Regression suite now 53: added `TestSynthesisRegression` — a source-level guard for E17, and a functional round-trip for E18 (promote on a real id must not raise, must flip scope to 'shared'; promote on a missing id must return `ok=False` cleanly).

### Safety
- No database files, memory contents, or private runtime config included. E17 narrows recall results; E18 fixes a crash and removes manual SQL string-escaping in favor of parameterization.


## 2.3.17 - 2026-07-13

### Fixed (E16 — cross-agent recall leaks forgotten memories)
- **`CrossAgentTools.cross_agent_recall` (live MCP tool `super_memory_cross_agent_recall`) queried `memories` via both an FTS join (`_fts_search`) and a LIKE fallback with no soft-delete guard.** 287 soft-deleted `workspace_markdown` rows could leak into cross-agent recall — same class as E4/E8/E15. Added `COALESCE(json_extract(...metadata_json,'$.soft_deleted'),0) != 1` to both query paths. Verified live: recall returns 50 hits, 0 soft-deleted leaked.

### Tests
- Regression suite now 51: added `TestCrossAgentRecallSoftDeleteRegression` (source-level guard on `_fts_search` + `cross_agent_recall`).

### Safety
- No database files, memory contents, or private runtime config included. Change only narrows cross-agent recall results.


## 2.3.16 - 2026-07-13

### Fixed (E15 — REM vector recall leaks forgotten memories)
- **`rem._rem_sqlite_vec` and `rem._rem_bruteforce` (live via `bridge.rem_search`) joined `memories`↔`memory_vectors` with no soft-delete guard.** 399 soft-deleted rows retained live vectors, so REM vector recall returned forgotten memories — same leak class as E4 (semantic hydrate) and E8 (FTS). The vector delete path is best-effort, so the guard must live at query time. Added `COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0) != 1` to both REM query paths. Verified live: 0 soft-deleted vectors selectable, 1044 alive vectors still returnable.

### Tests
- Regression suite now 50: added `TestRemVectorSoftDeleteRegression` (source-level guard on both REM paths).

### Safety
- No database files, memory contents, or private runtime config included. Change only narrows REM recall results.


## 2.3.15 - 2026-07-13

### Fixed (E14 — graph rebuild resurrects forgotten memories)
- **`graph.rebuild_incremental` (live via `bridge.graph_rebuild_incremental`) selected `m.*` with no soft-delete guard**, so it re-projected soft-deleted (forgotten) memories back into the neural/graph layer as neurons/synapses/fibers — **1018 rows on the live DB**. Same resurrection class as E7 (dream) and E8 (FTS reindex): a routine graph rebuild silently undid `forget()` for the graph recall layer. Added the canonical `COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0) != 1` guard to the projection source query. (`cleanup_orphans` already filtered soft-deleted; verified unchanged.)

### Tests
- Regression suite now 49: added `TestGraphRebuildSoftDeleteRegression` (source-level guard on `rebuild_incremental`).

### Audit notes (checked, no change needed)
- `surface.py` and `StatsMixin` report raw counts, but neither is reachable from a live MCP tool — the live `super_memory_stats` routes through `bridge.stats()` → `status()`, which carries the E3 alive fix. Left as-is rather than patching dead surfaces.

### Safety
- No database files, memory contents, or private runtime config included. Change only narrows what the graph rebuild projects; it cannot expose or ingest data.


## 2.3.14 - 2026-07-13

### Enhancements (E9–E13 — hardening + self-improvement follow-ups to the E1–E8 audit)

**E9 — Centralized soft-delete guard (`models.ALIVE_SQL` / `alive_sql()`).**
The soft-delete predicate had been hand-written in bridge/cleanup/conflict/version/service and *omitted* in dream_engine (E7) and hybrid_recall (E8), each omission a real recall/stat leak. Added one canonical source of truth in `models.py` (leaf module, no circular imports) and pointed the 4 ad-hoc sites at it. Added `TestSoftDeleteGuardCentralizationRegression`: a source-level guard that fails if any known recall/stat surface (dream `rank_by_surprisal`/`detect_patterns`/`dream_engine_status`, hybrid `_search_memories`/`_search_semantic_memories`) drops the `soft_deleted` filter — catching the next E7/E8-class regression at test time.

**E10 — Hardened `reindex_fts5` against soft-delete resurrection (defense-in-depth for E8).**
`memories_fts`/`memories_cjk_fts` are external-content FTS5; `'rebuild'` repopulates them from **all** rows incl. soft-deleted. `reindex_fts5` now scrubs soft-deleted rows back out (external-content `'delete'`) after every rebuild, so a reindex can never re-expose forgotten memories to MATCH even if a query-time guard is missed. Verified on the live DB: scrubbed 1038 soft-deleted rows from CJK FTS; 0 remain MATCH-able.

**E11 — Dream insight review-before-save queue.**
`run_dream_cycle(dry_run=False)` previously saved insights straight into the canonical store. New `require_review=True` routes gate-passing insights into a `dream_pending_insights` table for explicit `dream_approve_insight` / `dream_reject_insight` (idempotent enqueue by content hash; approval persists verbatim with a `reviewed` tag, rejection never persists). Default stays `False` (backward compatible).

**E12 — Pre-commit regression hook.**
Added `pytest-injection-hydration-regression` to `.pre-commit-config.yaml` — runs the 48-test suite (~1s) before every commit, blocking the next E7/E8-class regression before it lands instead of relying on manual audit.

**E13 — Recall trigram tier before full-scan LIKE.**
`_search_memories` fell straight from FTS5 MATCH to an unindexed `content LIKE '%q%'` full table scan. It now tries the trigram `memories_cjk_fts` index first (handles CJK/substring queries the main FTS misses, and uses an index instead of scanning). The shared `filter_sql` keeps the E8 soft-delete guard on the CJK tier too.

### Tests
- Regression suite now 48 (was 42): +E9 (2), +E10 (1), +E11 (2), +E13 (1).

### Safety
- No database files, memory contents, or private runtime config included. All changes either narrow what is read/returned or add an opt-in approval gate; none can expose or auto-ingest data.


## 2.3.13 - 2026-07-13

### Fixed (E8 — recall resurrects forgotten memories after any FTS reindex)
- **`HybridRecall._search_memories` (live MCP tool `super_memory_cross_scope_recall`) queried `memories`/`memories_fts` with no soft-delete guard.** `memories_fts` is external-content FTS5 (`content=memories`). Today `forget()` scrubs FTS terms so recall *looked* safe — but `reindex_fts5('rebuild')` repopulates FTS from **all** rows including soft-deleted ones. Reproduced on a throwaway DB: after a rebuild, all 1038 soft-deleted memories become `MATCH`-able again, and unguarded recall would return them — silently undoing `forget()` on the next routine reindex. This is the same leak class as the E4 semantic fix, but latent (only triggers post-reindex), which is why the first probe didn't reproduce it.
- Added the canonical `COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0)!=1` guard to the shared `where` list, so it flows into **both** the FTS join and the LIKE fallback (via the existing `m.`-strip). Recall now filters at query time instead of depending on FTS index hygiene.
- The semantic path (`_search_semantic_memories`) already had this guard from E4; verified unchanged.

### Tests
- Regression suite now 42: added `TestHybridRecallReindexResurrectionRegression` — a source-level guard on `_search_memories` and a reproduction test that rebuilds FTS with a soft-deleted row and asserts the guarded query drops it.

### Safety
- No database files, memory contents, or private runtime config included. Change only narrows recall results; it cannot expose or ingest data.


## 2.3.12 - 2026-07-13

### Fixed (E7 — dream engine consolidated forgotten memories)
- **`dream_engine` read `memories` with no soft-delete filter in all three query sites** (`rank_by_surprisal`, `detect_patterns`, `dream_engine_status`). Two real consequences:
  1. **Correctness (data integrity):** the consolidation cycle clustered and re-consolidated **soft-deleted (forgotten) memories** into brand-new `type=insight` records — effectively resurrecting content the user had deleted. This is the memory-quality inverse of a leak: `forget()` was silently undone by the next dream cycle.
  2. **Wrong values:** `dream_engine_status()` reported raw `COUNT(*)` = 2123 while true alive = 1085 (1038 soft-deleted rows counted as live), plus inflated session/agent/last-hour counts. Same bug class as the 2.3.x `bridge.status()` fix.
- All three queries now apply the canonical `COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0` guard, matching the recall/list/stats paths.

### Tests
- Regression suite now 40: added `TestDreamEngineSoftDeleteRegression` — a source-level guard (all three fns must reference `soft_deleted`) and a live-DB guard (`dream_engine_status` must report alive, not raw).

### Safety
- No database files, memory contents, or private runtime config included. Change only narrows what the dream cycle reads; it cannot ingest new data.


## 2.3.11 - 2026-07-13

### Fixed (E6 — the .venv junk root cause flagged in 2.3.10)
- **`safe_flows.train()` / `import_local()` ingested build/vendor files as memories.** `_iter_files()` walked the target directory with no ignore guard, so a `train_local` run over a workspace containing `.venv-yt-dlp` slurped **1142 vendored dependency files** (`.dist-info/top_level.txt`, license files, etc.) into all four layers as `flow=train` "memories". This was the exact source of the 872+ alive junk rows that failed `test_no_alive_venv_junk_rows`. `_iter_files()` now skips `is_ignored_source_path()` artifacts (`.venv`, `site-packages`, `node_modules`, `.dist-info`, `.egg-info`, build/dist/cache dirs), so every flow sharing it (`train`, `import_local`) is protected at the source.

### Data
- Purged 268 canonical junk memory ids (1062 layer rows + 537 palace_drawers + 268 honcho_events + 795 cognitive_neurons + 268 ingest_manifest entries). 0 vendor-path memories remain.

### Tests
- Regression suite now 38: added `test_safe_flows_iter_files_skips_vendor_paths` (real file yielded; `.venv`/`node_modules` artifacts skipped). The pre-existing live-DB guard `test_no_alive_venv_junk_rows` now passes.

### Safety
- No database files, memory contents, or private runtime config included. The change only narrows what the local train/import flows will ingest; it cannot cause new ingestion.


## 2.3.10 - 2026-07-13

### Removed (E5 — dead + broken code, per user decision "Option A")
- Deleted `super_memory/handlers/` (8 files, 1718 lines: `core.py`, `quality.py`, `cognitive.py`, `lifecycle.py`, `graph.py`, `ops.py`, `base.py`, `__init__.py`) and `super_memory/pipeline_steps.py`. Audit confirmed: **nothing in any live entrypoint** (`mcp_server.py`, `api.py`, `bridge.py`) imports `get_all_handlers()` or this package, and it was broken anyway — **65 references to `bridge.*` functions that do not exist** (`bridge.quality_score`, `bridge.retrieval_pipeline`, `bridge.reflex_pin`, etc.), so it would crash on import if it were ever wired in. Looks like an abandoned modularization of the monolithic `mcp_server.py` (244 live tools).
- `super_memory/retrieval_pipeline.py` was investigated for the same removal but **kept**: it is live via `auto_deep.py`'s P0 module audit (`importlib.import_module`) and has its own passing test (`tests/test_retrieval_pipeline.py`).

### Fixed (found while verifying the removal was safe)
- **Fresh-DB schema drift**: `schema.sql` (the source of truth for newly-created databases via `run_migrations`) still defined `palace_drawers` with the pre-2.3.7 spatial-only shape (`id` PK, no `drawer_id`). The 2.3.7 fix updated the *migration* path (`projections/closet.py`) but not the fresh-DB schema, so every brand-new database still hit "table palace_drawers has no column named drawer_id" on save — causing 59 test failures across `test_write_contract.py` and `test_tool_dispatch_smoke.py` that only reproduced on fresh tmp_path databases, not the live migrated one. `schema.sql` now matches the migrated shape (`drawer_id` PK + backward-compatible spatial columns).
- **Test DB isolation leak**: `tests/test_cross_layer_health.py` called `bridge.remember()` / `load_config(None)` with no `tmp_path` fixture, writing real rows into the live production database on every test run. Rewrote to use the same `SuperMemoryConfig(workspace_root=tmp_path, ...)` + `monkeypatch` pattern used elsewhere in the suite. Purged 36 rows of accumulated test pollution across memories/palace_drawers/honcho_events/cognitive_neurons from the live DB.

### Known pre-existing issue (not fixed this release, flagged for follow-up)
- `tests/test_injection_and_hydration_regression.py::test_no_alive_venv_junk_rows` fails: 872 alive rows in the live DB point at `.venv-yt-dlp` vendor paths, dated back to 2026-07-12 (before this session). Confirmed to reproduce identically on pristine v2.3.9 — pre-existing, unrelated to this release. `is_ignored_source_path()` exists in `super_memory/ingest/__init__.py` and is correctly wired into `FileAdapter`, but the exact ingestion path that wrote these specific rows wasn't identified; needs its own investigation.

### Tests
- Full targeted suite green: `test_write_contract.py`, `test_retrieval_pipeline.py`, `test_cross_layer_health.py`, and `test_injection_and_hydration_regression.py` (36/37, excluding the pre-existing venv-junk issue above) all pass. Live imports (`api`, `mcp_server`, `bridge`, `auto_deep`, `retrieval_pipeline`) verified post-deletion.


## 2.3.9 - 2026-07-13

### Fixed (semantic/vector layer — E4)
- **Semantic recall leaked soft-deleted memories.** `HybridRecall._search_semantic_memories` hydrated vector hits with only `id=? AND layer=?`, no `soft_deleted` guard. The sqlite-vec index is a derived side store, so a forgotten memory whose embedding lingered could resurface through semantic recall. Hydration now filters `COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1`.
- **`forget()` never dropped the embedding**, so the vector index bloated and orphaned indefinitely. Live audit found **272 embeddings but only 14 pointing to alive rows** (112 to soft-deleted, 146 to hard-deleted/nonexistent ids). Added `bridge._drop_embedding()` (best-effort, no-op when vector disabled) and wired it into both the soft- and hard-delete branches of `forget()`.

### Data
- Purged 258 orphaned sqlite-vec embeddings (soft-deleted + nonexistent). Vector index now 14 rows, all pointing to alive `workspace_markdown` memories (0 orphans).

### Tests
- Regression suite now 37 tests: E4 adds semantic soft-delete hydration guard, `forget()` drops embedding, and `_drop_embedding` safe-no-op-when-disabled.

### Safety
- No database files, memory contents, or private runtime config included. `_drop_embedding` is best-effort and swallows failures so delete never breaks when the optional vector store is unavailable.


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
