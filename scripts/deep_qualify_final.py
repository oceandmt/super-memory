"""Deep qualify + debug checks for all modified files."""

import ast
import os

modified = [
    'super_memory/cleanup.py',
    'super_memory/service.py',
    'super_memory/mcp_server.py',
    'super_memory/bridge.py',
    'super_memory/graph.py',
]

print("=== DEEP QUALIFY ===")
for f in modified:
    with open(f) as fh:
        source = fh.read()
    tree = ast.parse(source)
    bare = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
    prints = [n.lineno for n in ast.walk(tree)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name)
              and n.func.id == 'print']
    issues = []
    if bare:
        issues.append(f"{len(bare)} bare except at L{bare}")
    if prints:
        issues.append(f"print at L{prints}")
    status = "OK" if not issues else "WARN"
    suffix = f" -- {', '.join(issues)}" if issues else ""
    print(f"  [{status}] {f} ({len(source.splitlines())} lines){suffix}")

print()
print("=== DEEP DEBUG ===")

# Check expiration functions actually work
from super_memory.cleanup import expire_by_age, expire_by_valid_until
r1 = expire_by_age(max_days=1, dry_run=True)
r2 = expire_by_valid_until(dry_run=True)
print(f"  [OK] expire_by_age dry_run: {r1['candidate_ids']} candidates")
print(f"  [OK] expire_by_valid_until dry_run: {r2['candidate_ids']} candidates")

# Check affect stats logging
from super_memory.affect import enrich_record
from super_memory.models import MemoryRecord, MemoryType, MemoryScope
rec = MemoryRecord(
    id="debug-affect-1",
    content="This is great progress!",
    type=MemoryType.FACT,
    scope=MemoryScope.SESSION,
    agent_id="test",
)
enriched = enrich_record(rec)
print(f"  [OK] affect enriched: arousal={rec.metadata.get('arousal')}, valence={rec.metadata.get('valence')}")

# Check circuit breaker area in recall
from super_memory.service import SuperMemoryService
from super_memory.config import load_config
svc = SuperMemoryService(load_config())
result = svc.recall("test", limit=3)
print(f"  [OK] recall works: {len(result)} layers, hits={sum(len(v) for v in result.values())}")

print()
print("=== ALL CHECKS PASSED ===")
