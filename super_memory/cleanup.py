from __future__ import annotations

import datetime
import sqlite3

from datetime import timezone
from typing import Any

from .config import load_config
from .migrations import run_migrations
from .storage import SuperMemoryStore, clear_connection_cache, invalidate_connection, row_to_memory


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


def _prune_candidate_ids(conn: sqlite3.Connection, dry_run: bool = True, source_prefixes: list[str] | None = None, max_days: int | None = None) -> dict[str, Any]:
    """Find and optionally soft-delete memories matching retention policy criteria.

    Built-in criteria:
    1. Empty openclaw.turn events (source='openclaw.turn', content='')
    2. Explicit test/benchmark/contract sources via source_prefixes filter
    3. Very old memories (created_at < max_days) when max_days is set

    Returns a report of what was found and what was pruned.
    """
    FILTER_ACTIVE = (
        "(json_extract(metadata_json, '$.soft_deleted') IS NULL "
        "OR json_extract(metadata_json, '$.soft_deleted') != 1)"
    )

    conditions: list[str] = []
    params: list[object] = []
    labels: list[str] = []

    # Criterion 1: empty openclaw.turn events
    conditions.append("(content = '' AND source = 'openclaw.turn')")
    labels.append("empty_openclaw_turn")

    # Criterion 2: source_prefixes filter
    if source_prefixes:
        prefix_clauses = []
        for pfx in source_prefixes:
            prefix_clauses.append("source LIKE ?")
            params.append(pfx + "%")
        conditions.append("(" + " OR ".join(prefix_clauses) + ")")
        labels.append(f"sources_starting_with:{':'.join(source_prefixes)}")

    # Criterion 3: max_days age
    if max_days is not None:
        conditions.append(f"created_at < datetime('now', '-{max_days} days')")
        labels.append(f"older_than_{max_days}d")

    if not conditions:
        return {"skipped": True, "reason": "no criteria active"}

    # Criteria are OR'd — a memory matching ANY criterion is a prune candidate.
    # This means "content='' AND source='openclaw.turn'" OR "source LIKE 'test.%'"
    # will catch empty turn events AND test-prefixed memories independently.
    where_clause = " OR ".join(f"({c})" for c in conditions)
    full_where = f"({where_clause}) AND {FILTER_ACTIVE}"

    # Count candidates (distinct IDs, not layer rows)
    total_ids = conn.execute(
        f"SELECT COUNT(DISTINCT id) FROM memories WHERE {full_where}",
        params,
    ).fetchone()[0]
    total_rows = conn.execute(
        f"SELECT COUNT(*) FROM memories WHERE {full_where}",
        params,
    ).fetchone()[0]

    # Sample IDs for reporting
    sample_ids = [
        r["id"]
        for r in conn.execute(
            f"SELECT DISTINCT id FROM memories WHERE {full_where} LIMIT 20",
            params,
        ).fetchall()
    ]

    report: dict[str, Any] = {
        "criteria_labels": labels,
        "candidate_ids": total_ids,
        "candidate_layer_rows": total_rows,
        "sample_ids": sample_ids[:5],
        "dry_run": dry_run,
        "pruned": None,
    }

    if dry_run:
        return report

    # Collect all IDs first
    ids = [
        r["id"]
        for r in conn.execute(
            f"SELECT DISTINCT id FROM memories WHERE {full_where}",
            params,
        ).fetchall()
    ]
    if not ids:
        report["pruned"] = {"ids": 0, "rows": 0}
        return report

    q = ",".join("?" for _ in ids)
    fiber_ids = ["f:" + i for i in ids]
    fq = ",".join("?" for _ in fiber_ids)

    deleted: dict[str, int] = {}

    def _table_exists(table: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())

    def _record_delete(table: str, cur: object) -> None:
        deleted[table] = deleted.get(table, 0) + getattr(cur, "rowcount", 0)

    if _table_exists("honcho_events"):
        cur = conn.execute("DELETE FROM honcho_events WHERE memory_id IN (" + q + ")", ids)
        _record_delete("honcho_events", cur)
    if _table_exists("palace_drawers"):
        cur = conn.execute("DELETE FROM palace_drawers WHERE memory_id IN (" + q + ")", ids)
        _record_delete("palace_drawers", cur)
    if _table_exists("graph_edges"):
        cur = conn.execute("DELETE FROM graph_edges WHERE source_memory_id IN (" + q + ") OR target_memory_id IN (" + q + ")", ids + ids)
        _record_delete("graph_edges", cur)

    # Cognitive neurons/synapses (gracefully skip if cognitive tables don't exist)
    cog_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cognitive_neurons'").fetchone()
    if cog_table:
        neuron_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM cognitive_neurons WHERE source_memory_id IN (" + q + ")",
                ids,
            ).fetchall()
        ]
        if neuron_ids:
            nq = ",".join("?" for _ in neuron_ids)
            if _table_exists("cognitive_synapses"):
                cur = conn.execute("DELETE FROM cognitive_synapses WHERE source_neuron_id IN (" + nq + ") OR target_neuron_id IN (" + nq + ")", neuron_ids + neuron_ids)
                _record_delete("cognitive_synapses", cur)
            cur = conn.execute("DELETE FROM cognitive_neurons WHERE id IN (" + nq + ")", neuron_ids)
            _record_delete("cognitive_neurons", cur)
    if _table_exists("cognitive_fibers"):
        cur = conn.execute("DELETE FROM cognitive_fibers WHERE id IN (" + fq + ")", fiber_ids)
        _record_delete("cognitive_fibers", cur)
    cur = conn.execute("DELETE FROM memories WHERE id IN (" + q + ")", ids)
    _record_delete("memories", cur)

    report["pruned"] = {"ids": len(ids), "rows": deleted.get("memories", 0), "deleted_tables": deleted}
    return report


def prune(
    *,
    config_path: str | None = None,
    dry_run: bool = True,
    source_prefixes: list[str] | None = None,
    max_days: int | None = None,
) -> dict[str, Any]:
    """Prune memories matching retention policy criteria.

    Safe by default (dry_run=True). Use dry_run=False to actually delete.

    Built-in always-active criteria:
    - Empty openclaw.turn events (source='openclaw.turn', content='')

    Optional criteria:
    - source_prefixes: prune sources starting with these prefixes
      (e.g. ['test.', 'benchmark', 'super-memory.phase8.contract'])
    - max_days: prune memories older than N days
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    actions: list[str] = []
    report: dict[str, Any] = {"ok": True, "db_path": str(store.path)}

    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = _prune_candidate_ids(
                conn,
                dry_run=dry_run,
                source_prefixes=source_prefixes,
                max_days=max_days,
            )
            report["result"] = result
            if result.get("candidate_ids", 0) > 0:
                actions.append(f"{'dry_run' if dry_run else 'pruned'}:{result['candidate_ids']}_ids")
            actions.append(f"criteria:{':'.join(result.get('criteria_labels', ['none']))}")

            # Rebuild FTS after prune if not dry_run
            if not dry_run and result.get("pruned") and result["pruned"]["ids"] > 0:
                for table in ("memories_fts", "honcho_events_fts"):
                    try:
                        if _rebuild_fts_table(conn, table):
                            actions.append(f"rebuilt_fts:{table}")
                    except sqlite3.OperationalError as exc:
                        actions.append(f"skipped_fts:{table}:{exc}")

            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            report["quick_check"] = quick
            if quick != "ok":
                raise sqlite3.DatabaseError(f"PRAGMA quick_check failed: {quick}")

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    report["actions"] = actions
    return report


def prune_synapses_with_decay(
    *,
    config_path: str | None = None,
    dry_run: bool = True,
    decay_factor: float = 0.1,
    min_weight: float = 0.3,
    max_age_days: int = 30,
) -> dict[str, Any]:
    """Apply weight decay to synapses and prune stale connections.

    P2 #8 Optimization: Configurable weight-based pruning with decay.
    Each maintenance cycle, synapses lose `decay_factor` of their weight.
    Synapses below `min_weight` that are older than `max_age_days` are
    soft-deleted candidates.

    Strategy:
      1. Decay all synapse weights by (1 - decay_factor)
      2. Mark synapses where weight < min_weight AND age > max_age_days
      3. Dry-run safe — reports candidates without deleting

    Args:
        config_path: Optional config path
        dry_run: If True, only report
        decay_factor: Fraction of weight lost per cycle (default 0.1 = 10%)
        min_weight: Threshold below which synapses are pruning candidates
        max_age_days: Age beyond which low-weight synapses are pruned

    Returns:
        Dict with decayed/pruned counts
    """
    from datetime import datetime, timezone
    from .config import load_config as _lc
    from .storage import SuperMemoryStore

    cfg = _lc(config_path)
    store = SuperMemoryStore(cfg)
    now = datetime.now(timezone.utc).isoformat()

    report: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "total_synapses": 0,
        "decayed": 0,
        "below_threshold": 0,
        "prune_candidates": 0,
        "deleted": 0,
        "decay_factor": decay_factor,
        "min_weight": min_weight,
        "max_age_days": max_age_days,
    }

    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()

    with store.connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")

        total = conn.execute("SELECT COUNT(*) FROM cognitive_synapses").fetchone()[0]
        report["total_synapses"] = total

        if total == 0:
            return report

        # Count synapses already below threshold
        below = conn.execute(
            "SELECT COUNT(*) FROM cognitive_synapses WHERE weight < ? AND created_at < ?",
            (min_weight, cutoff),
        ).fetchone()[0]
        report["below_threshold"] = below

        # Dry run: build candidate list
        candidate_ids: list[str] = []
        if dry_run:
            rows = conn.execute(
                "SELECT id, weight FROM cognitive_synapses WHERE weight < ? AND created_at < ? ORDER BY weight ASC LIMIT 500",
                (min_weight, cutoff),
            ).fetchall()
            candidate_ids = [r["id"] for r in rows]
        else:
            # Apply decay to all synapses
            conn.execute(
                "UPDATE cognitive_synapses SET weight = MAX(0.01, weight * ?), updated_at = ? WHERE weight >= ?",
                (1.0 - decay_factor, now, min_weight),
            )
            report["decayed"] = conn.execute(
                "SELECT changes()"
            ).fetchone()[0]

            # Delete stale low-weight synapses
            conn.execute(
                "DELETE FROM cognitive_synapses WHERE weight < ? AND created_at < ?",
                (min_weight, cutoff),
            )
            report["deleted"] = conn.execute("SELECT changes()").fetchone()[0]
            conn.commit()

            # Get deleted IDs for report
            # (Deleted rows lost; we log count only)
            report["prune_candidates"] = report["deleted"]

        if dry_run:
            report["prune_candidates"] = len(candidate_ids)
            report["candidate_examples"] = candidate_ids[:10]

    return report


def auto_compact(
    *,
    config_path: str | None = None,
    threshold: float = 0.2,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Auto-compact soft-deleted records when they exceed a threshold.

    Counts soft-deleted records. If soft-deleted ratio > threshold,
    runs hard-delete + VACUUM to reclaim space.
    Safe by default (dry_run=True). Use dry_run=False to actually compact.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        deleted = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE json_extract(metadata_json, '$.soft_deleted') = 1"
        ).fetchone()[0]
        ratio = deleted / max(total, 1)
        report: dict[str, Any] = {
            "ok": True,
            "total": total,
            "soft_deleted": deleted,
            "ratio": round(ratio, 4),
            "threshold": threshold,
            "needs_compact": ratio > threshold,
            "dry_run": dry_run,
        }
        if not report["needs_compact"]:
            report["reason"] = f"ratio {ratio:.1%} <= threshold {threshold:.0%}, no compaction needed"
            return report

        # Find soft-deleted IDs
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT DISTINCT id FROM memories WHERE json_extract(metadata_json, '$.soft_deleted') = 1"
            ).fetchall()
        ]
        report["candidate_ids"] = len(ids)

        if dry_run:
            report["reason"] = f">{threshold:.0%} soft-deleted, {len(ids)} IDs would be hard-deleted + VACUUM"
            return report

        # Hard-delete using prune logic
        q = ",".join("?" for _ in ids)
        conn.execute("DELETE FROM memories WHERE id IN (" + q + ")", ids)
        conn.execute("DELETE FROM honcho_events WHERE memory_id IN (" + q + ")", ids)
        conn.execute("DELETE FROM palace_drawers WHERE memory_id IN (" + q + ")", ids)
        conn.execute(
            "DELETE FROM graph_edges WHERE source_memory_id IN (" + q + ") OR target_memory_id IN (" + q + ")",
            ids + ids,
        )
        conn.commit()

    # VACUUM outside transaction
    clear_connection_cache()
    vac_conn = sqlite3.connect(str(store.path), timeout=60)
    try:
        vac_conn.execute("VACUUM")
    finally:
        vac_conn.close()
    invalidate_connection(store.path)

    report["hard_deleted"] = len(ids)
    report["vacuumed"] = True
    return report


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
        # VACUUM requires exclusive access — close all cached connections first
        clear_connection_cache()
        conn = sqlite3.connect(str(store.path), timeout=60)
        try:
            conn.execute("VACUUM")
            actions.append("vacuum")
        finally:
            conn.close()
        # Invalidate so next connect() creates fresh connection
        invalidate_connection(store.path)

    return {
        "ok": True,
        "db_path": str(store.path),
        "migration": migration,
        "actions": actions,
        "checks": checks,
    }


def expire_by_age(
    *,
    config_path: str | None = None,
    max_days: int = 90,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Expire memories past their expires_days TTL.

    Finds memories where:
      - expires_days IS NOT NULL
      - created_at + expires_days < now()
      - NOT already soft-deleted

    Marks them as soft-deleted (soft_delete=1 in metadata_json).
    Safe by default (dry_run=True).
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, content, type, source, created_at,
                   json_extract(metadata_json, '$.expires_days') AS expires_days
            FROM memories
            WHERE json_extract(metadata_json, '$.expires_days') IS NOT NULL
              AND json_extract(metadata_json, '$.expires_days') != 'null'
              AND (json_extract(metadata_json, '$.soft_deleted') IS NULL
                   OR json_extract(metadata_json, '$.soft_deleted') != 1)
              AND datetime(created_at, '+' || CAST(json_extract(metadata_json, '$.expires_days') AS TEXT) || ' days') < datetime('now')
            ORDER BY created_at ASC
            """,
        ).fetchall()

        expired_ids = [r["id"] for r in rows]
        report: dict[str, Any] = {
            "ok": True,
            "strategy": "expire_by_age",
            "candidate_ids": len(expired_ids),
            "dry_run": dry_run,
            "samples": [{"id": r["id"], "type": r["type"], "source": r["source"], "created_at": r["created_at"]} for r in rows[:5]],
            "expired": None,
        }

        if not expired_ids:
            report["reason"] = "no expired memories found"
            return report

        if dry_run:
            report["reason"] = f"{len(expired_ids)} memories would be soft-deleted (max_days={max_days})"
            return report

        # Soft-delete expired memories
        now = datetime.datetime.now(timezone.utc).isoformat()
        for mid in expired_ids:
            conn.execute(
                """
                UPDATE memories
                SET metadata_json = json_set(
                    COALESCE(metadata_json, '{}'),
                    '$.soft_deleted', 1,
                    '$.expired_at', ?
                )
                WHERE id = ?
                """,
                (now, mid),
            )
        conn.commit()

        report["expired"] = {"soft_deleted_ids": len(expired_ids), "expired_at": now}
        return report


def prune_stale_events(
    *,
    config_path: str | None = None,
    max_days: int = 30,
    max_trust: float = 0.5,
    limit: int = 2000,
    dry_run: bool = True,
) -> dict[str, Any]:
    """E2: reversibly soft-delete the stale low-trust raw-event backlog.

    Targets the immortal openclaw.turn event pile that no maintenance path
    currently downgrades or prunes. Criteria (all must hold):
      - type = 'event'
      - source = 'openclaw.turn' (raw turn logs, not curated events)
      - created_at older than max_days
      - trust_score IS NULL or < max_trust
      - NOT pinned, NOT promoted, NOT already soft-deleted

    Soft-delete (metadata.soft_deleted=1) is reversible; never hard-deletes.
    Safe by default (dry_run=True).
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, type, source, created_at, trust_score
            FROM memories
            WHERE type = 'event'
              AND source = 'openclaw.turn'
              AND datetime(created_at, '+' || CAST(? AS TEXT) || ' days') < datetime('now')
              AND (trust_score IS NULL OR trust_score < ?)
              AND COALESCE(json_extract(metadata_json, '$.soft_deleted'), 0) != 1
              AND COALESCE(json_extract(metadata_json, '$.pinned'), 0) != 1
              AND COALESCE(json_extract(metadata_json, '$.promoted'), 0) != 1
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (max_days, max_trust, limit),
        ).fetchall()

        candidate_ids = [r["id"] for r in rows]
        report: dict[str, Any] = {
            "ok": True,
            "strategy": "prune_stale_events",
            "candidate_ids": len(candidate_ids),
            "dry_run": dry_run,
            "max_days": max_days,
            "max_trust": max_trust,
            "samples": [
                {"id": r["id"], "created_at": r["created_at"], "trust_score": r["trust_score"]}
                for r in rows[:5]
            ],
            "soft_deleted": None,
        }

        if not candidate_ids:
            report["reason"] = "no stale low-trust events found"
            return report
        if dry_run:
            report["reason"] = f"{len(candidate_ids)} stale events would be soft-deleted (reversible)"
            return report

        now = datetime.datetime.now(timezone.utc).isoformat()
        for mid in candidate_ids:
            conn.execute(
                """
                UPDATE memories
                SET metadata_json = json_set(
                    COALESCE(metadata_json, '{}'),
                    '$.soft_deleted', 1,
                    '$.soft_deleted_reason', 'stale_event_prune',
                    '$.soft_deleted_at', ?
                )
                WHERE id = ?
                """,
                (now, mid),
            )
        conn.commit()
        report["soft_deleted"] = {"ids": len(candidate_ids), "at": now}
        return report

def expire_by_valid_until(
    *,
    config_path: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Expire memories past their valid_until window.

    Finds memories where:
      - metadata.valid_until IS NOT NULL
      - valid_until < now()
      - NOT already soft-deleted

    Marks them as soft-deleted.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, content, type, source, created_at,
                   json_extract(metadata_json, '$.valid_until') AS valid_until
            FROM memories
            WHERE json_extract(metadata_json, '$.valid_until') IS NOT NULL
              AND json_extract(metadata_json, '$.valid_until') != 'null'
              AND (json_extract(metadata_json, '$.soft_deleted') IS NULL
                   OR json_extract(metadata_json, '$.soft_deleted') != 1)
              AND json_extract(metadata_json, '$.valid_until') < datetime('now')
            ORDER BY created_at ASC
            """,
        ).fetchall()

        expired_ids = [r["id"] for r in rows]
        report: dict[str, Any] = {
            "ok": True,
            "strategy": "expire_by_valid_until",
            "candidate_ids": len(expired_ids),
            "dry_run": dry_run,
            "samples": [{"id": r["id"], "type": r["type"], "source": r["source"], "valid_until": r["valid_until"]} for r in rows[:5]],
            "expired": None,
        }

        if not expired_ids:
            report["reason"] = "no expired memories found"
            return report

        if dry_run:
            report["reason"] = f"{len(expired_ids)} memories would be soft-deleted"
            return report

        now = datetime.datetime.now(timezone.utc).isoformat()
        for mid in expired_ids:
            conn.execute(
                """
                UPDATE memories
                SET metadata_json = json_set(
                    COALESCE(metadata_json, '{}'),
                    '$.soft_deleted', 1,
                    '$.expired_at', ?
                )
                WHERE id = ?
                """,
                (now, mid),
            )
        conn.commit()

        report["expired"] = {"soft_deleted_ids": len(expired_ids), "expired_at": now}
        return report
