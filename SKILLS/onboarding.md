# super-memory-onboarding

## Goal
Install, configure, and verify super-memory on any OpenClaw agent.

## Prerequisites
- OpenClaw running
- `pip` access
- Git access to `https://github.com/oceandmt/super-memory.git`

## Steps

### 1. Install / Verify
```bash
# Editable install from local clone
cd /home/oceandmt/.openclaw/workspace/projects/super-memory-github
pip install -e .

# Or fresh clone
git clone https://github.com/oceandmt/super-memory.git
cd super-memory && pip install -e .
```

### 2. Verify import
```python
import super_memory
v = super_memory.__version__
print(f"super-memory v{v}")
```

### 3. Verify MCP contract
```python
from super_memory.mcp_server import TOOLS, ADVANCED_TOOLS, NORMAL_TOOLS
print(f"MCP tools: {len(TOOLS)} total, {len(ADVANCED_TOOLS)} advanced, {len(NORMAL_TOOLS)} normal")
```
Expect: 254+ tools.

### 4. Verify bridge health
```python
from super_memory.bridge import deep_audit, deep_qualify, deep_debug
a = deep_audit(); q = deep_qualify(); d = deep_debug()
print(f"Audit: {a['grade']} | Qualify: {q['grade']} ({q['score']}/100) | Debug: {len(d['problems'])} problems")
```

### 5. Quick functional test
```python
from super_memory.bridge import remember, recall
r = remember({"content": "super-memory onboarding verified", "type": "context", "tags": ["onboarding", "test"]})
mem_id = r["record"]["id"]
result = recall("onboarding verified")
print(f"Remember: {mem_id[:8]} | Recall: {len(result.get('workspace_markdown', []))} results")
```

### 6. Three-way sync check
```bash
python3 -c "import super_memory; print(super_memory.__file__)"
cd /path/to/repo && git log -1
gh release view v2.2.0 --json tagName
```

## Verification
- ✅ `import super_memory` works
- ✅ MCP tools >= 254
- ✅ `bridge.deep_debug()` returns 0 problems
- ✅ remember + recall round-trip works

## Failure modes
| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: super_memory` | Run `pip install -e .` in repo dir |
| MCP tools < 254 | Re-install: `git pull && pip install -e .` |
| Can't connect to DB | Check `config_path`, ensure SQLite writable |
| Version mismatch | `pip install -e .` to sync editable link |
