# Super Memory

[![CI](https://github.com/oceandmt/super-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/oceandmt/super-memory/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/super-memory.svg)](https://badge.fury.io/py/super-memory)
[![Python Versions](https://img.shields.io/pypi/pyversions/super-memory.svg)](https://pypi.org/project/super-memory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Local multi-layer memory system for OpenClaw multi-agents.**

> **v2.3.29** — Grade A (92/100) • Production-Ready • 254 MCP tools • 480 tests passing • CI/CD green

Super Memory is a Hermes-style layered agent memory system with Workspace Markdown as canonical truth, plus 3 derived layers (MemPalace, Honcho, Neural Memory) for structured, conversational, and associative recall. It ships as a Python package with CLI, FastAPI server, and MCP server — usable as an OpenClaw plugin or standalone memory service.

---

## Quick Start

```bash
# Install from GitHub
pip install 'git+https://github.com/oceandmt/super-memory.git'

# Verify
super-memory --version
super-memory save-order

# Remember + Recall
super-memory remember "This is my first memory" --type context --scope session
super-memory recall "first memory"

# Start MCP server (for MCP-compatible agents)
super-memory-mcp --stdio --profile normal

# Start API server (for OpenClaw plugin)
super-memory-api
```

---

## Features

### Core Memory Operations (254 MCP tools)

| Category | Tools | Description |
|----------|-------|-------------|
| **Remember** | `remember`, `remember_through_envelope`, `remember_batch`, `auto`, `todo`, `sync_turn` | Save memories with quality gate, envelope, batch, auto-extraction |
| **Recall** | `recall`, `recall_arbitrate_v3`, `recall_quick`, `search_query`, `search_similar`, `prefetch`, `context` | Multi-layer recall, explainable arbitration, FTS + semantic search |
| **Lifecycle** | `lifecycle_tier`, `temporal_decay`, `lifecycle_compression`, `lifecycle_review`, `leitner`, `forget`, `edit`, `show` | Tier management (HOT/WARM/COLD), decay, compression, spaced repetition |
| **Quality** | `build_envelope`, `ingest_through_adapter`, `deep_audit`, `deep_qualify`, `deep_debug`, `deep_improve`, `auto_deep_pipeline` | Quality grading, provenance, CI/CD pipeline |
| **Cognitive** | `hypothesize`, `evidence`, `predict`, `verify`, `conflicts`, `explain`, `provenance`, `source`, `version` | Hypothesis workflow, Bayesian confidence, causal chains |
| **Cross-Agent** | `cross_agent_recall`, `cross_agent_compare`, `cross_agent_conflicts`, `honcho_ask`, `honcho_profile`, `isolation_summary` | Multi-agent memory, Honcho perspective, agent isolation |
| **Self-Improve** | `self_heal_embeddings`, `recall_record_correction`, `generate_curriculum`, `run_benchmark_tests`, `full_drift_repair` | Auto-fix, training cases, curriculum generation |
| **Consolidation** | `consolidate`, `dedup`, `dream_full_cycle`, `flush_session_memories` | Dedup, compress, mature, enrich, prune, insight generation (token-frequency noise filtered, injection-echo guarded) |
| **Citations** | `enrich_recall_with_citations`, `dialectic_answer` | Line-level source citations, deterministic/LLM synthesis |

### Explainable Recall (Recall Arbitration v3)

Every recall result includes `why_selected` breakdown:

```python
{
  "score": 0.784,
  "why": {
    "lexical_overlap": 0.35,
    "semantic_score": 0.22,
    "graph_activation": 0.12,
    "recency": 0.08,
    "trust": 0.10,
    "quality": 0.07,
    "type_boost": 0.03,
    "goal_bias": 0.02,
    "layer_weight": 0.01
  }
}
```

### Line Citations + Neighbor Expansion

Memories from markdown files include exact source location and context:

```
📄 auth-system.md L5-L8 [a1b2c3d4]
   Keys rotated every 90 days using RS256.
   Expanded: L2-L11
```

### Quality Pipeline (Grade A)

```python
from super_memory.bridge import auto_deep_pipeline
report = auto_deep_pipeline(dry_run=True)
print(f"Grade: {report['qualify_grade']} ({report['qualify_score']}/100)")
```

### Self-Improvement Cycle

Failed recalls are automatically captured as training cases:
```
Failed recall → training case JSON → curriculum → pytest benchmarks → CI
```

---

## Requirements

- Python 3.11+
- No Docker required
- Optional: Ollama (for semantic search), cryptography (for memory encryption)

---

## Install

### From GitHub

```bash
pip install 'git+https://github.com/oceandmt/super-memory.git'
super-memory --help
```

### With extras

```bash
# Semantic search via sqlite-vec + Ollama
pip install "super-memory[semantic] @ git+https://github.com/oceandmt/super-memory.git"
ollama pull nomic-embed-text

# Document extraction (PDF, DOCX, PPTX, HTML, XLSX)
pip install "super-memory[extract] @ git+https://github.com/oceandmt/super-memory.git"
```

See `docs/semantic-mode.md` for full semantic setup.

### Local development

```bash
git clone https://github.com/oceandmt/super-memory.git
cd super-memory
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

---

## Documentation

| Document | Description |
|----------|-------------|
| 📘 [`docs/technical-overview.md`](docs/technical-overview.md) | Architecture, layers, data flow |
| 🗺️ [`docs/roadmap.md`](docs/roadmap.md) | Development roadmap |
| 📚 [`SKILLS/`](SKILLS/) | Agent skills (onboarding, basic-usage, quality-ingest, recall-arbitration, cross-agent, auto-deep, self-improve, lifecycle) |
| 🔧 [`docs/MCP_SERVER.md`](docs/MCP_SERVER.md) | MCP server reference |
| 🧩 [`docs/OPENCLAW_PLUGIN_INSTALL.md`](docs/OPENCLAW_PLUGIN_INSTALL.md) | OpenClaw plugin setup |
| 📄 [`CHANGELOG.md`](CHANGELOG.md) | Full version history |
| ⚙️ [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Architecture deep-dive |

---

## Architecture

### Layered Save Order

```
1. Workspace Markdown ──── canonical truth (append-only daily notes)
2. MemPalace ───────────── structured/procedural/project memory
3. Honcho ──────────────── conversational participant/session memory
4. Neural Memory ──────── associative/graph/semantic memory
```

If canonical Markdown save fails, downstream layers still save with `pending_canonical_sync=True`. Call `flush_pending()` after recovery to replay into Markdown.

### Integration Surfaces

1. **OpenClaw Native Plugin** — memory-slot integration with staged rollout: `safe` → `admin` → `exclusive`
2. **MCP Server** — stdio MCP for non-OpenClaw AI agents (`normal` / `admin` profiles)
3. **FastAPI Server** — REST API on `127.0.0.1:8765` (local only, no auth)
4. **CLI** — `super-memory` command for direct terminal usage

### Key Modules

| Module | Path | Purpose |
|--------|------|---------|
| MemoryEnvelope | `core/envelope.py` | Quality/trust/provenance contract |
| SourceAdapter | `ingest/__init__.py` | Chat/File/URL → deterministic payloads |
| Semantic Closets | `projections/closet.py` | Pointer-based structured retrieval |
| Recall v3 | `recall/__init__.py` | Explainable multi-factor scoring |
| Drift Repair | `projections/drift_repair.py` | Orphan projection audit + repair |
| Dialectic | `recall/dialectic.py` | Format/synthesize recall answers |
| Curriculum | `evals/curriculum.py` | Failed recall → training → benchmarks |
| Auto Deep | `auto_deep.py` | CI/CD pipeline for memory health |

---

## Memory Lifecycle

| Type | Tier | Decay | Purpose |
|------|------|-------|---------|
| `decision` | pinned/HOT | Never | Technical decisions |
| `fact` | WARM | 180d | Verified knowledge |
| `insight` | WARM | 60d | Pattern discoveries |
| `context` | WARM→COLD | 14d | Conversation context |
| `event` | WARM→COLD | 7d | Timeline events |
| `workflow` | WARM | 90d | Learned workflows |
| `todo` | WARM | 30d | Action items |
| `instruction` | HOT | 180d | Agent instructions |

---

## OpenClaw Plugin

### Systemd Service (recommended)

```bash
# Create user service
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/super-memory-api.service <<'EOF'
[Unit]
Description=Super Memory API
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/.openclaw/workspace
ExecStart=%h/.openclaw/venvs/super-memory-cli/bin/super-memory-api --host 127.0.0.1 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now super-memory-api
curl -fsS http://127.0.0.1:8765/health
```

### Plugin Config

```json
{
  "plugins": {
    "entries": {
      "super-memory": {
        "enabled": true,
        "config": {
          "mode": "admin",
          "agentId": "lucas",
          "apiBaseUrl": "http://127.0.0.1:8765",
          "manageApiService": true,
          "autoSyncTurns": true,
          "autoFlush": true
        }
      }
    }
  }
}
```

### Workspace Templates

```bash
bash scripts/install-workspace-templates.sh
```

Includes: AGENTS.md, SOUL.md, USER.md, IDENTITY.md, MEMORY.md, HEARTBEAT.md, active-memory-rules.md, and the super-memory-operator skill.

---

## CLI Reference

```bash
# Memory operations
super-memory remember "content" --type decision --scope shared --project my-project
super-memory recall "query"
super-memory memory-search "query" --json-out
super-memory memory-get memory/2026-06-23.md --from-line 1 --lines 20

# Memory health
super-memory deep-audit
super-memory deep-qualify
super-memory auto-deep

# Semantic (with Ollama)
super-memory semantic doctor --config .openclaw/super-memory.yaml
super-memory semantic index --config .openclaw/super-memory.yaml
super-memory semantic verify "query" --config .openclaw/super-memory.yaml

# Setup & verify
super-memory setup --workspace-root "$HOME/.openclaw/workspace" --output "$HOME/.openclaw/super-memory.yaml"
super-memory doctor --no-benchmark --json-out
```

---

## CI/CD Status

- **CI**: 480/480 tests passing (Python 3.11 + 3.12)
- **Auto Deep**: Grade A (90/100)
- **Canonical Compliance**: 99.9%
- **MCP Tools**: 254 (122 categories)
- **Autocomplete Prefixes**: 17,090
- **Deployment**: ✅ release environment

---

## Project Structure

```
super-memory/
├── super_memory/
│   ├── core/envelope.py       # MemoryEnvelope v1
│   ├── ingest/                # SourceAdapter manifest
│   ├── projections/           # Closets, Drift Repair
│   ├── recall/                # Recall v3, Feedback, Citations, Dialectic
│   ├── evals/                 # Curriculum, benchmarks
│   ├── safety/                # Firewall, freshness, encryption
│   ├── dedup/                 # 3-tier dedup pipeline
│   └── ...                    # 60+ modules
├── SKILLS/                    # OpenClaw agent skills (8 proposals)
├── tests/                     # 480 tests (80 files)
├── docs/                      # Full documentation
├── scripts/                   # Plugin install, workspace templates
├── openclaw-plugin/           # Native OpenClaw plugin
└── config/                    # Example configs
```

---

## Planned Next

- Incremental vector index (no full rebuild)
- Cross-machine database merge
- Obsidian vault import
- LangChain/LlamaIndex adapter
- Performance query benchmark suite

See [`docs/roadmap.md`](docs/roadmap.md) for full roadmap.
