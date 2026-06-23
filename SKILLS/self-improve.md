# super-memory-self-improve

## Goal
Self-healing, self-training, self-improving memory from failed recall, drift, and feedback.

## Tools
- `super_memory_self_heal_status` - check self-heal state
- `super_memory_self_heal_embeddings` - repair embedding index
- `super_memory_capture_failed_recall` - log failed recall to training case
- `super_memory_recall_record_correction` - correction + training case
- `super_memory_recall_feedback_stats` - success/correction rates
- `super_memory_generate_curriculum` - full curriculum pipeline
- `super_memory_run_benchmark_tests` - run recall tests
- `super_memory_analyze_recall_failures` - find failure patterns
- `super_memory_audit_drift` - detect projection drift
- `super_memory_full_drift_repair` - audit + repair orphans
- `super_memory_repair_orphans` - delete orphaned projections

## Workflows

### 1. Self-heal embeddings
```python
from super_memory.bridge import self_heal_embeddings
result = self_heal_embeddings()
print(f"Repaired: {result.get('repaired_count', 0)}")
```

### 2. Capture and learn from failed recall
```python
from super_memory.bridge import recall_record_correction
result = recall_record_correction(
    query="connection pool size",
    memory_id="correct-memory-id",
    wrong_answer="pool=10",
    expected_answer="pool=20 for production",
)
print(f"Training case: {result['training_case']['case']['id']}")
```

### 3. Analyze failure patterns
```python
from super_memory.bridge import analyze_recall_failures
analysis = analyze_recall_failures()
for f in analysis['repeated_failures'][:5]:
    print(f"  '{f['query']}' failed {f['failures']} times")
```

### 4. Generate curriculum + tests
```python
from super_memory.bridge import generate_curriculum
c = generate_curriculum()
print(f"Cases: {c['training_cases']['generated']} | Tests: {c['benchmark_tests']['generated']}")
```

### 5. Drift repair
```python
from super_memory.bridge import full_drift_repair
report = full_drift_repair(dry_run=True)  # preview
repair = full_drift_repair(dry_run=False) # apply
```

### Auto-improvement schedule
```cron
0 * * * * python3 -c "from super_memory.bridge import audit_drift; print(audit_drift()['drift_score'])"
0 4 * * * python3 -c "from super_memory.bridge import generate_curriculum, run_benchmark_tests"
0 5 * * 0 python3 -c "from super_memory.bridge import full_drift_repair, self_heal_embeddings"
```

## Verification
- recall_record_correction creates training case file
- generate_curriculum creates JSON cases + pytest file
- run_benchmark_tests runs and returns pass/fail
- full_drift_repair(dry_run=True) previews without side effects
