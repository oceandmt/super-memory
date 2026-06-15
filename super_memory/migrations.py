"""SQLite schema migration runner for Super-Memory.

Keeps all table definitions in schema.sql as the single source of truth.
Safe to run repeatedly; uses CREATE IF NOT EXISTS and additive ALTERs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .config import load_config
from .models import SuperMemoryConfig

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def sqlite_path(config: SuperMemoryConfig) -> Path:
    path = Path(config.workspace_root) / config.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _safe_ident(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError(f"unsafe sqlite identifier: {value}")
    return value


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    table = _safe_ident(table)
    return {row[1] for row in conn.execute("PRAGMA table_info(" + table + ")").fetchall()}


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    table = _safe_ident(table)
    column = _safe_ident(column)
    if column in _table_columns(conn, table):
        return False
    conn.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + ddl)
    return True


def _migrate_memories(conn: sqlite3.Connection) -> list[str]:
    changed: list[str] = []
    cols = _table_columns(conn, "memories")
    if not cols:
        return changed
    additions = {
        "layer": "TEXT NOT NULL DEFAULT 'workspace_markdown'",
        "type": "TEXT NOT NULL DEFAULT 'context'",
        "scope": "TEXT NOT NULL DEFAULT 'session'",
        "agent_id": "TEXT",
        "session_id": "TEXT",
        "project": "TEXT",
        "tags_json": "TEXT NOT NULL DEFAULT '[]'",
        "source": "TEXT",
        "trust_score": "REAL",
        "created_at": "TEXT",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for col, ddl in additions.items():
        if _add_column(conn, "memories", col, ddl):
            changed.append(f"memories.{col}")
    if "created_at" in _table_columns(conn, "memories"):
        conn.execute("UPDATE memories SET created_at = datetime('now') WHERE created_at IS NULL")
    return changed


def _migrate_honcho_events(conn: sqlite3.Connection) -> list[str]:
    changed: list[str] = []
    if not _table_columns(conn, "honcho_events"):
        return changed
    additions = {
        "memory_id": "TEXT",
        "workspace": "TEXT DEFAULT 'openclaw'",
        "session_id": "TEXT",
        "observer_peer_id": "TEXT DEFAULT 'lucas'",
        "observed_peer_id": "TEXT",
        "source": "TEXT",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        "created_at": "TEXT",
    }
    for col, ddl in additions.items():
        if _add_column(conn, "honcho_events", col, ddl):
            changed.append(f"honcho_events.{col}")
    if "created_at" in _table_columns(conn, "honcho_events"):
        conn.execute("UPDATE honcho_events SET created_at = datetime('now') WHERE created_at IS NULL")
    return changed


def run_migrations(config: SuperMemoryConfig | None = None) -> dict[str, object]:
    config = config or load_config()
    db_path = sqlite_path(config)
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        # Phase 1: heal legacy missing columns (separate tx so indexes reference them)
        changed = []
        changed.extend(_migrate_memories(conn))
        changed.extend(_migrate_honcho_events(conn))
        conn.commit()
    # Phase 2: full schema with clean columns
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.executescript(schema_sql)
        changed2 = []
        changed2.extend(_migrate_memories(conn))
        changed2.extend(_migrate_honcho_events(conn))
        conn.commit()
    return {"ok": True, "db_path": str(db_path), "changed": changed+changed2, "change_count": len(changed)+len(changed2)}


def main() -> None:
    print(run_migrations())


if __name__ == "__main__":
    main()
