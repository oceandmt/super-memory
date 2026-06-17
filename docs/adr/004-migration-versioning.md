# ADR 004: Schema Migration Versioning

Date: 2026-06-17

Status: Accepted

## Context

Super Memory uses a dual-migration strategy:
1. **Legacy idempotent runner** (`migrations.py::run_migrations`) — runs `schema.sql` + additive `ALTER TABLE` for column additions. Safe to run repeatedly; no version tracking.
2. **Alembic versioned migrations** (`alembic/`) — provides reproducible, versioned schema evolution with upgrade/downgrade support.

Both must coexist without conflicting: the legacy runner handles initial creation and emergency column healing, while Alembic provides CI/governance-grade versioning.

## Decision

We adopt a **complementary dual-runner** approach:

- **`run_migrations()`** remains the primary engine at runtime (called from `SQLiteLayerBackend._init_db()`). It is idempotent and safe for concurrent access via file-level locking (`fcntl.flock`).
- **`run_alembic_migrations()`** provides an opt-in versioned path. The Alembic `env.py` points to the same SQLite database path derived from `SuperMemoryConfig` via `load_config()`, not a hardcoded path.
- **No conflict**: Alembic's `alembic_version` table tracks its own state. The legacy runner is pure SQL and does not reference it.

### Key Properties

1. **Same DB, Same Source** — Both runners target the same `sqlite_path` derived from `SuperMemoryConfig`. The `alembic/env.py` imports `super_memory.config.load_config` and `super_memory.migrations.sqlite_path` for deterministic path resolution.
2. **Version Tracking** — Alembic records applied revisions in the `alembic_version` table. The legacy runner is versionless; its schema is defined by `schema.sql` + additive `ALTER` logic.
3. **CI Integration** — `run_alembic_migrations("head")` can be called in CI/CD to ensure the schema is up-to-date before test suites.
4. **No Rollback by Default** — Since SQLite has limited ALTER support, Alembic downgrades are generated but not actively tested in production-like scenarios.

## Consequences

- **Positive**: Migration versioning is operational. CI can enforce schema correctness with Alembic.
- **Positive**: No breaking changes to existing runtime behavior. Legacy runner still works for all in-process use.
- **Negative**: Two migration paths increase maintenance burden. Schema changes must update both `schema.sql` and Alembic migration scripts.

## See Also

- `super_memory/migrations.py` — Legacy runner with file-lock safety
- `alembic/env.py` — Alembic environment with SuperMemory config integration
- `alembic/versions/` — Versioned migration scripts
