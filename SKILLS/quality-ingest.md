# super-memory-quality-ingest

## Goal
Save memories with quality gate, provenance tracking, source adapter manifest, lifecycle policy.

## Prerequisites
- super-memory >= v2.2.0 (P0 modules)

## Tools
- `super_memory_build_envelope` - wrap content with quality/trust/provenance
- `super_memory_remember_through_envelope` - build + save one call
- `super_memory_ingest_through_adapter` - ingest qua SourceAdapter
- `super_memory_list_source_adapters` - xem adapters available
- `super_memory_ingest_and_remember` - ingest + save
- `super_memory_build_closets` - xay closet/drawer cho mot memory
- `super_memory_rebuild_all_closets` - rebuild tat ca closets
- `super_memory_deep_audit` - kiem tra canonical compliance

## Workflows

### 1. Save voi MemoryEnvelope (recommended)
```python
from super_memory.bridge import remember_through_envelope
r = remember_through_envelope(
    content="The authentication service uses JWT with RS256. Keys rotated every 90 days.",
    memory_type="decision",
    scope="shared",
    project="auth-system",
    tags=["jwt", "rs256", "key-rotation"],
    source_adapter="chat",
    trust_score=0.85,
    lifecycle_tier="warm",
)
# r["envelope"] - MemoryEnvelope metadata
# r["saved"] - canonical bridge.remember() result
```

### 2. Ingest file + auto chunking
```python
from super_memory.bridge import ingest_through_adapter
payloads = ingest_through_adapter(
    "file:/path/to/doc.md",
    agent_id="my-agent",
    project="docs"
)
```

### 3. Build semantic closets
```python
from super_memory.bridge import build_closets_for_memory, search_closets
build_closets_for_memory("memory-id")
results = search_closets("JWT rotation", limit=5)
for r in results["results"]:
    print(f"  {r['summary'][:80]}  [{r['pointer']}]")
```

### 4. Verify quality
```python
from super_memory.bridge import deep_audit
a = deep_audit()
for i in a["issues"]:
    print(f"{i['severity']}: {i['issue']}")
```

## Memory types + lifecycle
| Type | Use | Lifecycle |
|------|-----|-----------|
| fact | Kien thuc xac thuc | verify + slow decay (180d) |
| decision | Quyet dinh ky thuat | pin until superseded |
| insight | Phat hien tu pattern | reinforce on recall (60d) |
| context | Context conversation | fast decay (14d) |
| event | Timeline event | fast decay (7d) |
| workflow | Learned workflow | reinforce on use (90d) |
| blocker | Blocking issue | close after resolve (30d) |

## Verification
- remember_through_envelope returns envelope + saved
- ingest_through_adapter returns payloads with source metadata
- build_closets creates drawer + closet entries
- deep_audit shows 99%+ canonical compliance
