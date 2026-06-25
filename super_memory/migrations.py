"""SQLite schema migration runner for Super-Memory.

Keeps all table definitions in schema.sql as the single source of truth.
Safe to run repeatedly; uses CREATE IF NOT EXISTS and additive ALTERs.
"""
from __future__ import annotations

import fcntl
import sqlite3
from pathlib import Path

try:
    from alembic.config import Config as AlembicConfig

    from alembic import command
    _HAS_ALEMBIC = True
except ImportError:
    _HAS_ALEMBIC = False

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
        "pending_canonical_sync": "INTEGER DEFAULT 0",
        "content_hash": "TEXT",
    }
    for col, ddl in additions.items():
        if _add_column(conn, "memories", col, ddl):
            changed.append(f"memories.{col}")
    if "created_at" in _table_columns(conn, "memories"):
        conn.execute("UPDATE memories SET created_at = datetime('now') WHERE created_at IS NULL")
    return changed


def _migrate_honcho_events(conn: sqlite3.Connection) -> list[str]:
    changed: list[str] = []
    cols = _table_columns(conn, "honcho_events")
    if not cols:
        return changed
    # Older builds created honcho_events.memory_id as NOT NULL, which breaks
    # standalone Honcho capture events that intentionally have no canonical
    # memory projection. SQLite cannot drop NOT NULL in place, so rebuild the
    # table into the schema.sql shape when that legacy constraint is detected.
    info = conn.execute("PRAGMA table_info(honcho_events)").fetchall()
    memory_col = next((row for row in info if row[1] == "memory_id"), None)
    if memory_col is not None and int(memory_col[3] or 0) == 1:
        conn.execute("ALTER TABLE honcho_events RENAME TO honcho_events_legacy_notnull")
        conn.execute("""
            CREATE TABLE honcho_events (
                id TEXT PRIMARY KEY,
                memory_id TEXT,
                workspace TEXT NOT NULL DEFAULT 'openclaw',
                session_id TEXT,
                observer_peer_id TEXT NOT NULL DEFAULT 'lucas',
                observed_peer_id TEXT,
                content TEXT NOT NULL,
                source TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        legacy_cols = _table_columns(conn, "honcho_events_legacy_notnull")
        select_exprs = []
        for col, default in [
            ("id", "lower(hex(randomblob(16)))"),
            ("memory_id", "NULL"),
            ("workspace", "'openclaw'"),
            ("session_id", "NULL"),
            ("observer_peer_id", "'lucas'"),
            ("observed_peer_id", "NULL"),
            ("content", "''"),
            ("source", "NULL"),
            ("metadata_json", "'{}'"),
            ("created_at", "datetime('now')"),
        ]:
            select_exprs.append(col if col in legacy_cols else default)
        conn.execute(
            "INSERT INTO honcho_events (id, memory_id, workspace, session_id, observer_peer_id, observed_peer_id, content, source, metadata_json, created_at) SELECT "
            + ", ".join(select_exprs)
            + " FROM honcho_events_legacy_notnull"
        )
        conn.execute("DROP TABLE honcho_events_legacy_notnull")
        changed.append("honcho_events.memory_id_nullable")
        cols = _table_columns(conn, "honcho_events")
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




def _migrate_views(conn: sqlite3.Connection) -> list[str]:
    changed: list[str] = []
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name='v_session_health'"
    ).fetchone()
    current = row[0] if row and row[0] else ""
    if (
        not current
        or "honcho_events_legacy_notnull" in current
        or "LEFT JOIN honcho_events h" not in current
    ):
        conn.execute("DROP VIEW IF EXISTS v_session_health")
        conn.execute("""
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
        """)
        changed.append("v_session_health")
    return changed


def _has_cjk(text: str) -> bool:
    """Check if text contains CJK characters (CJK Unified Ideographs, Hangul, Katakana/Hiragana)."""
    try:
        import unicodedata
        for ch in text:
            if len(ch) > 1:
                continue
            cp = ord(ch)
            # CJK Unified Ideographs
            if 0x4E00 <= cp <= 0x9FFF:
                return True
            # Hangul Syllables
            if 0xAC00 <= cp <= 0xD7AF:
                return True
            # Katakana
            if 0x30A0 <= cp <= 0x30FF:
                return True
            # Hiragana
            if 0x3040 <= cp <= 0x309F:
                return True
            # CJK Extension A
            if 0x3400 <= cp <= 0x4DBF:
                return True
            # CJK Compatibility Ideographs
            if 0xF900 <= cp <= 0xFAFF:
                return True
    except Exception:
        pass
    return False


def _detect_tokenizer(config=None) -> str:
    """Detect whether to use trigram tokenizer based on config or DB content.

    Returns 'trigram' if CJK support is enabled/needed, else 'default'.
    """
    if config:
        cjk_enabled = getattr(config, "cjk_fts5", None) or getattr(config, "cjk_search", "")
        if cjk_enabled in (True, "true", "1", "trigram", "cjk"):
            return "trigram"
    return "default"


def _migrate_fts5(conn: sqlite3.Connection) -> list[str]:
    """Create or upgrade FTS5 virtual tables for fast full-text search.

    Uses content-table form so the FTS index stays in sync with the base
    table via DELETE/INSERT triggers or manual rebuild.

    Falls back silently if FTS5 is not compiled into SQLite.
    """
    changed: list[str] = []
    # Check if FTS5 is available
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
    except sqlite3.OperationalError:
        return []  # FTS5 not available in this SQLite build

    # memories_fts: content-table form (idempotent check + auto-heal stale format)
    try:
        existing_fts = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='memories_fts'"
        ).fetchone()
        needs_recreate = (
            existing_fts is not None
            and existing_fts[0] is not None
            and 'content=memories' not in existing_fts[0]
        )
        if needs_recreate:
            conn.execute('DROP TRIGGER IF EXISTS memories_fts_ai')
            conn.execute('DROP TRIGGER IF EXISTS memories_fts_ad')
            conn.execute('DROP TRIGGER IF EXISTS memories_fts_au')
            conn.execute('DROP TABLE IF EXISTS memories_fts')
        exists_before = not needs_recreate and existing_fts is not None
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts "
            "USING fts5(content, content=memories, content_rowid=rowid)"
        )
        # FTS5 content-table form requires triggers to keep index in sync
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_fts_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_fts_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_fts_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        if not exists_before:
            changed.append("memories_fts")
    except sqlite3.OperationalError:
        pass

    # honcho_events_fts: content-table form (idempotent check + auto-heal)
    try:
        existing_fts = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='honcho_events_fts'"
        ).fetchone()
        needs_recreate = (
            existing_fts is not None
            and existing_fts[0] is not None
            and 'content=honcho_events' not in existing_fts[0]
        )
        if needs_recreate:
            conn.execute('DROP TRIGGER IF EXISTS honcho_events_fts_ai')
            conn.execute('DROP TRIGGER IF EXISTS honcho_events_fts_ad')
            conn.execute('DROP TRIGGER IF EXISTS honcho_events_fts_au')
            conn.execute('DROP TABLE IF EXISTS honcho_events_fts')
        exists_before = not needs_recreate and existing_fts is not None
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS honcho_events_fts "
            "USING fts5(content, content=honcho_events, content_rowid=rowid)"
        )
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS honcho_events_fts_ai AFTER INSERT ON honcho_events BEGIN
                INSERT INTO honcho_events_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS honcho_events_fts_ad AFTER DELETE ON honcho_events BEGIN
                INSERT INTO honcho_events_fts(honcho_events_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS honcho_events_fts_au AFTER UPDATE ON honcho_events BEGIN
                INSERT INTO honcho_events_fts(honcho_events_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                INSERT INTO honcho_events_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        if not exists_before:
            changed.append("honcho_events_fts")
    except sqlite3.OperationalError:
        pass

    # CJK trigram FTS5 tables (P2 #6) — tokenize=trigram for multi-language search
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories_cjk_fts "
            "USING fts5(content, tokenize='trigram', content=memories, content_rowid=rowid)"
        )
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_cjk_fts_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_cjk_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_cjk_fts_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_cjk_fts(memories_cjk_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_cjk_fts_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_cjk_fts(memories_cjk_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                INSERT INTO memories_cjk_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        if conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='memories_cjk_fts'").fetchone():
            changed.append("memories_cjk_fts")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS honcho_events_cjk_fts "
            "USING fts5(content, tokenize='trigram', content=honcho_events, content_rowid=rowid)"
        )
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS honcho_events_cjk_fts_ai AFTER INSERT ON honcho_events BEGIN
                INSERT INTO honcho_events_cjk_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS honcho_events_cjk_fts_ad AFTER DELETE ON honcho_events BEGIN
                INSERT INTO honcho_events_cjk_fts(honcho_events_cjk_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS honcho_events_cjk_fts_au AFTER UPDATE ON honcho_events BEGIN
                INSERT INTO honcho_events_cjk_fts(honcho_events_cjk_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                INSERT INTO honcho_events_cjk_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        if conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='honcho_events_cjk_fts'").fetchone():
            changed.append("honcho_events_cjk_fts")
    except sqlite3.OperationalError:
        pass

    return changed


def run_migrations(config: SuperMemoryConfig | None = None) -> dict[str, object]:
    config = config or load_config()
    db_path = sqlite_path(config)
    lock_path = db_path.with_suffix(".migration.lock")
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    
    # Acquire file lock to serialize concurrent migrations
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
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
                # P0/P1 additive tables for projection drift, long-memory drawers,
                # and Honcho-style peer/perspective memory.  CREATE IF NOT EXISTS
                # keeps live DB migrations safe and repeatable.
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS projection_manifest (
                        projection_id TEXT PRIMARY KEY,
                        memory_id TEXT NOT NULL,
                        projection_type TEXT NOT NULL,
                        source_hash TEXT NOT NULL,
                        projection_hash TEXT,
                        adapter_name TEXT,
                        adapter_version TEXT,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE INDEX IF NOT EXISTS idx_projection_manifest_memory ON projection_manifest(memory_id);
                    CREATE INDEX IF NOT EXISTS idx_projection_manifest_type_status ON projection_manifest(projection_type,status);
                    CREATE TABLE IF NOT EXISTS semantic_drawers (
                        drawer_id TEXT PRIMARY KEY,
                        memory_id TEXT NOT NULL,
                        layer TEXT,
                        start_offset INTEGER,
                        end_offset INTEGER,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS semantic_closets (
                        closet_id TEXT PRIMARY KEY,
                        drawer_id TEXT NOT NULL,
                        memory_id TEXT NOT NULL,
                        closet_text TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS peer_profiles (
                        peer_id TEXT PRIMARY KEY,
                        workspace TEXT NOT NULL DEFAULT 'openclaw',
                        role TEXT,
                        display_name TEXT,
                        stable_facts_json TEXT NOT NULL DEFAULT '[]',
                        preferences_json TEXT NOT NULL DEFAULT '[]',
                        goals_json TEXT NOT NULL DEFAULT '[]',
                        habits_json TEXT NOT NULL DEFAULT '[]',
                        constraints_json TEXT NOT NULL DEFAULT '[]',
                        confidence REAL DEFAULT 0.7,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE TABLE IF NOT EXISTS perspective_memories (
                        id TEXT PRIMARY KEY,
                        memory_id TEXT NOT NULL,
                        observer_peer_id TEXT NOT NULL,
                        observed_peer_id TEXT NOT NULL,
                        workspace TEXT NOT NULL DEFAULT 'openclaw',
                        session_id TEXT,
                        observation_type TEXT,
                        confidence REAL,
                        source_ids_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    );
                """)
                view_changed = _migrate_views(conn)
                fts5_changed = _migrate_fts5(conn)
            conn.commit()
            all_changed = changed + changed2 + view_changed + fts5_changed
            return {"ok": True, "db_path": str(db_path), "changed": all_changed, "change_count": len(all_changed)}
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def run_alembic_migrations(config: SuperMemoryConfig | None = None, revision: str = "head") -> dict[str, object]:
    """Run versioned Alembic migrations against the configured SQLite DB.

    This complements the legacy idempotent schema runner.  It is intended for
    reproducible CI/dev schema creation and future non-idempotent changes.
    """
    if not _HAS_ALEMBIC:
        return {"ok": False, "error": "alembic is not installed"}
    config = config or load_config()
    db_path = sqlite_path(config)
    project_root = Path(__file__).resolve().parents[1]
    alembic_ini = project_root / "alembic.ini"
    if not alembic_ini.exists():
        return {"ok": False, "error": f"missing alembic.ini: {alembic_ini}"}
    alembic_cfg = AlembicConfig(str(alembic_ini))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, revision)
    return {"ok": True, "db_path": str(db_path), "revision": revision, "runner": "alembic"}


def main() -> None:
    print(run_migrations())


if __name__ == "__main__":
    main()
