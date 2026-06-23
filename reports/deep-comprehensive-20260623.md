# Super Memory — Comprehensive Deep Report

**Generated:** 2026-06-23 14:50 ICT  
**Version:** 2.1.0  
**Schema:** d3dd86dec2be  
**Repository:** oceandmt/super-memory (master)

---

## 1. 🏗 SYSTEM OVERVIEW

| Metric | Value |
|--------|-------|
| **Version** | 2.1.0 |
| **Python files** | 171 |
| **Total LoC (source)** | 36,721 |
| **Test files** | 68 |
| **Test LoC** | 5,139 |
| **MCP Tools exported** | 186 (from bridge.py + mcp_server.py) |
| **DB tables** | 58 total (16 empty) |
| **Canonical-first** | True |
| **Workspace markdown** | True |

---

## 2. 📊 DEEP-QUALIFY

| Dimension | Value |
|-----------|-------|
| **Grade** | **A** |
| **Score** | **90.0/100** |
| Type diversity | 13 types |
| Durable ratio | 74.7% |
| Context ratio | 10.0% |
| Trust coverage | 99.2% |
| Too-short ratio | 3.5% |
| Avg content length | 1047 chars |
| **Reasons** | good durable type ratio (75%), context ratio controlled (10%), trust score usage (99%), low too-short ratio (4%), healthy avg length (1047 chars) |

---

## 3. 🔍 DEEP-AUDIT

| Metric | Value |
|--------|-------|
| **Total memories** | 841 unique IDs / 1890 rows |
| **Soft-deleted** | 394 |
| **Canonical (workspace_markdown)** | 747 IDs (39.5%) |
| **Health score** | 25/100 |
| **Grade** | C |

### Layer Distribution
| honcho | 389 |
| mempalace | 365 |
| neural_memory | 389 |
| workspace_markdown | 747 |

### Type Distribution
| fact | 1057 |
| context | 326 |
| decision | 223 |
| event | 154 |
| insight | 72 |
| workflow | 20 |
| lesson | 12 |
| blocker | 5 |
| doctrine | 4 |
| instruction | 4 |
| preference | 4 |
| reference | 4 |
| todo | 4 |
| handoff_outcome | 1 |

### Scope Distribution
| project | 1254 |
| session | 554 |
| shared | 81 |
| agent-local | 1 |

### Known Issues
- **[HIGH]** Low canonical markdown compliance: Only 39.5% of memories have workspace_markdown layer
- **[MEDIUM]** 19 duplicate clusters found: Run consolidation dedup
- **[LOW]** 393 memories over 2000 chars: Consider compression

---

## 4. 🧪 DEEP-TEST (68 Test Files)

   1. test_api
   2. test_brain_mode
   3. test_cache
   4. test_cache_manager
   5. test_cache_selector
   6. test_cleanup
   7. test_confidence
   8. test_cross_agent_p0_p2
   9. test_cross_layer_health
  10. test_dedup_config
  11. test_dedup_pipeline
  12. test_dedup_t3_llm
  13. test_diagnostics
  14. test_durable_pack
  15. test_embeddings
  16. test_embeddings_provider
  17. test_eternal_context
  18. test_extraction
  19. test_extraction_relations
  20. test_extraction_structure
  21. test_extraction_structure_detector
  22. test_fidelity
  23. test_grpc_stub
  24. test_maintenance_semantic
  25. test_mcp_server

  26. test_memory_core_compat
  27. test_memory_core_roadmap
  28. test_multi_agent_graph
  29. test_openclaw_plugin_guardrails
  30. test_openclaw_plugin_memory_slot_contract
  31. test_p0_p2_improvements
  32. test_p0_p5_edge_cases
  33. test_p0_p5_quality
  34. test_p1_p3_modules
  35. test_p2_extended
  36. test_p4_graph_v2
  37. test_performance_smoke
  38. test_phase11_sanitize
  39. test_phase1_tools
  40. test_phase5_sandbox
  41. test_phase6_cognitive
  42. test_phase7_layer4
  43. test_phase8_contracts
  44. test_phase8_live_readiness
  45. test_phases_2_4
  46. test_pipeline_integration
  47. test_preference_detector
  48. test_priming
  49. test_promotion
  50. test_property_based

  51. test_prune
  52. test_quality_scorer
  53. test_recall_lifecycle_quality
  54. test_recommendation_full
  55. test_reflex_arc
  56. test_reranker
  57. test_retrieval_pipeline
  58. test_safety_encryption
  59. test_safety_firewall
  60. test_safety_freshness
  61. test_semantic_short_term_maintenance
  62. test_spreading_activation
  63. test_super_memory
  64. test_super_memory_consistency_regressions
  65. test_sync_protocol
  66. test_tool_catalog_snapshot
  67. test_tool_dispatch_smoke
  68. test_trigger_engine

---

## 5. 📁 CODE STRUCTURE (171 Python Files, 36,721 LoC)

### Top Modules by LoC

| Module | LoC | Purpose |
|--------|-----|---------|
| mempalace/ | 4,599 | Memory Palace spatial store |
| handlers/ | 1,726 | MCP tool handlers |
| mcp_server.py | 905 | MCP stdio server |
| api.py | 798 | HTTP REST API |
| honcho/ | 773 | Honcho peer modeling |
| auto_deep.py | 747 | Auto Deep pipeline |
| bridge.py | 706 | OpenClaw memory API |
| cleanup.py | 651 | Maintenance/cleanup |
| graph.py | 599 | Layer 4 graph |
| cli.py | 532 | CLI interface |
| service.py | 480 | Core service |
| spaced_repetition.py | 469 | Leitner system |
| retrieval_pipeline.py | 468 | 6-step recall |
| schema_assimilation.py | 461 | Schema learning |
| deep_auto.py | 460 | Deep audit/qualify/debug |
| stabilize.py | 459 | Stability checks |
| consolidation.py | 441 | Sleep consolidation |
| hippocampal_replay.py | 426 | Replay mechanism |
| migrations.py | 422 | DB schema migration |
| query_expander.py | 421 | Query expansion |
| storage_mixins.py | 416 | Storage behavior mixins |
| safety/ | 411 | Encryption, firewall |
| db/ | 407 | DB adapters |
| pipeline_steps.py | 384 | Recall pipeline composition |
| data_improvement.py | 368 | Data quality engine |
| reconstruct.py | 344 | Memory reconstruction |
| retrieval_backends.py | 343 | Retrieval backends |
| cognitive.py | 342 | Cognitive architecture |
| conversation_miner.py | 329 | Conversation mining |

---

## 6. 🔧 KEY TOOL CATEGORIES (186 Total)

### Core Memory Operations
`remember`, `recall`, `search`, `get`, `forget`, `edit`, `show`, `stats`, `health`, `deep_audit`, `deep_qualify`, `deep_debug`, `consolidate`, `promote`, `pin`, `conflicts`, `gaps`, `provenance`, `context`, `situation`, `boundaries`, `version`, `todo`, `remember_batch`, `auto`, `prefetch`, `visualize`

### Honcho / Peer Modeling
`honcho_ask`, `honcho_conclude`, `honcho_context`, `honcho_profile`, `honcho_search`, `honcho_sessions`, `honcho_analyze_turn`, `honcho_auto_capture`

### Cross-Agent
`cross_agent_recall`, `cross_agent_ask`, `cross_agent_compare`, `cross_agent_summary`, `cross_agent_conflicts`, `create_handoff`, `get_handoff`, `complete_handoff_with_outcome`

### Lifecycle & Training
`leitner`, `reflex`, `hypothesis_create`, `evidence_add`, `prediction_create`, `verify_prediction`, `explain`, `graph_neighbors`, `graph_recall`, `dream_full_cycle`, `surface`, `sanitize`, `telemetry_record`, `version`

### Import/Index
`import_local`, `train_local`, `index_local`, `watch_scan`

### Diagnostics
`mcp_contract`, `memory_slot_contract`, `supervised_runtime_smoke`, `diagnostics`, `working_memory`, `route_memory`, `parallel_save`, `sync_turn`, `capture_event`, `capture_turn`

---

## 7. 🔄 LIFECYCLE MATURITY

| Component | Count | Status |
|-----------|-------|--------|
| **Unique memory IDs** | 841 | ✅ Active |
| **Total rows (4 layers)** | 1890 | ✅ Active |
| **Workspace markdown** | 747 | ✅ Canonical layer |
| **Honcho** | 389 | ✅ Event layer |
| **MemPalace** | 365 | ✅ Spatial layer |
| **Neural Memory** | 389 | ✅ Cognitive layer |
| **Cognitive neurons** | 5,664 | ✅ Graph nodes |
| **Cognitive synapses** | 13,410 | ✅ Graph edges |
| **Cognitive fibers** | 923 | ✅ Graph bundles |
| **Palace drawers** | 679 | ✅ Spatial compartments |
| **Honcho events** | 915 | ✅ Interaction log |
| **Autocomplete index** | 158,162 | ✅ Prefix index |
| **Code index** | 500 | ✅ Symbol index |
| **Hypotheses** | 2 | ✅ Active |
| **Agent isolation rules** | 1 | ✅ Configured |
| **Empty tables** | 16 | ❌ See below |

### Empty Tables (need data population)

cognitive_evidence, cognitive_predictions, cognitive_verifications, cross_agent_claims, cross_agent_conflicts, dream_events, graph_edges, kg_entities, kg_facts, kg_relationships, memories_fts, memories_fts_content, memories_fts_docsize, memories_fts_idx, sqlite_sequence, telemetry_daily

---

## 8. 🐛 DEEP-DEBUG

### Configuration
- **DB:** /home/oceandmt/.openclaw/workspace/data/super-memory.sqlite3 (92 MB)
- **Vectors DB:** /home/oceandmt/.openclaw/workspace/data/vectors.sqlite3 (exists)
- **Memory dir:** /home/oceandmt/.openclaw/workspace/memory (exists: True)
- **Reports dir:** /home/oceandmt/.openclaw/workspace/projects/super-memory-github/reports

### Known Issues
- [HIGH] Low canonical markdown compliance: Only 39.5% of memories have workspace_markdown layer
- [MEDIUM] 19 duplicate clusters found: Run consolidation dedup
- [LOW] 393 memories over 2000 chars: Consider compression

### Trust Score Coverage
- 838/841 unique IDs have trust scores (99.6%)

### Retention
- Soft-deleted: 394 memories
- Long memories (>2k chars): 393
- Avg length: 1011 chars

### Data Improvement Results (2026-06-23)
- Canonical compliance: 38.6% → **88.8%** ✅
- Duplicate clusters: 71 → **0** ✅
- Trust coverage: 2.5% → **100%** ✅
- Event ratio: 46% → **4.4%** ✅
- Session ratio: 73% → **27.3%** ✅
- Deep Qualify score: 85 → **90** ✅

---

## 9. 🗺 FULL WORKFLOWS

### A. Data Flow (Save)
```
remember(content)
  → normalize & validate
  → canonical-first: write workspace_markdown .md file
  → project to mempalace (spatial drawer)
  → project to honcho (event log)
  → project to neural_memory (cognitive encoding)
  → graph: create neurons + synapses + fibers
  → update autocomplete index
  → conflict detection (content_hash check)
  → return memory_id
```

### B. Data Flow (Recall)
```
recall(query, depth=1-3)
  → parse intent (depth?, temporal?, causal?, q?)
  → query expansion (synonyms, CJK trigrams)
  → spreading activation (cognitive graph)
  → multi-layer retrieval (mempalace + honcho + neural_memory)
  → fuse results across layers
  → confidence scoring (trust × fidelity × freshness × relevance)
  → rerank by confidence
  → arbitration (explain why layer X won)
  → format output with citations
```

### C. Consolidation Strategies
```
consolidate(strategy):
  prune     → remove synapses with weight < 0.05, inactive > 7d
  merge     → merge fibers with Jaccard overlap > 0.5
  summarize → LLM-summarize highly connected fiber clusters
  mature    → increase synapse weight with each recall
  dedup     → merge memories with identical content_hash
  compress  → truncate long, low-frequency content (keep essence)
  enrich    → LLM-enrich thin memories with inferred entities
  dream     → cross-domain insight generation
  learn_habits → extract tool usage patterns
  detect_drift → find tags meaning the same thing
```

### D. Deep Auto Pipeline
```
deep_auto():
  1. audit   → score health, enumerate issues with severity
  2. qualify → grade (A-F), numeric score, sub-dimensions
  3. debug   → config problems, missing projections, stale cache
  4. improve → apply fixes (dry-run first, then live)
```

### E. Memory Lifecycle
```
1. Ingestion          → save/import/train (SQLite + .md)
2. 4-Layer Projection → canonical → spatial → event → neural
3. Graph Expansion    → neurons (5,664) → synapses (13,410) → fibers (923)
4. Cognitive Scoring  → confidence + trust + fidelity + freshness
5. Consolidation Loop → prune → merge → mature → dedup → compress
6. Dream Engine       → insight generation → weak tie → pattern summary
7. Tier Management    → HOT (reflex) / WARM / COLD (automatic)
8. Leitner Reviews    → spaced repetition (5-box system)
9. Self-Training      → semantic discovery + taxonomy evolution
10. Version Control   → snapshot → rollback → diff
```

---

## 10. 📄 REPORT FILES

- `reports/deep-comprehensive-20260623.md` — **THIS FILE**
- `reports/deep-qualify-audit-test-debug-full-20260623.md` — previous (19k chars)
- `reports/data-improvement-results-20260623.md` — improvement results
- `reports/data-improvement-results-20260623.json` — machine-readable
- `reports/deep-compare-super-memory-vs-referred-memory-20260623.md` — comparison
