# Super-Memory vs Neural-Memory Comparison

Comprehensive comparison between Super Memory (local OpenClaw-specific) and `nhadaututtheky/neural-memory` (GitHub PyPI package).

## Executive Summary

| Aspect | Super-Memory | Neural-Memory (GitHub) |
|--------|-------------|----------------------|
| **Status** | Local dev project | Production PyPI package |
| **Primary use** | OpenClaw memory slot | Generic MCP memory for any AI agent |
| **Architecture** | Markdown-first + derived graph | Graph-native spreading activation |
| **Distribution** | GitHub project | PyPI + npm + VS Code Marketplace |
| **Maturity** | Development (41 tests passing) | Production (7400+ tests) |
| **Cost** | Free (all-local) | Free + Pro $9/mo |

## Architecture Comparison

### Core Memory Paradigm

**Super-Memory**:
- **Canonical truth**: Workspace Markdown files (`memory/YYYY-MM-DD.md`, `MEMORY.md`)
- **Layered save order**: Markdown → MemPalace → Honcho → NeuralMemory (derived)
- **Retrieval**: Multi-source (local FTS5, Meilisearch, associative layer)
- **Philosophy**: Markdown auditability + associative intelligence

**Neural-Memory**:
- **Canonical truth**: Graph (neurons + synapses in SQLite/InfinityDB)
- **Primary method**: Spreading activation (mimics human brain)
- **24 explicit relationship types**: CAUSED_BY, LEADS_TO, RESOLVED_BY, CONTRADICTS, SUGGESTED_BY, etc.
- **Philosophy**: Pure graph reasoning, no vector DB dependency (free tier)

### Storage Backend

**Super-Memory**:
- Primary: Filesystem (`.md` files)
- Secondary: SQLite (MemPalace/Honcho/NeuralMemory adapters)
- Graph: Derived projection (Layer 4)
- Size: Optimized for markdown human-readability

**Neural-Memory**:
- Free: SQLite + FTS5 keyword search
- Pro: InfinityDB + HNSW semantic search
- Compression: 5-tier (float32 → float16 → int8 → binary → metadata)
- Size: ~5GB per 1M neurons (free), ~1GB (Pro compressed)

## Feature Comparison

### Core Tools

**Super-Memory** (21+ tools):
- remember, remember_batch, recall, search_compatible, get_compatible
- show, context, todo, auto, stats, health
- prefetch, sync_turn, promote, sanitize_prompt, status
- Phase 3: conflicts, provenance, source, version, pin, consolidate, gaps, explain, situation, reflex, boundaries

**Neural-Memory** (63 MCP tools):
- nmem_remember, nmem_recall, nmem_health (primary 3)
- 14 memory types: fact, decision, error, insight, preference, workflow, instruction...
- Cognitive: hypothesize, evidence, predict, verify (Bayesian confidence)
- Temporal: causal chain, temporal_range, temporal_neighborhood
- Brain management: version, rollback, diff, transplant
- Import: ChromaDB, Mem0, Cognee, Graphiti, LlamaIndex adapters
- Training: PDF, DOCX, PPTX, HTML, JSON, XLSX, CSV ingestion

### Advanced Features

| Feature | Super-Memory | Neural-Memory |
|---------|-------------|---------------|
| **Cognitive reasoning** | Phase 6 baseline (working memory, attention, arbitration) | Hypothesis/evidence/prediction/verify with Bayesian confidence |
| **Temporal queries** | Phase 7 baseline (BEFORE/AFTER synapses) | temporal_range, temporal_neighborhood, causal chains |
| **Consolidation** | Phase 6 cycle (parallel save, merge, promotion) | Episodic → semantic maturation, HNSW clustering (Pro) |
| **Compression** | Text-level (Phase 7) | 5-tier vector compression (Pro: 97% savings) |
| **Conflict detection** | Phase 3 baseline | Built-in CONTRADICTS synapses |
| **Training from docs** | Phase 4 stub (not implemented) | Production: PDF/DOCX/PPTX/HTML/JSON/XLSX/CSV |
| **Cloud sync** | Phase 4 stub (not implemented) | Production: Cloudflare D1 Merkle delta sync |
| **Brain marketplace** | Phase 4 stub (not implemented) | Production: Brain Store with 3 seed brains |
| **Web dashboard** | None | 7-page React UI + graph viz |
| **VS Code extension** | None | Marketplace extension with CodeLens + WebSocket |

## Integration Comparison

### OpenClaw Integration

**Super-Memory**:
- **Purpose-built** for OpenClaw multi-agent memory
- Plugin structure: `openclaw-plugin/super-memory/`
- Memory slot replacement: `plugins.slots.memory: "super-memory"`
- Hooks: pre-prompt context, post-agent capture, pre-compaction flush
- Multi-agent provenance: `agent:<lucas|alex|max|isol>`, `scope:<shared|local>`
- Workspace templates: `SOUL.md`, `AGENTS.md`, `MEMORY.md`, etc.
- Skill: `super-memory-operator/SKILL.md`

**Neural-Memory**:
- **Generic MCP** server for any AI agent
- OpenClaw integration: via `neuralmemory` npm package + plugin
- Memory slot: `plugins.slots.memory: "neuralmemory"`
- No OpenClaw-specific hooks or workspace conventions
- Multi-agent: generic support, no OpenClaw-specific routing

### MCP Server

**Super-Memory**:
- Stdio MCP: `super-memory-mcp --stdio --profile normal`
- Tool profiles: normal, admin
- Guardrails: prompt sanitization, auto-capture sanitization, schema normalization

**Neural-Memory**:
- Stdio MCP: `nmem-mcp`
- Auto-initializes on first use
- 63 tools exposed by default

### API Server

**Super-Memory**:
- FastAPI: `super-memory-api --host 127.0.0.1 --port 8765`
- OpenClaw plugin calls API locally
- Status endpoint: `/status`

**Neural-Memory**:
- Optional: `pip install neural-memory[server]`
- Web dashboard: `nmem serve` → `http://localhost:8000/dashboard`
- REST API for all 63 tools

## Performance & Scale

### Benchmarks

**Super-Memory**:
- Tests: 41 passing (core functionality)
- No published performance benchmarks yet
- Target: OpenClaw multi-agent scale (dozens of agents, thousands of memories)

**Neural-Memory**:
- Tests: 7400+ passing
- Write 50 memories: 1.2s (121x faster than Mem0, 80x faster than Cognee)
- Read 20 queries: 1.8s
- **0 API calls, 0 LLM cost** for core operations
- Free tier: ~50K neurons tested
- Pro tier: 2M+ neurons, <5ms recall

### Scalability

**Super-Memory**:
- Designed for: OpenClaw workspace continuity (moderate scale)
- Bottleneck: Markdown append-only files + SQLite adapters
- Not yet stress-tested at 1M+ memory scale

**Neural-Memory**:
- Free: FTS5 keyword match, ~500ms at 1M neurons
- Pro: HNSW semantic search, <5ms at 1M neurons, tested to 2M+
- Smart merge: O(N×k) HNSW clustering vs O(N²) brute-force

## Development & Community

**Super-Memory**:
- License: Not specified (local project)
- Repository: Local development only
- Community: None (single-developer project)
- Documentation: `docs/` folder, README
- Support: Boss + Lucas only

**Neural-Memory**:
- License: MIT
- Repository: https://github.com/nhadaututtheky/neural-memory
- Community: PyPI package, VS Code Marketplace, active development
- Documentation: https://nhadaututtheky.github.io/neural-memory/
- Support: GitHub issues, community contributions

## Deployment & Installation

### Super-Memory

```bash
# Development install
cd super-memory
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

# OpenClaw plugin
cp -r openclaw-plugin/super-memory ~/.openclaw/plugins/
bash scripts/install-workspace-templates.sh

# Config
{
  "plugins": {
    "slots": { "memory": "super-memory" },
    "entries": {
      "super-memory": {
        "enabled": true,
        "config": { "apiBaseUrl": "http://127.0.0.1:8765" }
      }
    }
  }
}
```

### Neural-Memory

```bash
# User install
pip install neural-memory

# MCP config (auto-detected by Cursor/Claude/Windsurf)
{
  "mcpServers": {
    "neural-memory": { "command": "nmem-mcp" }
  }
}

# OpenClaw plugin
pip install neural-memory && npm install -g neuralmemory
{
  "plugins": {
    "slots": { "memory": "neuralmemory" }
  }
}
```

## Cost Model

**Super-Memory**:
- Development: Free (all-local)
- Runtime: Free (no API calls, no cloud)
- Storage: Local filesystem only

**Neural-Memory**:
- Free tier: Complete (63 tools, unlimited memories, fully offline)
- Pro tier: $9/mo
  - HNSW semantic search
  - InfinityDB backend
  - 5-tier compression (97% storage savings)
  - Merkle delta cloud sync
  - Smart merge consolidation
  - Cone queries (adjustable semantic recall)
- 30-day money-back guarantee
- Downgrade anytime, keep data

## Use Case Fit

### Super-Memory Best For

1. **OpenClaw-specific deployments**
   - Multi-agent memory with Lucas/Alex/Max routing
   - Workspace Markdown continuity requirement
   - Deep OpenClaw hook integration (pre-prompt, post-capture, flush)
   - Boss-supervised development cycle

2. **Markdown-first philosophy**
   - Human-readable audit trail required
   - Git-friendly memory persistence
   - Explicit save order (canonical → derived)

3. **Development/research**
   - Exploring memory architectures
   - Custom cognitive orchestration
   - Tight control over all layers

### Neural-Memory Best For

1. **Production AI agent memory**
   - Generic MCP clients (Claude, Cursor, Windsurf, etc.)
   - Large-scale memory (1M+ items)
   - Multi-device sync required
   - Community-supported, battle-tested

2. **Graph-first reasoning**
   - Spreading activation recall
   - Explicit causal chains (CAUSED_BY, LEADS_TO, etc.)
   - Hypothesis/evidence/prediction workflows

3. **Zero-cost operation**
   - No API calls
   - No LLM embeddings required (free tier)
   - Fully offline capable
   - Pro tier optional for semantic search

4. **Rich ecosystem**
   - Web dashboard + VS Code extension
   - Brain marketplace (import pre-built brains)
   - Import from other tools (Mem0, ChromaDB, etc.)
   - Document training (PDF/DOCX/etc.)

## Key Architectural Decisions

### Why Super-Memory chose Markdown-first

1. **Human auditability**: Boss can read `memory/2026-06-14.md` directly
2. **Git-friendly**: Markdown diffs are readable
3. **OpenClaw convention**: Workspace continuity pattern
4. **Canonical truth**: Derived layers are secondary
5. **No lock-in**: Plain text survives tool changes

### Why Neural-Memory chose Graph-first

1. **Brain-like reasoning**: Spreading activation mimics human memory
2. **Explicit relationships**: 24 synapse types encode meaning
3. **Performance**: Graph traversal faster than multi-layer search
4. **Zero dependencies**: No vector DB, no embeddings API required
5. **Scalability**: Pro tier HNSW scales to millions

## Migration Path

### From Neural-Memory → Super-Memory

**Not recommended**. Neural-Memory is production-ready, Super-Memory is development-only.

If required:
1. Export Neural-Memory brain: `nmem brain export -o export.json`
2. Parse neurons/synapses into Super-Memory format
3. Write to `memory/*.md` + SQLite adapters
4. Rebuild graph projection (Layer 4)

### From Super-Memory → Neural-Memory

**Viable for production deployment**:
1. Extract memories from `memory/*.md`
2. Use Neural-Memory import: `nmem import --source super-memory`
3. Configure Neural-Memory MCP
4. Transition OpenClaw slot: `neuralmemory`

## Conclusion

**Super-Memory** is a **research-stage OpenClaw-specific memory system** optimized for markdown continuity, multi-agent provenance, and deep OpenClaw integration. Best for Boss's supervised development where markdown auditability and explicit save order matter.

**Neural-Memory** is a **production-grade generic AI agent memory system** with a mature graph-native architecture, 63 tools, rich ecosystem (dashboard, VS Code extension, Brain Store), proven scale (2M+ neurons), and zero operational cost. Best for general MCP clients and production deployments.

**Recommendation**: Continue developing Super-Memory as a research project and OpenClaw memory slot candidate. For production AI agent memory needs outside OpenClaw, Neural-Memory is the mature choice.
