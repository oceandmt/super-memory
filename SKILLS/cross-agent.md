# super-memory-cross-agent

## Goal
Multi-agent memory operations: share, compare, synthesize across agents and sessions.

## Tools
- `super_memory_cross_agent_recall` - recall across agent namespaces
- `super_memory_cross_agent_compare` - compare different agents knowledge
- `super_memory_cross_agent_conflicts` - detect contradictions between agents
- `super_memory_cross_agent_report` - structured cross-agent report
- `super_memory_cross_agent_summary` - summarized view of an agent
- `super_memory_cross_scope_recall` - recall across scopes
- `super_memory_cross_session_synthesis` - synthesize across sessions
- `super_memory_shared_recall` - recall only shared memories
- `super_memory_honcho_ask` - query Honcho perspective system
- `super_memory_honcho_profile` - get/set peer card

## Workflows

### 1. Cross-agent recall
```python
from super_memory.bridge import cross_agent_recall
results = cross_agent_recall(query="database schema", agents=["lucas", "alex"], semantic_reorder=True)
```

### 2. Compare agents knowledge
```python
from super_memory.bridge import cross_agent_compare
comparison = cross_agent_compare(topic="authentication", agents=["lucas", "alex"])
```

### 3. Cross-session synthesis
```python
from super_memory.bridge import cross_session_synthesis
synth = cross_session_synthesis(queries=["What did we decide about caching?"], sessions=["session-1", "session-2"])
```

### 4. Honcho perspective
```python
from super_memory.bridge import honcho_ask, honcho_profile
result = honcho_ask(query="What does Alex know about deployment?", about="alex")
honcho_profile(about="alex", facts=["Alex prefers Docker Compose for staging"])
```

### 5. Agent isolation
```python
from super_memory.bridge import isolation_set_rules, isolation_summary
isolation_set_rules(agent="alex", can_see=["lucas"])
isolation_summary()
```

## Verification
- cross_agent_recall returns results filtered by agent
- cross_agent_compare shows per-agent knowledge + gaps
- honcho_ask returns perspective about a peer
- isolation_summary shows current visibility rules
