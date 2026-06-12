# Super Memory

Local multi-layer memory app for OpenClaw multi-agents.

Super Memory uses the Hermes-style idea of layered agent memory as the base, with Workspace Markdown as canonical truth and local adapters for MemPalace, Honcho, and NeuralMemory-style functions.

## Requirements

- Python 3.11+
- No Docker required
- Embedded LLM is optional, not required for baseline remember/recall

## Install for local development

```bash
cd projects/super-memory
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

## CLI

```bash
super-memory save-order
super-memory remember "Boss prefers canonical markdown first" --type preference --scope shared --agent-id lucas --project super-memory --tag doctrine
super-memory recall canonical
```

## Save order

1. Workspace Markdown = canonical local truth
2. MemPalace memory functions = structured/procedural/project memory
3. Honcho memory functions = conversational participant/session memory
4. Neural Memory functions = associative/graph/semantic memory

Downstream layers are treated as derived. By default, if canonical Workspace Markdown save fails, later layers are skipped.

## Current implementation status

Implemented now:

- Python package skeleton
- CLI: `remember`, `recall`, `save-order`
- Layered save order
- Workspace Markdown append-only daily note backend
- SQLite deterministic adapters for MemPalace/Honcho/NeuralMemory layers
- Multi-agent provenance tags
- Tests for save order and recall

Planned next:

- Direct upstream adapters after deeper source-level mapping
- OpenClaw plugin/MCP wrapper
- Promotion workflow into `MEMORY.md` / `memory/registers/`
- Self-improvement proposal generator via Skill Workshop
- Better recall ranking and source citations

See `docs/ARCHITECTURE.md`.
