# Super Memory

[![CI](https://github.com/YOUR_USERNAME/super-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/super-memory/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/super-memory.svg)](https://badge.fury.io/py/super-memory)
[![Python Versions](https://img.shields.io/pypi/pyversions/super-memory.svg)](https://pypi.org/project/super-memory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Local multi-layer memory app for OpenClaw multi-agents.

Super Memory uses the Hermes-style idea of layered agent memory as the base, with Workspace Markdown as canonical truth and local adapters for MemPalace, Honcho, and NeuralMemory-style functions.

## Requirements

- Python 3.11+
- No Docker required
- Embedded LLM is optional, not required for baseline remember/recall

## Install for local development

```bash
git clone <repo-url> super-memory
cd super-memory
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## CLI

```bash
super-memory save-order
super-memory remember "Boss prefers canonical markdown first" --type preference --scope shared --agent-id lucas --project super-memory --tag doctrine
super-memory recall canonical
super-memory memory-search canonical --json-out
super-memory memory-get memory/2026-06-13.md --from-line 1 --lines 20
```

## MCP server

Super Memory now includes a local stdio MCP server for MCP-compatible agents:

```bash
super-memory-mcp --stdio --profile normal
```

Default exposed tools include remember, remember-batch, show, context, todo, auto, stats, health, sanitize-prompt, sanitize-auto-capture, normalize-memory, recall, prefetch, sync-turn, memory-search, memory-get, and status. Admin profile additionally exposes promotion.

Guardrail: this project can be developed as an OpenClaw memory-slot replacement candidate, but do not apply/register it into this machine's active OpenClaw config unless Boss explicitly instructs that later.

## Save order

1. Workspace Markdown = canonical local truth
2. MemPalace memory functions = structured/procedural/project memory
3. Honcho memory functions = conversational participant/session memory
4. Neural Memory functions = associative/graph/semantic memory

Downstream layers are treated as derived. By default, if canonical Workspace Markdown save fails, later layers are skipped.

## Current implementation status

Implemented now:

- Python package skeleton
- CLI: `remember`, `recall`, `save-order`, `memory-search`, `memory-get`
- Layered save order
- Workspace Markdown append-only daily note backend
- SQLite deterministic adapters for MemPalace/Honcho/NeuralMemory layers
- Multi-agent provenance tags
- OpenClaw-compatible search/get shape layer
- OpenClaw plugin wrapper with guarded/non-applied capability skeleton
- MCP stdio server
- Phase 1 neural-memory-inspired daily tools: batch remember, show, context, todo, auto extraction, stats, and health
- Phase 1.1 guardrails: prompt sanitization, auto-capture sanitization, and schema normalization before save/recall flows
- Phase 2 hardening skeletons: MCP subprocess client, dynamic MCP tools/list proxy endpoint, guarded OpenClaw hook skeletons for pre-prompt context / post-agent capture / pre-compaction flush / reset flush / startup consolidation, and memory_search/memory_get contract tests
- Phase 3 advanced intelligence baseline tools: conflicts, provenance, source, version, pin, consolidate, gaps, explain, situation, reflex, and boundaries
- Phase 4 optional/heavy feature skeletons: train/import/index, cloud sync, Telegram backup, visualize, store/community brain, and watch directory daemon remain disabled-safe stubs until explicitly configured
- Phase 5 sandbox backtest harness: OpenSandbox/OpenClaw isolated test plan, sandbox-only config fixture, dry-run CLI, and safety contract tests
- Phase 6 cognitive orchestration baseline: working memory, attention scoring, memory routing, parallel save, recall arbitration, consolidation cycle, conflict resolution, promotion candidates, and feedback outcome recording
- Phase 7 Layer 4 completion baseline: derived neuron/synapse/fiber graph projection, deterministic hypothesis/evidence/prediction/verify workflow, lifecycle review/cache/tier/compression/reflex status, and workspace-only local train/import/watch scan/sync/store status flows
- Phase 8 live-readiness baseline: diagnostics dashboard, memory-slot contract smoke, MCP contract check, local supervised no-live-config runtime smoke, graph incremental rebuild/orphan cleanup, reasoning confidence/provenance history, prediction expiry, and train/import/watch dedup manifests
- Tests for save order, recall, OpenClaw compatibility, MCP, and guardrails

## OpenClaw Workspace Templates

Super Memory ships with a ready-to-use OpenClaw workspace starter pack so any OpenClaw instance can operate immediately after installing the plugin.

**Included templates**: `openclaw-plugin/super-memory/workspace-templates/`
- `AGENTS.md` — startup procedures and Super Memory tool guide
- `SOUL.md` — persona, boundaries, language policy
- `USER.md` — human profile template
- `IDENTITY.md` — assistant identity
- `MEMORY.md` — curated long-term memory starter
- `HEARTBEAT.md` — periodic check template
- `memory/active-memory-rules.md` — memory doctrine

**Included skill**: `openclaw-plugin/super-memory/skills/super-memory-operator/`
- First-run checklist
- Daily operating procedures
- Troubleshooting guide
- Memory write style guidelines

**Quick install**:

```bash
bash scripts/install-workspace-templates.sh
```

See `docs/OPENCLAW_WORKSPACE_TEMPLATES.md` for details and recommended OpenClaw config.

Planned next:

- Direct upstream adapters after deeper source-level mapping
- Full supervised gateway/plugin runtime smoke inside OpenSandbox with live OpenClaw hook API validation before any production slot replacement
- Self-improvement proposal generator via Skill Workshop
- Better recall ranking and source citations

See `docs/ARCHITECTURE.md`.
