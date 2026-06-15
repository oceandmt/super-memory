# MemPalace & Honcho: super-memory vs GitHub Upstream Comparison

## Executive Summary

| Layer | super-memory (local) | GitHub Upstream | Gap Level |
|-------|---------------------|-----------------|-----------|
| **MemPalace** | SQLite adapter với spatial projection đơn giản | Full system: ChromaDB + 4-layer loading + AAAK compression + 170-token wake + LongMemEval 96.6% | **LỚN** - chỉ có spatial metaphor, thiếu core engine |
| **Honcho** | SQLite adapter với session/peer projection đơn giản | Production service: dialectic reasoning, peer modeling, cross-session persistence, API + SDK | **RẤT LỚN** - chỉ log events, không có reasoning |

**Core finding**: super-memory's MemPalace/Honcho layers là **local SQLite projection adapters** được thiết kế để chạy không phụ thuộc Docker/LLM, không phải implementation đầy đủ của upstream projects.

---

## MemPalace: super-memory vs GitHub MemPalace (mempalace/mempalace)

### GitHub MemPalace Architecture

```
Layer 1: Verbatim Storage (ChromaDB) - Raw conversation history
Layer 2: Structured Extraction - Entities, concepts, relationships
Layer 3: Spatial Organization - Memory Palace (wing/room/drawer/hall)
Layer 4: Compressed Index - AAAK 30x compression, 170-token startup
```

### Key Features (GitHub)

- **19 MCP tools**: search, store, graph query, agent diaries
- **CLI**: project mining, conversation mining
- **Zero LLM cost** for memory infrastructure (regex/keyword only)
- **LongMemEval**: 96.6% R@5 (claims verified by independent analysis)
- **Pluggable backend**: ChromaDB default, swappable
- **22K GitHub stars in 48 hours** (viral launch)

### super-memory MemPalace Layer (Current)

```python
# Chỉ có projection vào palace_drawers table
palace_drawers:
  wing = project hoặc metadata.wing
  room = session_id hoặc type
  hall = mapping từ MemoryType → PalaceHall (8 halls)
  checksum = SHA256(wing\0room\0hall\0content)  # dedup
  UNIQUE INDEX trên checksum
  INDEX trên (wing, room, hall)
```

### Gap Analysis

| Feature | super-memory | GitHub MemPalace |
|---------|-------------|-----------------|
| Verbatim storage layer | ❌ (dùng Markdown) | ✅ ChromaDB |
| Structured extraction (entities/concepts) | ❌ | ✅ |
| 4-layer progressive loading | ❌ | ✅ |
| AAAK compression (30x) | ❌ | ✅ |
| 170-token wake cost | ❌ | ✅ |
| Agent diaries | ❌ | ✅ |
| 19 MCP tools | ❌ (shared tools) | ✅ |
| CLI for project/conversation mining | ❌ | ✅ |
| LongMemEval benchmark | ❌ | ✅ 96.6% R@5 |
| Spatial navigation (wing/room/hall query) | ⚠️ basic via recall | ✅ dedicated |
| Pluggable backend | ❌ (SQLite only) | ✅ |

---

## Honcho: super-memory vs GitHub Honcho (plastic-labs/honcho)

### GitHub Honcho Architecture

```
Workspace → Peers (Human/Agent/Project/System)
  → Sessions (conversations)
    → Messages (verbatim)
    → Dialectic Reasoning (multi-pass depth 1-3)
      → Peer Representations (user/agent models)
      → Session Context (assembled per turn)
```

### Key Features (GitHub)

- **Dialectic reasoning**: Analyzes each turn, derives insights về preferences/habits/goals
- **Peer modeling**: Separate representations cho user và agent
- **Cross-session persistence**: Models improve over time
- **Session-scoped context**: Base context = session summary + user representation + peer card
- **Managed (api.honcho.dev) hoặc self-hosted** FastAPI
- **Python/TypeScript SDKs**
- **OpenClaw integration**: `openclaw-honcho` plugin replaces `memory-core`/`memory-lancedb`

### MCP Tools (GitHub Honcho)

- `honcho_ask` - Query about participant
- `honcho_context` - Recent memories + profile + conclusions
- `honcho_search` - Keyword search over memories
- `honcho_search_messages` - Search captured messages
- `honcho_search_conclusions` - Search insights/conclusions
- `honcho_profile` - Read/update peer card
- `honcho_remember` - Store fact (auto-detected type)
- `honcho_observe` - Write event to session
- `honcho_conclude` - Create/list/delete insights
- `honcho_reasoning` - LLM-synthesized insight about participant
- `honcho_rule` - Manage auto-capture rules
- `honcho_capture_turn` - Capture conversation turn
- `honcho_session` - Get session context
- `honcho_forget` - Delete remembered fact
- `honcho_status` - Local store stats + backend health

### super-memory Honcho Layer (Current)

```python
# Chỉ log event vào honcho_events table
honcho_events:
  observer_peer_id = record.agent_id (lucas/alex/max/isol)
  observed_peer_id = metadata.peer_id hoặc "boss"
  workspace = "openclaw" hoặc metadata.workspace
  session_id = record.session_id
  INDEX trên (workspace, session_id)
  INDEX trên (observer_peer_id, observed_peer_id)
```

### Gap Analysis

| Feature | super-memory | GitHub Honcho |
|---------|-------------|--------------|
| Dialectic reasoning (multi-pass depth 1-3) | ❌ | ✅ |
| Peer representations/modeling | ❌ | ✅ |
| Cross-session model improvement | ❌ | ✅ |
| Session context assembly (auto-assembled per turn) | ❌ | ✅ |
| Peer cards (profile) | ❌ | ✅ |
| Insights/conclusions | ❌ | ✅ |
| Multi-agent workspace isolation | ❌ | ✅ |
| Dedicated MCP tools (honcho_ask, etc.) | ❌ | ✅ |
| Self-hosted API server | ❌ | ✅ |
| SDKs (Python/TypeScript) | ❌ | ✅ |
| Auto-capture rules | ❌ | ✅ |
| Message search | ❌ | ✅ |
| Conclusion search | ❌ | ✅ |
| Forget/delete memory | ❌ (via shared tools) | ✅ |
| Cold/warm prompt selection | ❌ | ✅ |
| Background dialectic on session init | ❌ | ✅ |

---

## Proposed Improvements

### Phase 1: MemPalace - Spatial Intelligence Upgrade (Priority: HIGH)

```python
# 1. Thêm structured extraction layer
class SpatialExtractor:
    def extract_entities(self, text: str) -> list[Entity]
    def extract_concepts(self, text: str) -> list[Concept]
    def extract_relationships(self, text: str) -> list[Relationship]

# 2. Implement 4-layer progressive loading
class MemPalaceLoader:
    def load_layer1_verbatim(self, limit: int) -> list[MemoryRecord]      # ~170 tokens
    def load_layer2_structured(self, query: str) -> list[MemoryRecord]    # entities/concepts
    def load_layer3_spatial(self, wing: str, room: str) -> list[MemoryRecord]  # palace query
    def load_layer4_compressed(self, query: str) -> list[MemoryRecord]    # AAAK index

# 3. Add AAAK compression (keyword-based, no LLM)
class AAAKCompressor:
    def compress(self, memories: list[MemoryRecord]) -> CompressedIndex
    def search(self, query: str, index: CompressedIndex) -> list[MemoryRecord]
```

**Target**: 170-token wake cost, spatial query via `wing/room/hall` paths.

### Phase 2: Honcho - Dialectic Reasoning Core (Priority: HIGH)

```python
# 1. Peer modeling
class PeerModel:
    id: str
    role: PeerRole
    facts: list[Fact]
    preferences: list[Preference]
    habits: list[Habit]
    goals: list[Goal]

    def update_from_session(self, session: Session) -> None
    def to_context_block(self, max_tokens: int) -> str

# 2. Dialectic reasoning (multi-pass)
class DialecticEngine:
    def analyze_turn(self, user_msg: str, assistant_msg: str,
                     peer_model: PeerModel, depth: int = 2) -> DialecticResult

    # Pass 1: General facts about the participant
    # Pass 2: Session-scoped patterns and context
    # Pass 3: Deep insights and hypotheses (optional)

# 3. Session context assembly
class SessionContextBuilder:
    def build(self, session_id: str, peer_model: PeerModel,
              recent_turns: list[Turn]) -> ContextBlock
```

**Target**: `honcho_ask`, `honcho_context`, `honcho_profile` working locally.

### Phase 3: MCP Tools (Priority: MEDIUM)

```python
# MemPalace MCP tools
- super_memory_palace_search(query, wing?, room?, hall?)
- super_memory_palace_load_layer(layer: 1|2|3|4, query?)
- super_memory_palace_wings()
- super_memory_palace_rooms(wing)
- super_memory_palace_drawers(wing, room, hall?)

# Honcho MCP tools
- super_memory_honcho_ask(query, about_peer?)
- super_memory_honcho_context(session_id?, peer_id?)
- super_memory_honcho_profile(peer_id, facts?)
- super_memory_honcho_conclude(content, about_peer?)
- super_memory_honcho_sessions(workspace?)
- super_memory_honcho_search(query, about_peer?)
```

### Phase 4: Benchmarks & Validation (Priority: MEDIUM)

| Benchmark | Target |
|-----------|--------|
| MemPalace wake tokens | ≤ 200 tokens (vs 170 GitHub) |
| MemPalace recall@5 (LongMemEval subset) | ≥ 90% |
| Honcho dialectic latency | < 500ms per turn |
| Honcho peer model accuracy | Manual eval vs GitHub |

---

## Recommended File Structure

```
super_memory/
├── mempalace/
│   ├── __init__.py
│   ├── extractor.py          # Structured extraction (entities/concepts/relations)
│   ├── loader.py             # 4-layer progressive loading
│   ├── compressor.py         # AAAK compression
│   ├── spatial.py            # Wing/room/hall navigation
│   └── tools.py              # MCP tool definitions
├── honcho/
│   ├── __init__.py
│   ├── peer.py               # Peer model + representation
│   ├── dialectic.py          # Multi-pass reasoning engine
│   ├── session.py            # Session context assembly
│   ├── insights.py           # Conclusions/insights generation
│   └── tools.py              # MCP tool definitions
├── layers.py                 # Update: use new mempalace/honcho modules
└── mcp_server.py             # Register new tools
```

---

## Trade-off Decision

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **Full reimplement** | Feature parity với GitHub | Months of work, duplicate effort | ❌ |
| **Local adapters only** (current) | Simple, fast, no deps | Thiếu core intelligence | ✅ Baseline |
| **Hybrid: Core engine + OpenClaw hooks** | Best of both: spatial/dialectic intelligence + Markdown canonical + multi-agent provenance | Medium effort | ✅ **RECOMMENDED** |

---

## Sprint Plan (if approved)

1. **Sprint 1** (1-2 weeks): Implement `mempalace/extractor.py` + `loader.py` + 4-layer loading
2. **Sprint 2** (1-2 weeks): Implement `honcho/peer.py` + `dialectic.py` + session context
3. **Sprint 3** (1 week): MCP tools + benchmarks + integration test
4. **Sprint 4** (ongoing): Iterate based on Boss usage patterns

**Estimated effort**: ~4-6 weeks part-time để đạt ~80% GitHub functionality với OpenClaw-native advantages (markdown canonical, multi-agent provenance, workspace templates).

---

*Created: 2026-06-14 | Author: Lucas | Source: Boss request in #super-memory channel*
