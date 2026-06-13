# Phase 5 — OpenSandbox/OpenClaw isolated backtest

Status: project-only harness. It does not install/register anything into the active host OpenClaw runtime.

## Goal

Use OpenSandbox as an isolation layer to backtest Super Memory against a sandbox OpenClaw instance before any production memory-slot attempt.

## Safety invariants

- Dry-run by default.
- No real provider credentials.
- Do not mount the real `~/.openclaw` read-write.
- Use fixture memory only.
- Keep Phase 4 heavy features disabled: train/import/index, cloud sync, Telegram backup, visualize, store/community brain, watch daemon.
- Workspace Markdown remains canonical; derived layers stay downstream.

## Harness

Run from repo root:

```bash
python scripts/phase5_sandbox_backtest.py
```

This prints a JSON plan containing:

- prerequisite checks for `docker`, `osb`, `python`, `node`, `npm`
- sandbox image/timeout
- generated sandbox-only OpenClaw config fixture
- fixture memory content
- ordered command plan
- safety warnings

Bounded local verification:

```bash
python scripts/phase5_sandbox_backtest.py --execute
```

`--execute` currently runs only bounded local verification:

- `python -m py_compile super_memory/*.py`
- `node --check openclaw-plugin/super-memory/index.js`
- `node --check openclaw-plugin/super-memory/mcp-client.js`
- `pytest -q`

It does not yet create an OpenSandbox lifecycle automatically because the local OpenSandbox endpoint/domain/API-key details must be known first.

## Intended sandbox backtest matrix

1. Create OpenSandbox sandbox with Node 22 + Python.
2. Copy or clone this repo into sandbox workspace.
3. Install Super Memory dev dependencies.
4. Start `super-memory-api` on `127.0.0.1:8765` inside sandbox.
5. Install/run OpenClaw inside sandbox only.
6. Load the generated sandbox-only plugin config.
7. Verify plugin load.
8. Verify MCP stdio server.
9. Verify `memory_search` / `memory_get` replacement behavior.
10. Verify dynamic `/mcp-tools` proxy.
11. Verify guarded hook skeletons only after matching live OpenClaw hook APIs.
12. Verify failure isolation: canonical markdown failure skips downstream projections.
13. Verify restart persistence in sandbox-local SQLite/fixtures.
14. Confirm no writes to host OpenClaw memory or config.

## Qualification rule

Phase 5 passes only when sandbox OpenClaw can use Super Memory as an isolated memory-slot candidate without affecting host runtime state.
