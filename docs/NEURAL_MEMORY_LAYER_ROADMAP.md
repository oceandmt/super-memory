# Neural-Memory Layer Roadmap for Super-Memory

Goal: evolve Super-Memory's Layer 4 neural-memory component closer to `nhadaututtheky/neural-memory` while preserving Super-Memory's OpenClaw-specific Markdown-first doctrine.

## Positioning

Super-Memory should not become a clone of GitHub Neural-Memory. The durable advantage of Super-Memory is:

1. OpenClaw-native memory slot integration.
2. Workspace Markdown as canonical truth.
3. Multi-agent provenance and routing for Lucas/Alex/Max/Isol-style deployments.
4. Safe install templates and operator skills for new OpenClaw instances.

The neural-memory layer should become a stronger derived associative/cognitive layer, not replace the canonical Markdown layer.

## Target Architecture

```text
Workspace Markdown canonical truth
  -> structured MemoryRecord
  -> neural projection: neurons / synapses / fibers
  -> spreading activation recall
  -> cognitive workflows: hypothesis / evidence / prediction / verification
  -> lifecycle: consolidation / reinforcement / compression / decay
  -> OpenClaw hooks: pre-prompt, post-turn, pre-compaction
```

## Gap Summary

| Area | Current Super-Memory | GitHub Neural-Memory | Gap |
| --- | --- | --- | --- |
| Graph model | Basic neurons/synapses/fibers | Rich graph with explicit relationships | Expand relation taxonomy + traversal |
| Recall | Multi-source baseline | Spreading activation | Implement weighted activation engine |
| Cognitive workflow | Baseline hypothesis/evidence/predict/verify | Bayesian confidence workflow | Add confidence update math + status lifecycle |
| Temporal memory | Basic BEFORE/AFTER | temporal_range + neighborhood | Add time-indexed queries |
| Consolidation | Baseline cycle | Episodic to semantic maturation | Add deterministic semantic merge/promote |
| Lifecycle | Basic cache/tier/compression | decay/reinforcement/compression | Add access reinforcement + decay policy |
| Import/train | Safe stubs | Production doc imports | Implement Markdown/JSON/CSV first |
| Benchmarks | Smoke tests only | Published performance claims | Add benchmark harness + regression gates |

## Development Phases

### Phase A — Graph Schema Parity

Priority: high.

Deliverables:
- Expand synapse relation types:
  - `CAUSED_BY`, `LEADS_TO`, `RESOLVED_BY`, `CONTRADICTS`, `SUPPORTS`, `REFUTES`, `SUPERSEDES`, `BEFORE`, `AFTER`, `MENTIONS`, `TAGGED_AS`, `IN_PROJECT`, `OWNED_BY_AGENT`, `DERIVED_FROM`.
- Add relation direction semantics.
- Add trust/confidence/salience fields to neurons and synapses.
- Add graph migration script.
- Add tests for relation creation, dedupe, and reverse traversal.

Acceptance:
- New relation set is documented.
- Existing memories migrate without data loss.
- `pytest` passes.

### Phase B — Spreading Activation Recall

Priority: highest.

Deliverables:
- Implement activation scoring:
  - seed query matches entities/tags/text
  - spread along weighted synapses up to configurable depth
  - decay by hop distance
  - boost by recency, priority, trust, access frequency
- Add `neural_recall(query, depth=0..3, max_tokens)` API.
- Return activation paths for explainability.
- Add MCP tool alias compatible with `nmem_recall` shape where practical.

Acceptance:
- Recall returns ranked memories plus path evidence.
- Exact keyword search and graph recall can be compared side-by-side.
- Benchmark: 1K, 10K synthetic memories with p50/p95 latency.

### Phase C — Cognitive Workflow Parity

Priority: high.

Deliverables:
- Upgrade hypothesis/evidence/prediction/verify:
  - hypothesis confidence in [0.01, 0.99]
  - evidence `for` / `against` with weight
  - Bayesian-style update
  - auto-confirm >=0.9 with enough evidence
  - auto-refute <=0.1 with enough evidence
- Link prediction outcomes back to hypotheses.
- Add `nmem_hypothesize`, `nmem_evidence`, `nmem_predict`, `nmem_verify` compatible tool surfaces.

Acceptance:
- Confidence evolves deterministically in tests.
- Prediction verification creates evidence synapses.

### Phase D — Temporal and Causal Queries

Priority: medium-high.

Deliverables:
- Add indexes on event time and created time.
- Implement:
  - temporal range query
  - temporal neighborhood around memory/fiber
  - causal trace forward/backward through `CAUSED_BY` / `LEADS_TO`
  - sequence trace through `BEFORE` / `AFTER`
- Add timeline narrative helper.

Acceptance:
- Can answer: “what led to this blocker?” and “what happened around this decision?”

### Phase E — Lifecycle, Decay, Reinforcement

Priority: medium.

Deliverables:
- Access frequency counter.
- Reinforcement on recall/use.
- Decay score for stale memories.
- Tier policy: hot / warm / cold.
- Compression states: full / summary / essence / ghost.
- Pin/reflex protection.

Acceptance:
- Frequently used memories stay hot.
- Old unused memories demote safely.
- Pinned/reflex memories never decay away.

### Phase F — Consolidation and Semantic Promotion

Priority: medium.

Deliverables:
- Consolidation commands:
  - dedupe near-identical records
  - merge overlapping episodic memories
  - promote stable repeated facts into semantic memory
  - detect contradictions
- Keep Markdown canonical: generated semantic memories must cite source Markdown lines/records.

Acceptance:
- Consolidation produces reviewable changes, not silent destructive rewrites.
- All promoted memories preserve provenance.

### Phase G — Import/Train First Real Slice

Priority: medium.

Deliverables:
- Implement safe local import for:
  - Markdown
  - JSON
  - CSV
- Optional later: PDF/DOCX/HTML.
- Add chunking and provenance source registration.

Acceptance:
- Can train/import a folder into neural projection without changing canonical files unless explicitly requested.

### Phase H — Benchmarks and Regression Gates

Priority: high before calling it production-like.

Benchmark suite:

1. Write benchmark:
   - 50, 500, 5K memory inserts.
   - Measure total time, p50/p95 per memory.
2. Recall benchmark:
   - 20, 200, 2K queries.
   - Compare keyword recall vs spreading activation.
3. Graph traversal benchmark:
   - depth 1/2/3, fanout 5/20/100.
4. Storage benchmark:
   - SQLite size per 1K / 10K / 100K records.
5. Quality benchmark:
   - fixed gold set of questions with expected source memories.
   - report hit@1, hit@5, MRR.
6. OpenClaw hook benchmark:
   - pre-prompt context latency budget <= 2s.
   - post-turn save should not block visible reply too long.

Acceptance gates:
- 10K memories recall p95 < 500ms for depth 1 on local SQLite.
- pre-prompt hook p95 < 2s.
- no data loss in migration tests.
- all tests pass.

## Compatibility Strategy

Expose GitHub neural-memory-like names only where useful:

- `nmem_remember` -> wrapper around Super-Memory remember.
- `nmem_recall` -> graph spreading activation recall.
- `nmem_health` -> health + graph stats.
- `nmem_hypothesize/evidence/predict/verify` -> cognitive workflow.

Avoid claiming full 63-tool compatibility until tools are actually implemented.

## Recommended Immediate Next Sprint

Sprint 1 should focus on the highest leverage gap: spreading activation.

Tasks:
1. Add relation taxonomy constants and docs.
2. Add graph activation engine.
3. Add activation path output.
4. Add `neural_recall` service method.
5. Add MCP/API surface for `nmem_recall`-style recall.
6. Add benchmarks for 1K and 10K synthetic memories.
7. Update comparison doc with actual Super-Memory benchmark numbers.

Expected result: Super-Memory becomes meaningfully closer to GitHub Neural-Memory in its core differentiator — associative graph recall — while retaining OpenClaw/Markdown strengths.

## Risk Notes

- Do not replace Markdown canonical truth with SQLite graph truth.
- Do not overbuild all 63 tools before the recall engine is strong.
- Do not add cloud sync/marketplace before local correctness and benchmarks.
- Do not enable Super-Memory in this machine's active OpenClaw runtime unless Boss explicitly requests it.

## Final Recommendation

Build toward “OpenClaw Neural-Memory-compatible layer” rather than “Neural-Memory clone”.

The right target is:

- Markdown-first canonical memory.
- Neural graph as derived intelligence layer.
- `nmem_*` compatible tool shapes for familiar workflows.
- Real spreading activation recall.
- Benchmarks proving latency and quality.
- OpenClaw-native hooks/templates/skills as Super-Memory's unique advantage.
