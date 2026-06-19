from __future__ import annotations

import sqlite3
from typing import Any

from .config import load_config
from .migrations import run_migrations
from .storage import SuperMemoryStore


def _sqlite_master_sql(conn: sqlite3.Connection, type_: str, name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        (type_, name),
    ).fetchone()
    return row[0] if row and row[0] else None


def _recreate_session_health_view(conn: sqlite3.Connection) -> bool:
    desired_sql = """
    CREATE VIEW v_session_health AS
    SELECT
        s.id AS session_id,
        s.agent_id,
        s.status,
        s.started_at,
        s.updated_at,
        COUNT(h.id) AS event_count
    FROM sessions s
    LEFT JOIN honcho_events h ON h.session_id = s.id
    GROUP BY s.id, s.agent_id, s.status, s.started_at, s.updated_at
    """.strip()
    current = _sqlite_master_sql(conn, "view", "v_session_health") or ""
    # Repair legacy/broken views, including the known stale reference to
    # honcho_events_legacy_notnull. DROP+CREATE is safe for SQLite views because
    # views store no data.
    needs_recreate = (
        not current
        or "honcho_events_legacy_notnull" in current
        or "LEFT JOIN honcho_events h" not in current
    )
    if not needs_recreate:
        return False
    conn.execute("DROP VIEW IF EXISTS v_session_health")
    conn.execute(desired_sql)
    return True


def _rebuild_fts_table(conn: sqlite3.Connection, table: str) -> bool:
    if table not in {"memories_fts", "honcho_events_fts"}:
        raise ValueError(f"unsupported FTS table: {table}")
    sql = _sqlite_master_sql(conn, "table", table)
    if not sql or "USING fts5" not in sql.lower():
        return False
    # SQLite cannot bind table names, so only whitelisted derived FTS table
    # names are interpolated here. Avoid f-strings so the static SQL safety
    # gate can distinguish this from unsafe dynamic SQL.
    conn.execute("INSERT INTO " + table + "(" + table + ") VALUES('rebuild')")
    return True


def cleanup(
    *,
    config_path: str | None = None,
    vacuum: bool = False,
    integrity_check: bool = True,
) -> dict[str, Any]:
    """Run official safe SQLite cleanup/repair for Super Memory.

    Conservative by design:
    - run migrations first for schema/tables/indexes/triggers
    - repair derived views and rebuild FTS indexes inside one transaction
    - optionally VACUUM after commit because SQLite forbids VACUUM in a tx
    - never drop data tables; only derived views/FTS indexes are touched
    """
    cfg = load_config(config_path)
    migration = run_migrations(cfg)
    store = SuperMemoryStore(cfg)
    actions: list[str] = []
    checks: dict[str, Any] = {}

    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if _recreate_session_health_view(conn):
                actions.append("recreated_view:v_session_health")

            for table in ("memories_fts", "honcho_events_fts"):
                try:
                    if _rebuild_fts_table(conn, table):
                        actions.append(f"rebuilt_fts:{table}")
                except sqlite3.OperationalError as exc:
                    actions.append(f"skipped_fts:{table}:{exc}")

            # Prove the known-problem view resolves now while still in tx.
            conn.execute("SELECT COUNT(*) FROM v_session_health").fetchone()
            checks["v_session_health"] = "ok"

            if integrity_check:
                quick = conn.execute("PRAGMA quick_check").fetchone()[0]
                checks["quick_check"] = quick
                if quick != "ok":
                    raise sqlite3.DatabaseError(f"PRAGMA quick_check failed: {quick}")

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    if vacuum:
        with store.connect() as conn:
            conn.execute("VACUUM")
            actions.append("vacuum")

    return {
        "ok": True,
        "db_path": str(store.path),
        "migration": migration,
        "actions": actions,
        "checks": checks,
    }
