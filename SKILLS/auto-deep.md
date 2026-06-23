# super-memory-auto-deep

## Goal
Automated memory health pipeline: audit, qualify, debug, improve, consolidate, dream, tiers.

## Tools
- `super_memory_deep_audit` - full memory audit
- `super_memory_deep_qualify` - quality score (A-F grade)
- `super_memory_deep_debug` - module-level analysis
- `super_memory_deep_improve` - auto-fix detected issues
- `super_memory_auto_deep_pipeline` - run all deep steps
- `super_memory_consolidate` - dedup/compress/summarize/mature/enrich/prune
- `super_memory_dedup` - detect & merge duplicates
- `super_memory_lifecycle_tier` - auto HOT/WARM/COLD promotion
- `super_memory_lifecycle_compression` - mark long memories for compression
- `super_memory_lifecycle_review` - Leitner spaced repetition queue
- `super_memory_leitner` - review session
- `super_memory_dream_full_cycle` - insight generation from weak ties

## Workflows

### Full CI/CD pipeline
```python
from super_memory.bridge import auto_deep_pipeline
report = auto_deep_pipeline(dry_run=True)
print(f"Audit: {report['audit_grade']} | Qualify: {report['qualify_grade']} ({report['qualify_score']}/100)")
for p in report["improvement_proposals"]:
    print(f"  {p['priority']}: {p['proposal']}")
report = auto_deep_pipeline(dry_run=False)
```

### Nightly consolidation
```python
from super_memory.bridge import consolidate
consolidate(strategy="dedup")      # merge duplicates
consolidate(strategy="compress")   # compress long memories
consolidate(strategy="mature")     # reinforce confidence
consolidate(strategy="enrich")     # extract entities/concepts
consolidate(strategy="prune")      # remove orphaned edges
```

### Spaced repetition (Leitner)
```python
from super_memory.bridge import lifecycle_review
reviews = lifecycle_review(action="queue", limit=10)
lifecycle_review(action="mark", fiber_id=item["fiber_id"], success=True)
```

### Dream / Insight generation
```python
from super_memory.bridge import dream_full_cycle
insights = dream_full_cycle()
for ins in insights.get("insights", []):
    print(f"New insight: {ins['content'][:100]}")
```

### Crontab recommendation
```cron
0 2 * * * python3 -c "from super_memory.bridge import consolidate; consolidate(strategy='all')"
0 3 * * 0 python3 -c "from super_memory.bridge import auto_deep_pipeline"
```

## Verification
- auto_deep_pipeline(dry_run=True) returns proposals without side effects
- consolidate(strategy='all') runs without errors
- lifecycle_review(action='queue') returns due items
- dream_full_cycle() returns new insights or empty gracefully
