from __future__ import annotations

import sqlite3


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_write_intents (
          id TEXT PRIMARY KEY,
          idempotency_key TEXT NOT NULL UNIQUE,
          source_adapter TEXT,
          source_event_id TEXT,
          agent_id TEXT,
          session_id TEXT,
          project TEXT,
          normalized_hash TEXT NOT NULL,
          simhash INTEGER,
          status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          completed_at TEXT,
          error TEXT,
          memory_id TEXT,
          claim_token TEXT,
          lease_until TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS memory_fingerprints (
          memory_id TEXT NOT NULL,
          layer TEXT NOT NULL,
          normalized_hash TEXT NOT NULL,
          simhash INTEGER,
          content_hash TEXT,
          source_event_key TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          PRIMARY KEY(memory_id, layer)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_fingerprints_hash ON memory_fingerprints(normalized_hash);
        CREATE INDEX IF NOT EXISTS idx_memory_fingerprints_source_event ON memory_fingerprints(source_event_key);
        CREATE INDEX IF NOT EXISTS idx_memory_fingerprints_simhash ON memory_fingerprints(simhash);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_fingerprints_canonical_hash
          ON memory_fingerprints(normalized_hash) WHERE layer = 'workspace_markdown';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_fingerprints_source_event
          ON memory_fingerprints(source_event_key) WHERE source_event_key IS NOT NULL AND layer = 'workspace_markdown';
        CREATE TABLE IF NOT EXISTS memory_jobs (
          id TEXT PRIMARY KEY,
          memory_id TEXT NOT NULL,
          layer TEXT NOT NULL,
          job_type TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 5,
          next_run_at TEXT,
          locked_at TEXT,
          locked_by TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now')),
          last_error TEXT,
          UNIQUE(memory_id, layer, job_type)
        );
        """
    )
    # Existing installations may predate the lease/recovery fields. SQLite's
    # ALTER TABLE ADD COLUMN is intentionally applied one column at a time.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(memory_write_intents)").fetchall()}
    additions = {
        "memory_id": "ALTER TABLE memory_write_intents ADD COLUMN memory_id TEXT",
        "claim_token": "ALTER TABLE memory_write_intents ADD COLUMN claim_token TEXT",
        "lease_until": "ALTER TABLE memory_write_intents ADD COLUMN lease_until TEXT",
        "attempts": (
            "ALTER TABLE memory_write_intents "
            "ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
        ),
        "updated_at": "ALTER TABLE memory_write_intents ADD COLUMN updated_at TEXT",
    }
    for name, statement in additions.items():
        if name not in existing:
            conn.execute(statement)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_write_intents_status_lease ON memory_write_intents(status, lease_until)")
