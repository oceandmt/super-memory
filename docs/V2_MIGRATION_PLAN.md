# Super-Memory v2 Migration Plan: Remove Legacy `graph_edges`

## Objective
Remove the legacy `graph_edges` table and all backward-compatibility shims, making `cognitive_synapses` the single source of truth for graph relationships.

## Current State (v1.x)
| Component | Status |
|-----------|--------|
| `cognitive_synapses` | Primary graph table (source/target neuron_id, weight, confidence, relation) |
| `graph_edges` | Legacy table (source/target memory_id) — read in `/status`, fallback in graph queries |
| Bridge | `cognitive_neurons.source_memory_id` → memory_id for cross-table lookup |
| Tests | Some edge-case tests may rely on `graph_edges` reads |

## Migration Steps (v2.0)

### Phase 1: Pre-Migration Audit (can do now)
1. **Query inventory** — grep all `graph_edges` references in codebase
   ```bash
   grep -rn "graph_edges" super_memory/ tests/ docs/
   ```
2. **Dependency map** — identify all code paths that read/write `graph_edges`
3. **Test coverage** — ensure contract tests cover `cognitive_synapses` paths

### Phase 2: Code Changes
1. **Remove `graph_edges` table from `schema.sql`**
   - Drop `CREATE TABLE graph_edges` and related indexes
   - Remove `graph_edges` from migrations (if any)
2. **Update `storage.py`**
   - Remove `graph_neighbors` method using `graph_edges`
   - Update `graph/neighbors` endpoint to use `cognitive_synapses` via neuron bridge
3. **Update `bridge.py`**
   - Remove `graph_neighbors` passthrough to storage
   - Ensure `cognitive_synapses` query helpers cover all use cases
4. **Update `api.py`**
   - `/status` should report `cognitive_synapses` only (remove `graph_edges` count)
   - Remove `graph_edges` from response if present
5. **Update `mcp_server.py`**
   - No MCP tool directly exposes `graph_edges` — verify
5. **Update tests**
   - Remove `graph_edges` assertions
   - Add `cognitive_synapses` assertions where needed

### Phase 3: Data Migration (one-time)
- No data migration needed: `cognitive_synapses` already contains all new edges
- Legacy edges in v1.x `graph_edges` rows become historical only (can drop table)

### Phase 4: Verification
1. Run full test suite: `pytest -q` → 72 passed
2. Run benchmarks: `python -m super_memory.benchmarks` → all passed
3. Deploy to staging VPS, smoke test all endpoints
4. Verify `/status` returns only `cognitive_synapses` count
5. Tag `v2.0.0` release

## Rollback Plan
- Keep `graph_edges` in schema for 1 release cycle with a deprecation warning
- If issues arise: restore table, revert code, re-evaluate

## Timeline
- **Week 1:** Phase 1 audit (can start immediately)
- **Week 2:** Phase 2 code changes
- **Week 3:** Phase 3 data migration script + verification
- **Week 4:** Phase 4 verification + v2.0.0 tag

## Notes
- This migration is non-urgent; v1.x is stable with dual-read
- Only proceed after confirming no external consumers depend on `graph_edges`
- Consider parallel run period (both tables) for 1 cycle before hard drop