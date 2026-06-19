# Super Memory v0.1.1 Deep Qualification Report

Date: 2026-06-19 Asia/Saigon
Job: deep-research, deep-qualify, deep-audit, deep-test, deep-debug local installed OpenClaw `super-memory`
Scope: OpenClaw installed runtime, local checkout `projects/super-memory-github`, GitHub `oceandmt/super-memory`, and live Super Memory SQLite state.

## Executive Summary

PASS. The local OpenClaw-installed `super-memory` runtime is synced with the local GitHub checkout and the upstream GitHub release/tag `v0.1.1`. The cleanup/runtime bug class around `v_session_health` / `honcho_events_legacy_notnull` is fixed and verified at code, CLI, MCP, database, and test-suite levels.

No blocking runtime defects were found.

## Version / Sync Verification

- Installed distribution: `super-memory==0.1.1`
- Installed venv: `/home/oceandmt/.openclaw/venvs/super-memory-cli`
- Installed package import path from neutral cwd: `/home/oceandmt/.openclaw/venvs/super-memory-cli/lib/python3.12/site-packages/super_memory/__init__.py`
- Installed direct URL metadata:
  - URL: `https://github.com/oceandmt/super-memory.git`
  - requested revision: `v0.1.1`
  - commit: `7442a95aec42a2519df834f8e78f824ee81ced46`
- Local checkout: `/home/oceandmt/.openclaw/workspace/projects/super-memory-github`
- Local `HEAD`: `7442a95aec42a2519df834f8e78f824ee81ced46`
- `origin/master`: `7442a95aec42a2519df834f8e78f824ee81ced46`
- GitHub remote `master`: `7442a95aec42a2519df834f8e78f824ee81ced46`
- Git tag `v0.1.1`: `7442a95aec42a2519df834f8e78f824ee81ced46`
- GitHub release: <https://github.com/oceandmt/super-memory/releases/tag/v0.1.1>
- Local repo working tree at verification time: clean.

## Runtime / Tool Exposure

Verified from neutral cwd using the OpenClaw installed venv:

- `dist_version`: `0.1.1`
- MCP `SERVER_INFO.version`: `0.1.1`
- total MCP tools in runtime registry: `165`
- normal profile tool count: `18`
- `super_memory_cleanup` present in full registry: yes
- `super_memory_cleanup` present in normal profile: yes
- `super_memory_cleanup` present in admin profile: yes
- CLI exposes `cleanup`: yes

## Installed Package vs Checkout File Hashes

Spot-checked critical runtime files between the installed site-packages copy and `projects/super-memory-github` checkout:

- `api.py`: MATCH
- `bridge.py`: MATCH
- `cleanup.py`: MATCH
- `cli.py`: MATCH
- `config.py`: MATCH
- `mcp_server.py`: MATCH
- `migrations.py`: MATCH
- `models.py`: MATCH
- `service.py`: MATCH
- `storage.py`: MATCH

## Database / Cleanup Verification

Live MCP cleanup result against `super-memory.yaml`:

- cleanup `ok`: true
- migration `ok`: true
- migration `changed`: `[]`
- migration `change_count`: `0`
- `v_session_health`: `ok`
- `PRAGMA quick_check`: `ok`

Installed CLI cleanup smoke:

- command: `super-memory cleanup --config super-memory.yaml --json-out`
- result: `ok=True`
- `v_session_health=ok`

## Deep Test / Audit Gates

Log artifact: `reports/deep-qualify-20260619-0905.log`

Passed gates:

- SQL safety:
  - `SQL_SAFETY_OK`
  - `Checked 79 files, no f-string SQL patterns found.`
- Tool contracts:
  - `TOOL_CONTRACTS_OK`
  - `Verified 88 manifest contracts, 138 MCP tools, 21 P0-P5 tools.`
- Focused regression / snapshot / SQL safety tests:
  - `7 passed in 4.94s`
- Full pytest suite:
  - `288 passed, 11 skipped, 1 warning in 715.40s`
- CLI doctor:
  - exit code `0`
- CLI cleanup:
  - exit code `0`
- Local audit script:
  - `[OK] super-memory audit passed (21 modules, 36 tools, all healthy)`

## MCP Diagnostics

MCP diagnostics returned `ok=true`.

Current live status snapshot:

- total memories: `8868`
- layers:
  - `workspace_markdown`: `2607`
  - `mempalace`: `2087`
  - `honcho`: `2087`
  - `neural_memory`: `2087`
- graph edges / cognitive synapses: `44658`
- cognitive neurons: `12468`
- cognitive fibers: `2606`
- palace drawers: `2279`
- Honcho events: `2115`

Cross-layer health:

- verdict: `pass`
- active ids: `2368`
- full 4-layer coverage: `1848`
- full 4-layer coverage pct: `78.0%`
- pending canonical sync: `0`
- sqlite-only ids: `0`
- content drift count: `0`
- orphan projections total: `0`
- issues: `[]`

MCP contract:

- profile: `admin`
- exposed tool count: `138`
- required tools present: yes
- missing required tools: `[]`
- transport: `in_process_mcp_handle`, `ok=true`

## Findings

### Blocking issues

None.

### Non-blocking observations

1. Pytest warning:
   - `StarletteDeprecationWarning`: FastAPI/Starlette testclient warns about `httpx` and suggests `httpx2`.
   - This is dependency deprecation noise, not a current failure.

2. Lifecycle diagnostic reports duplicate groups in derived memory layers.
   - Cross-layer health still passes.
   - `pending_canonical_sync=0`, `content_drift_count=0`, and `orphan_projections_total=0`.
   - Treat as future hygiene/consolidation work, not a release blocker.

3. Full 4-layer coverage is `78.0%`.
   - This is not reported as an issue by the health checker.
   - It is useful as a monitoring metric for future consolidation/backfill, not a current defect.

## Conclusion

The OpenClaw installed `super-memory` runtime is fully synchronized with `projects/super-memory-github` and GitHub `oceandmt/super-memory` release `v0.1.1` at commit `7442a95aec42a2519df834f8e78f824ee81ced46`.

The official cleanup tool is present and works through both MCP and CLI. The `v_session_health` stale-reference bug is verified fixed. Deep qualification, audit, test, and runtime smoke checks pass.
