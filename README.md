# Super Memory

[![CI](https://github.com/oceandmt/super-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/oceandmt/super-memory/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/super-memory.svg)](https://badge.fury.io/py/super-memory)
[![Python Versions](https://img.shields.io/pypi/pyversions/super-memory.svg)](https://pypi.org/project/super-memory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Local multi-layer memory app for OpenClaw multi-agents.

Super Memory uses the Hermes-style idea of layered agent memory as the base, with Workspace Markdown as canonical truth and local adapters for MemPalace, Honcho, and NeuralMemory-style functions.

## Requirements

- Python 3.11+
- No Docker required
- Embedded LLM is optional, not required for baseline remember/recall

## Install from GitHub

Other OpenClaw instances can install the Super Memory CLI/API/MCP package directly from this repository:

```bash
pip install 'git+https://github.com/oceandmt/super-memory.git'
super-memory --help
```

Semantic sqlite-vec/Ollama mode can be installed from a release tag with the semantic extra:

```bash
pip install "super-memory[semantic] @ git+https://github.com/oceandmt/super-memory.git@v1.1.2"
ollama pull nomic-embed-text
super-memory semantic doctor --config .openclaw/super-memory.yaml
super-memory semantic index --config .openclaw/super-memory.yaml
super-memory semantic verify "semantic recall smoke test" --config .openclaw/super-memory.yaml
```

Full semantic setup guide: [`docs/semantic-mode.md`](docs/semantic-mode.md).

📘 **Technical overview** (architecture, layers, data flow): [`docs/technical-overview.md`](docs/technical-overview.md).

🗺️ **Development roadmap** (planned phases): [`docs/roadmap.md`](docs/roadmap.md).

Recommended first-time setup for an OpenClaw workspace:

Fresh-install data isolation: without a config file or `SUPER_MEMORY_WORKSPACE_ROOT`, Super Memory stores data relative to the current working directory. Attaching it to a real OpenClaw workspace is an explicit opt-in via `super-memory setup --workspace-root ...`, YAML config, or environment variables.


```bash
super-memory setup \
  --workspace-root "$HOME/.openclaw/workspace" \
  --output "$HOME/.openclaw/super-memory.yaml" \
  --overwrite
super-memory doctor --no-benchmark --json-out
```

Start the local API bridge used by the native OpenClaw plugin:

```bash
super-memory-api
```

The API binds to `127.0.0.1:8765` by default. **Do not expose it directly to a network** unless you add an authentication layer in front of it.

## Integration surfaces

Super Memory has two integration surfaces:

1. **OpenClaw native plugin / memory-slot integration** — for OpenClaw. The long-term target is to run Super Memory as OpenClaw's memory slot. Use additive modes first for qualification, then promote to memory-slot mode when ready.
2. **MCP server** — for AI agents that are not OpenClaw but can speak MCP. These agents use MCP profiles (`normal` or `admin`), not OpenClaw plugin modes.

## Native OpenClaw plugin install

Clone the repository and install the native plugin wrapper:

```bash
git clone https://github.com/oceandmt/super-memory.git
cd super-memory
bash scripts/install-openclaw-plugin.sh --mode admin --no-restart
```

Recommended rollout for OpenClaw is staged:

1. `safe` — additive tools/corpus only; fastest install/load smoke test.
2. `admin` — additive admin/capture mode; recommended qualification mode for cross-agent/cross-session operation while keeping `memory-core` intact.
3. `exclusive` — **OpenClaw memory-slot mode**; replaces the OpenClaw memory slot and may register legacy `memory_search`/`memory_get` shims. This is the target mode for OpenClaw memory-slot cutover after qualification passes.

Verify the plugin install:

```bash
bash scripts/openclaw_plugin_doctor.sh
super-memory doctor --no-benchmark --json-out
curl -fsS http://127.0.0.1:8765/health
```

Full native plugin guide: [`docs/OPENCLAW_PLUGIN_INSTALL.md`](docs/OPENCLAW_PLUGIN_INSTALL.md).

## Install for local development

```bash
git clone https://github.com/oceandmt/super-memory.git super-memory
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

Super Memory also includes a local stdio MCP server for MCP-compatible agents that are not OpenClaw. MCP users do not use `safe/admin/exclusive`; they choose an MCP profile:

```bash
super-memory-mcp --stdio --profile normal
```

`normal` exposes daily-safe tools such as remember, remember-batch, show, context, todo, auto, stats, health, sanitize-prompt, sanitize-auto-capture, normalize-memory, recall, prefetch, sync-turn, memory-search, memory-get, and status. `admin` additionally exposes promotion and cross-agent/cross-session memory tools.

For cross-agent/cross-session setup, run the MCP server with `--profile admin` and follow `docs/CROSS_AGENT_SESSION_MEMORY_SETUP.md`.

Guardrail: this project can be developed as an OpenClaw memory-slot replacement candidate, but do not apply/register it into this machine's active OpenClaw config unless Boss explicitly instructs that later.

## API server

Start the FastAPI server (local only):

```bash
super-memory-api
```

The API binds to `127.0.0.1:8765` by default. **⚠️ Do not expose this API to a network** — it has no authentication and can access the local filesystem for train/import/watch operations. If you must proxy it, add a reverse-proxy auth layer first.

## Save order

1. Workspace Markdown = canonical local truth
2. MemPalace memory functions = structured/procedural/project memory
3. Honcho memory functions = conversational participant/session memory
4. Neural Memory functions = associative/graph/semantic memory

Downstream layers are treated as derived. By default (`require_canonical_first: true`), if canonical Workspace Markdown save fails, downstream SQLite layers **still save** with `pending_canonical_sync=True`. Call `flush_pending()` after recovering the workspace path to replay pending records into Markdown. This resilient fallback prevents data loss while keeping Markdown as the canonical source of truth.

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
- Cross-agent/cross-session memory: agent-scoped recall, Honcho session timelines, session archives, cross-scope recall, handoff bundles, and reporting tools
- Tests for save order, recall, OpenClaw compatibility, MCP, cross-agent/session flows, and guardrails

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
