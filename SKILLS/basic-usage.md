# super-memory-basic-usage

## Goal
Core memory operations — remember, recall, search, forget, edit.

## Prerequisites
- super-memory installed and MCP tools available

## Tools
- `super_memory_remember` - luu memory
- `super_memory_recall` - truy van multi-layer
- `super_memory_search_query` - full-text search
- `super_memory_search_similar` - semantic search
- `super_memory_forget` - soft/hard delete
- `super_memory_edit` - sua content/type/priority
- `super_memory_show` - xem chi tiet memory

## Workflows

### 1. Save memory (basic)
```python
from super_memory.bridge import remember
r = remember({
    "content": "MySQL connection pool size should be 20 for production",
    "type": "decision",
    "project": "my-project",
    "tags": ["mysql", "production", "config"],
    "scope": "shared"
})
# r["record"]["id"] - memory ID
```

### 2. Recall (multi-layer)
```python
from super_memory.bridge import recall
results = recall("MySQL pool size")
for layer, records in results.items():
    for rec in records:
        print(f"[{layer}] {rec.type}: {rec.content[:100]}")
```

### 3. Search (FTS + semantic)
```python
from super_memory.bridge import search_query, search_similar
fts = search_query("production pool")
sim = search_similar("database connection configuration")
```

### 4. Update lifecycle
```python
from super_memory.bridge import edit, forget
edit("memory-id", content="Pool size = 25 (updated)")
forget("memory-id")                # soft delete
forget("memory-id", hard=True)     # cascade to all projections
```

### 5. Scope & project isolation
| scope | visibility |
|-------|-----------|
| `session` | current session only |
| `agent-local` | this agent only |
| `shared` | all agents |
| `project` | agents working on same project |
| `cross-agent` | cross-agent queries |

## Verification
- remember returns `record["id"]` not empty
- recall finds memory by content match
- forget soft-delete hides from recall
- search returns relevant results sorted by score
