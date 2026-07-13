from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass
from typing import Any

from . import memory_core
from . import lifecycle
from .semantic import semantic_doctor, semantic_index, semantic_verify



def _was_run_recently(config_path: str | None = None, key: str = "maintenance_run", within_hours: int = 1) -> bool:
    """Check if a maintenance step was run recently to avoid redundant execution."""
    from .config import load_config
    from .storage import SuperMemoryStore
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS lifecycle_state (key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        row = conn.execute(
            "SELECT updated_at FROM lifecycle_state WHERE key = ?", (key,)
        ).fetchone()
        if row:
            try:
                last = datetime.fromisoformat(row["updated_at"])
                return (datetime.now(timezone.utc) - last).total_seconds() < within_hours * 3600
            except Exception:
                pass
    return False


def _record_run(config_path: str | None = None, key: str = "maintenance_run") -> None:
    """Record that a maintenance step was performed."""
    import json
    from .config import load_config
    from .storage import SuperMemoryStore
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS lifecycle_state (key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO lifecycle_state (key, payload_json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps({"run": True, "note": "auto-maintenance"}), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def _run_cognitive_cycle(config_path: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Auto-cycle cognitive workflow: expire stale predictions, check active hypotheses.

    P0 Optimization: Wire existing hypothesis/prediction/evidence/verify tools
    into maintenance so they run automatically instead of requiring manual invocation.
    """
    report: dict[str, Any] = {"ok": True, "dry_run": dry_run, "expired": 0, "active_hypotheses": 0, "notes": []}
    from . import bridge as _bridge, telemetry as _telemetry, config as _config, storage as _storage

    # Telemetry collection (P3 #9)
    try:
        report["steps"]["telemetry"] = _telemetry.telemetry_status()
    except Exception as exc:
        report["steps"]["telemetry"] = {"ok": False, "error": str(exc)}

        # Step 1: Expire stale predictions
        expire_r = _bridge.expire_predictions(config_path=config_path)
        report["expired"] = expire_r.get("count", 0)
        if expire_r.get("count", 0) > 0:
            report["notes"].append(f"Expired {expire_r['count']} stale predictions")

        # Step 2: Check active hypotheses for auto-resolve
        hyps = _bridge.hypothesis_list(status="active", limit=50, config_path=config_path)
        active = hyps.get("hypotheses", [])
        report["active_hypotheses"] = len(active)

        # Step 3: Collect recent memories as potential evidence for active hypotheses
        if not dry_run and active:
            from .config import load_config as _lc
            from .storage import SuperMemoryStore
            import json, sqlite3
            cfg = _lc(config_path)
            store = SuperMemoryStore(cfg)
            with store.connect() as conn:
                for hyp in active[:3]:  # Limit to top 3 to avoid long turns
                    # Look for memories that could be evidence
                    keywords = hyp["content"].lower().split()[:5]
                    for kw in keywords:
                        if len(kw) < 3:
                            continue
                        rows = conn.execute(
                            "SELECT id, content, created_at FROM memories WHERE content LIKE ? AND created_at > ? AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1 ORDER BY created_at DESC LIMIT 3",
                            (f"%{kw}%", hyp.get("updated_at", "")),
                        ).fetchall()
                        for row in rows:
                            # Check if already evidence
                            ev_exists = conn.execute(
                                "SELECT id FROM cognitive_evidence WHERE hypothesis_id=? AND content=?",
                                (hyp["id"], row["content"]),
                            ).fetchone()
                            if not ev_exists:
                                # Auto-add as neutral evidence (weight 0.3 to avoid bias)
                                _bridge.evidence_add(
                                    hyp["id"],
                                    content=row["content"][:500],
                                    direction="for",
                                    weight=0.3,
                                    config_path=config_path,
                                )
                                report["notes"].append(f"Auto-evidence for {hyp['id'][:24]}: '{row['content'][:60]}...'")

        # Step 4: Check for confirmed/refuted hypotheses to auto-promote
        confirmed = _bridge.hypothesis_list(status="confirmed", limit=10, config_path=config_path).get("hypotheses", [])
        for hyp in confirmed:
            report["notes"].append(f"Confirmed hypothesis: {hyp['content'][:80]}")
        refuted = _bridge.hypothesis_list(status="refuted", limit=10, config_path=config_path).get("hypotheses", [])
        for hyp in refuted:
            report["notes"].append(f"Refuted hypothesis: {hyp['content'][:80]}")

    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
    return report


def maintenance_run(*, dry_run: bool = True, limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Run safe Super Memory maintenance in canonical-first order.

    This is intentionally non-destructive except for soft-delete/metadata marks in
    lifecycle cleanup when dry_run is false. It never hard-deletes or truncates
    canonical markdown.

    Auto-schedule: tracks last run time and skips if run within 1 hour.
    """
    recently = _was_run_recently(config_path, "maintenance_run")
    report: dict[str, Any] = {
        "ok": True, "dry_run": dry_run, "steps": {},
        "auto_schedule": {"skipped_recently": recently, "window_hours": 1},
    }
    if recently:
        report["note"] = "Skipped: maintenance was run within the last hour"
        return report

    report["steps"]["embedding_doctor"] = memory_core.embedding_doctor(config_path=config_path)
    try:
        report["steps"]["lifecycle_quality_cleanup"] = lifecycle.quality_cleanup(dry_run=dry_run, limit=limit, config_path=config_path)
    except Exception as exc:
        report["steps"]["lifecycle_quality_cleanup"] = {"ok": False, "error": str(exc), "retryable": "locked" in str(exc).lower()}

    # Semantic indexing is safe and idempotent. Keep bounded to avoid long MCP turns.
    try:
        report["steps"]["semantic_doctor"] = semantic_doctor(config_path=config_path)
        if not dry_run and report["steps"]["semantic_doctor"].get("ok"):
            vector_count = int(report["steps"]["semantic_doctor"].get("vector_count") or 0)
            if vector_count == 0:
                report["steps"]["semantic_index"] = semantic_index(config_path=config_path, rebuild=False, batch_size=4, limit=min(limit, 25))
            else:
                report["steps"]["semantic_index"] = {"ok": True, "skipped": True, "reason": "existing vector index present", "vector_count": vector_count}
            report["steps"]["semantic_verify"] = semantic_verify(config_path=config_path, query="Super Memory durable pack OpenClaw agent role baseline", limit=5)
    except Exception as exc:
        report["steps"]["semantic_error"] = str(exc)

    # Short-term promotion lifecycle
    report["steps"]["short_term_audit"] = memory_core.short_term_audit(limit=limit, config_path=config_path)
    report["steps"]["short_term_repair"] = memory_core.short_term_repair(limit=limit, dry_run=True, config_path=config_path)

    # Dreaming lifecycle
    report["steps"]["dreaming_audit"] = memory_core.dreaming_audit(config_path=config_path)
    if report["steps"].get("lifecycle_quality_cleanup", {}).get("retryable"):
        report["steps"]["dreaming_run"] = {"ok": True, "skipped": True, "reason": "database lock contention; retry maintenance later"}
    else:
        report["steps"]["dreaming_run"] = memory_core.dreaming_run(limit=min(limit, 200), dry_run=dry_run, config_path=config_path)

    # Cognitive workflow auto-cycle (P0) — wire hypothesis→predict→evidence→verify
    try:
        report["steps"]["cognitive_cycle"] = _run_cognitive_cycle(config_path=config_path, dry_run=dry_run)
    except Exception as exc:
        report["steps"]["cognitive_cycle"] = {"ok": False, "error": str(exc)}

    # Conversation mining (P1) — auto-extract memories from Honcho events
    try:
        if not dry_run:
            from .config import load_config as _lc
            from .storage import SuperMemoryStore
            cfg = _lc(config_path)
            store = SuperMemoryStore(cfg)
            from .conversation_miner import run_conversation_mining
            report["steps"]["conversation_mining"] = run_conversation_mining(store, dry_run=dry_run, limit=min(limit, 100))
        else:
            report["steps"]["conversation_mining"] = {"ok": True, "skipped": True, "reason": "dry-run mode; enable with dry_run=False"}
    except Exception as exc:
        report["steps"]["conversation_mining"] = {"ok": False, "error": str(exc)}

    # Cluster-based dedup (P1) — Jaccard similarity on memories
    try:
        from .config import load_config as _lc2
        from .storage import SuperMemoryStore as _sms
        from .mempalace.dedup import deduplicate_memories
        cfg2 = _lc2(config_path)
        store2 = _sms(cfg2)
        report["steps"]["cluster_dedup"] = deduplicate_memories(store2, threshold=0.6, dry_run=True, limit=min(limit, 500))
    except Exception as exc:
        report["steps"]["cluster_dedup"] = {"ok": False, "error": str(exc)}

    # Self-improvement cycle (P4) — integrate preference detection
    try:
        from .self_improve import run_self_improve_cycle
        report["steps"]["self_improve"] = run_self_improve_cycle(config_path=config_path, dry_run=dry_run)
    except Exception as exc:
        report["steps"]["self_improve"] = {"ok": False, "error": str(exc)}

    # Schema assimilation (P2) — integrate with lifecycle
    try:
        if not _was_run_recently(config_path, "schema_assimilation", within_hours=4):
            from .schema_assimilation import run_schema_assimilation as _run
            from .config import load_config as _lc
            from .storage import SuperMemoryStore
            cfg = _lc(config_path)
            store = SuperMemoryStore(cfg)
            report["steps"]["schema_assimilation"] = _run(store, dry_run=dry_run)
            _record_run(config_path, "schema_assimilation")
        else:
            report["steps"]["schema_assimilation"] = {"ok": True, "skipped": True, "reason": "run within last 4 hours"}
    except Exception as exc:
        report["steps"]["schema_assimilation"] = {"ok": False, "error": str(exc)}

    # Hippocampal replay (P1) — integrate with lifecycle
    try:
        if not _was_run_recently(config_path, "hippocampal_replay", within_hours=2):
            from .hippocampal_replay import run_hippocampal_replay as _run, HippocampalReplayConfig
            from .config import load_config as _lc
            from .storage import SuperMemoryStore
            cfg = _lc(config_path)
            store = SuperMemoryStore(cfg)
            hc = HippocampalReplayConfig(dry_run=dry_run)
            _replay_res = _run(store, hc)
            # E24: run_hippocampal_replay returns a ReplayResult dataclass, which
            # is not JSON-serializable. maintenance_run is a live MCP tool whose
            # return is json.dumps()'d by mcp_server -- assigning the raw object
            # crashed the tool whenever replay actually ran (not skipped).
            # Normalise to a plain dict.
            if is_dataclass(_replay_res) and not isinstance(_replay_res, type):
                _replay_res = asdict(_replay_res)
            report["steps"]["hippocampal_replay"] = _replay_res
            _record_run(config_path, "hippocampal_replay")
        else:
            report["steps"]["hippocampal_replay"] = {"ok": True, "skipped": True, "reason": "run within last 2 hours"}
    except Exception as exc:
        report["steps"]["hippocampal_replay"] = {"ok": False, "error": str(exc)}


    # Dream consolidation engine (P0 #2) — idle-time memory consolidation
    try:
        if not _was_run_recently(config_path, "dream_engine", within_hours=4):
            report["steps"]["dream_engine"] = dream_engine.run_dream_cycle(
                SuperMemoryStore(load_config(config_path)),
                dry_run=dry_run,
                window_hours=48,
                max_insights=5,
                config_path=config_path,
            )
            _record_run(config_path, "dream_engine")
        else:
            report["steps"]["dream_engine"] = {"ok": True, "skipped": True, "reason": "run within last 4 hours"}
    except Exception as exc:
        report["steps"]["dream_engine"] = {"ok": False, "error": str(exc)}

    # E7: write-contract reconcile — heal cross-layer drift from best-effort
    # saves (a downstream layer failing after markdown succeeded leaves a gap).
    # Reconcile backfills missing layer projections. Throttled to hourly.
    try:
        if not _was_run_recently(config_path, "write_contract_reconcile", within_hours=1):
            from . import bridge as _wc_bridge
            report["steps"]["write_contract_reconcile"] = _wc_bridge.write_contract_reconcile(
                limit=200, config_path=config_path
            )
            _record_run(config_path, "write_contract_reconcile")
        else:
            report["steps"]["write_contract_reconcile"] = {"ok": True, "skipped": True, "reason": "run within last hour"}
    except Exception as exc:
        report["steps"]["write_contract_reconcile"] = {"ok": False, "error": str(exc)}

    # E2: stale-event pruning — downgrade the immortal low-trust event backlog.
    # Reversible soft-delete; throttled to weekly. Runs live even in a dry_run
    # maintenance pass is NOT desired, so it honors the pass-level dry_run flag.
    try:
        if not _was_run_recently(config_path, "stale_event_prune", within_hours=168):
            from .cleanup import prune_stale_events
            report["steps"]["stale_event_prune"] = prune_stale_events(
                config_path=config_path,
                max_days=30,
                max_trust=0.5,
                limit=2000,
                dry_run=dry_run,
            )
            if not dry_run:
                _record_run(config_path, "stale_event_prune")
        else:
            report["steps"]["stale_event_prune"] = {"ok": True, "skipped": True, "reason": "run within last 7 days"}
    except Exception as exc:
        report["steps"]["stale_event_prune"] = {"ok": False, "error": str(exc)}

    # Synaptic pruning with weight decay (P2 #8) — maintain cognitive graph health
    try:
        from .cleanup import prune_synapses_with_decay
        report["steps"]["synaptic_pruning"] = prune_synapses_with_decay(
            config_path=config_path,
            dry_run=True,  # Always dry-run by default (safe)
            decay_factor=0.1,
            min_weight=0.3,
            max_age_days=30,
        )
    except Exception as exc:
        report["steps"]["synaptic_pruning"] = {"ok": False, "error": str(exc)}

    from . import bridge, telemetry

    # Telemetry collection (P3 #9)
    try:
        report["steps"]["telemetry"] = telemetry.telemetry_status()
    except Exception as exc:
        report["steps"]["telemetry"] = {"ok": False, "error": str(exc)}

    from . import bridge, dream_engine
    report["steps"]["cross_layer_health"] = bridge.cross_layer_health(config_path=config_path)
    report["steps"]["durable_pack_status"] = bridge.durable_pack_status(config_path=config_path)
    report["ok"] = all(not isinstance(v, dict) or v.get("ok", True) for v in report["steps"].values())

    _record_run(config_path, "maintenance_run")
    return report
