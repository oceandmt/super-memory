import sqlite3

from super_memory.cleanup import cleanup
from super_memory.config import load_config


def test_cleanup_repairs_legacy_session_health_view(tmp_path):
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\nsqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )

    cleanup(config_path=str(cfg_path))
    cfg = load_config(str(cfg_path))
    db_path = tmp_path / cfg.sqlite_path

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP VIEW IF EXISTS v_session_health")
        conn.execute(
            """
            CREATE VIEW v_session_health AS
            SELECT s.id AS session_id, COUNT(h.id) AS event_count
            FROM sessions s
            LEFT JOIN honcho_events_legacy_notnull h ON h.session_id = s.id
            GROUP BY s.id
            """
        )
        conn.commit()

    result = cleanup(config_path=str(cfg_path))
    assert result["ok"] is True
    assert (
        "recreated_view:v_session_health" in result["actions"]
        or "v_session_health" in result["migration"]["changed"]
    )
    assert result["checks"]["v_session_health"] == "ok"

    with sqlite3.connect(db_path) as conn:
        view_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name='v_session_health'"
        ).fetchone()[0]
        assert "honcho_events_legacy_notnull" not in view_sql
        assert "LEFT JOIN honcho_events h" in view_sql
        conn.execute("SELECT COUNT(*) FROM v_session_health").fetchone()
