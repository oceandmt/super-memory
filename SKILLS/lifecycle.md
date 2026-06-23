# super-memory-lifecycle

## Goal
Manage memory lifecycle: tier promotion, decay, compression, spaced repetition, dream, cleanup.

## Tools
- `super_memory_lifecycle_tier` - auto HOT/WARM/COLD by access patterns
- `super_memory_temporal_decay` - apply decay to expired memories
- `super_memory_lifecycle_compression` - mark/compress long memories
- `super_memory_lifecycle_review` - spaced repetition queue
- `super_memory_leitner` - review session (mark success/fail)
- `super_memory_dream_full_cycle` - generate insights from weak ties
- `super_memory_flush_session_memories` - purge expired session memories
- `super_memory_consolidate` - compress/mature/prune

## Workflows

### 1. Tier management
```python
from super_memory.bridge import lifecycle_tier
status = lifecycle_tier(action="evaluate")
print(f"HOT: {status['hot_count']} | WARM: {status['warm_count']} | COLD: {status['cold_count']}")
lifecycle_tier(action="apply")
```

### 2. Temporal decay + compression
```python
from super_memory.bridge import temporal_decay, lifecycle_compression
temporal_decay()
lifecycle_compression(action="mark")
```

### 3. Spaced repetition (Leitner)
```python
from super_memory.bridge import lifecycle_review
reviews = lifecycle_review(action="queue", limit=5)
for item in reviews.get("queue", []):
    print(f"{item['content'][:80]} box={item['box']}")
    lifecycle_review(action="mark", fiber_id=item["fiber_id"], success=True)
```

### 4. Dream engine
```python
from super_memory.bridge import dream_full_cycle
insights = dream_full_cycle()
for ins in insights.get('insights', []):
    print(f"  {ins.get('content', '')[:120]}")
```

### 5. Cleanup expired session memories
```python
from super_memory.bridge import flush_session_memories
flush_session_memories()
```

### Type-specific lifecycle
| Type | Tier | Decay |
|------|------|-------|
| decision | pinned/HOT | Never |
| fact | WARM | 180d |
| insight | WARM | 60d |
| context | WARM->COLD | 14d |
| event | WARM->COLD | 7d |
| workflow | WARM | 90d |
| todo | WARM | 30d |
| instruction | HOT | 180d |

## Verification
- lifecycle_tier(action='evaluate') shows distribution
- lifecycle_review(action='queue') returns due reviews
- dream_full_cycle() runs without error
- flush_session_memories() returns count
