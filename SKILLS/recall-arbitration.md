# super-memory-recall-arbitration

## Goal
Explainable, multi-factor memory recall with scoring breakdown, citations, layer votes, and optional dialectic synthesis.

## Prerequisites
- super-memory >= v2.2.0

## Tools
- `super_memory_recall_arbitrate_v3` - unified recall with explanations
- `super_memory_recall_quick` - lightweight lexical search (no graph)
- `super_memory_enrich_recall_with_citations` - add line citations + neighbor expansion
- `super_memory_dialectic_answer` - optional synthesis (format or LLM)
- `super_memory_hybrid_fuse` - merge multiple recall sources
- `super_memory_explain` - explain how two concepts connect
- `super_memory_diversify_results` - deduplicate + diversify

## Workflow: Recall with explanations

```python
from super_memory.bridge import recall_arbitrate_v3
result = recall_arbitrate_v3("What is the authentication strategy?", limit=5, min_score=0.1)

for sel in result["selected"]:
    print(f"Score: {sel['score']:.3f}")
    print(f"Why: {json.dumps(sel['why'], indent=2)}")
    # lexical_overlap, semantic_score, graph_activation, recency, trust, quality, type_boost, goal_bias, layer_weight

print(f"Layer votes: {result['layer_votes']}")
print(f"Excluded: {result['excluded_count']} (duplicates across layers)")
print(f"Winner layer: {result['winner_layer']}")
print(f"Confidence: {result['confidence']:.3f}")
```

## Workflow: Enriched citations

```python
from super_memory.bridge import enrich_recall_with_citations
result = recall_arbitrate_v3("JWT key rotation")
citations = enrich_recall_with_citations(result, neighbor_lines=3)
for c in citations["citations"]:
    print(f"📄 {c['citation']}")
    print(f"   {c['excerpt'][:200]}")
    print(f"   Expanded: {c['expanded_range']}")
```

## Workflow: Dialectic synthesis
```python
from super_memory.bridge import dialectic_answer
answer = dialectic_answer("What's our JWT strategy?", recall_result=result, mode="format")
print(answer["answer"])
print(answer["confidence"])
print(answer["gaps"])
```

## Scoring formula
```
final_score = (
    lexical  * 0.20 + semantic * 0.20 + graph * 0.15 +
    recency  * 0.08 + trust    * 0.10 + quality * 0.12 +
    type_boost * 0.06 + goal_bias * 0.05 + layer * 0.04
) * rank_decay
```

## When to use which
| Mode | Use case | Speed |
|------|----------|-------|
| recall_arbitrate_v3 | Full explainable recall | Medium |
| recall_quick | Fast lexical check | Fast |
| dialectic_answer('format') | Structured answer with citations | Medium |
| dialectic_answer('synthesize') | LLM synthesis (reasoning) | Slow |
