"""Super Memory service: canonical-first save orchestration, recall, dedup, sync.

The central orchestration layer that:
- Routes saves through SAVE_ORDER (markdown → mempalace → honcho → neural_memory)
- Falls back gracefully when markdown is unavailable
- Deduplicates by content_hash
- Enriches records with affect (arousal/valence)
- Expands queries and fuses results via RRF across 4 layers
"""

from __future__ import annotations

import importlib.util as _importlib_util

from .hooks import TurnContext
from .layers import MemoryBackend, SQLiteLayerBackend, WorkspaceMarkdownBackend
from .models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType, SaveResult, SuperMemoryConfig
from .observability import traced
from .storage import SuperMemoryStore
from .write_contract import register_memory as _wc_register_memory, find_duplicate as _wc_find_duplicate, ensure_schema as _wc_ensure_schema

_HAS_STRUCTLOG = _importlib_util.find_spec("structlog") is not None
if _HAS_STRUCTLOG:
    import structlog as _structlog
    logger = _structlog.get_logger("super-memory.service")
else:
    import logging as _logging
    logger = _logging.getLogger("super-memory.service")

SAVE_ORDER = [
    MemoryLayer.WORKSPACE_MARKDOWN,
    MemoryLayer.MEMPALACE,
    MemoryLayer.HONCHO,
    MemoryLayer.NEURAL_MEMORY,
]


def infer_project_for_record(record: MemoryRecord, workspace_root: str | None = None) -> str | None:
    """Infer a project for records that arrive without explicit project metadata.

    Conservative and deterministic: it only fills obvious project names from
    source paths, cwd/workspace paths, tags, or strong content mentions.
    """
    if record.project:
        return record.project
    text = " ".join([record.content[:2000], record.source or "", " ".join(record.tags or [])]).lower()
    source = (record.source or "").replace("\\", "/")
    if "/projects/" in source:
        tail = source.split("/projects/", 1)[1].split("/", 1)[0]
        if tail:
            return tail
    if "super-memory-github" in text or "projects/super-memory-github" in text:
        return "super-memory-github"
    if "super memory" in text or "super-memory" in text or "super_memory" in text:
        return "super-memory"
    if "openclaw-memory-system" in text:
        return "openclaw-memory-system"
    if ("source:neural_memory" in text or "openclaw-bridge" in text or "route:local-neural" in text or "source:memory" in text) and (record.scope.value == "project" or "scope:project" in text):
        return "openclaw-memory-system"
    if workspace_root and "super-memory-github" in str(workspace_root).lower() and ("super-memory" in text or "super_memory" in text):
        return "super-memory-github"
    return None


def _run_auto_deep_background() -> None:
    """Run auto_deep in background thread, best-effort."""
    try:
        from .auto_deep import run_deep_engine
        result = run_deep_engine()
        logger.info(
            "auto_deep.completed",
            grade=result.qualify.grade,
            avg_score=result.audit.stats.get("avg_score"),
            duration_ms=f"{result.total_duration_ms:.0f}",
        )
    except Exception as exc:
        logger.debug("auto_deep.background_failed", error=f"{type(exc).__name__}: {exc}")


class SuperMemoryService:
    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.backends: dict[MemoryLayer, MemoryBackend] = {
            MemoryLayer.WORKSPACE_MARKDOWN: WorkspaceMarkdownBackend(config),
            MemoryLayer.MEMPALACE: SQLiteLayerBackend(config, MemoryLayer.MEMPALACE),
            MemoryLayer.HONCHO: SQLiteLayerBackend(config, MemoryLayer.HONCHO),
            MemoryLayer.NEURAL_MEMORY: SQLiteLayerBackend(config, MemoryLayer.NEURAL_MEMORY),
        }
        self.store = SuperMemoryStore(config)

    def save(self, record: MemoryRecord) -> list[SaveResult]:
        """Save through the canonical-first layered order with Markdown-fail fallback.

        Markdown is the canonical layer. If it fails:
        - Downstream SQLite layers still run (no data loss).
        - Results from SQLite layers carry `pending_canonical_sync=True`.
        - Call `flush_pending()` to replay those records into Markdown when the
          workspace path becomes available.

        After filesystem markdown save succeeds, also write a workspace_markdown
        row into the shared SQLite memories table so all 4 layers are visible
        through a single SQL-based pane of glass.
        """

        import hashlib

        results: list[SaveResult] = []
        markdown_ok = False

        # Compute content hash for cross-layer drift detection
        content_hash = hashlib.sha256(record.content.encode("utf-8", errors="replace")).hexdigest()
        record.metadata["content_hash"] = content_hash

        # E5: unified trust pathway — assign a source-aware default when the
        # caller did not set one, instead of leaving trust_score NULL. Uses the
        # single content-quality heuristic (_compute_trust) then adjusts by source.
        if record.trust_score is None:
            try:
                from .data_improvement import _compute_trust
                base = _compute_trust(record.content, record.type.value)
            except Exception:
                base = 0.5
            src = (record.source or "").lower()
            if src in ("direct", "boss", "user") or src.startswith("user"):
                base += 0.15  # explicit human-authored knowledge
            elif src == "openclaw.turn":
                base -= 0.15  # raw auto-logged turns are least trusted
            elif src.startswith("super-memory.dream") or src.startswith("super-memory.auto"):
                base -= 0.05  # machine-derived
            record.trust_score = round(min(1.0, max(0.1, base)), 3)
            record.metadata["trust_source"] = "service.save.default"

        # Project inference/backfill for consistent project graph and recall scoping.
        inferred_project = infer_project_for_record(record, workspace_root=str(self.config.workspace_root))
        if inferred_project and not record.project:
            record.project = inferred_project
            record.metadata["project_inferred"] = True
            record.metadata["project_inference_source"] = "service.save"

        # P0 Dedup guard: skip if same content_hash exists in active workspace_markdown
        dedup_result = self.dedup_check(record)
        if dedup_result.get("skipped"):
            logger.info(
                "save.dedup_skip",
                skipped_id=record.id,
                matched_id=dedup_result["matched_id"],
                content_type=dedup_result.get("matched_type"),
                content_hash=content_hash[:16],
            )
            # Mark metadata to indicate dedup was triggered
            record.metadata["dedup_skipped"] = True
            record.metadata["dedup_matched_id"] = dedup_result["matched_id"]
            record.metadata["dedup_original_id"] = record.id
            # Return existing record reference only. Do NOT write any marker row here:
            # writing with matched_id would overwrite the canonical workspace row, and
            # writing with a new ID would reintroduce duplicate noise.
            return [SaveResult(layer=MemoryLayer.WORKSPACE_MARKDOWN, ok=True,
                               message=f"dedup-skip: matched {dedup_result['matched_id']}",
                               reference=dedup_result["matched_id"])]

        # P0 Firewall: check content before saving
        try:
            from .pipeline_integration import run_safety_firewall, enrich_with_relations, check_triggers
            fw = run_safety_firewall(record.content)
            if fw["blocked"]:
                logger.warning("save.firewall_blocked", reason=fw["reason"], memory_id=record.id)
                record.metadata["firewall_blocked"] = True
                record.metadata["firewall_reason"] = fw["reason"]
            # P1 Relations/Structure/Trigger enrichment (non-blocking)
            meta = record.metadata
            enrich_with_relations(meta, record.content, source=record.source)
        except Exception as exc:
            logger.debug("save.pipeline_enrich_failed", error=f"{type(exc).__name__}: {exc}")

        # P0 Dedup & freshness metadata
        try:
            from .safety.freshness import evaluate_freshness
            from datetime import timezone
            fr = evaluate_freshness(record.created_at)
            record.metadata["freshness_level"] = fr.level.value
            record.metadata["freshness_score"] = fr.score
        except Exception:
            pass

        # Enrich with arousal/valence
        arousal_log: dict | None = None
        try:
            from .affect import enrich_record as _enrich
            enriched = _enrich(record)
            arousal_log = {
                "arousal": record.metadata.get("arousal"),
                "valence": record.metadata.get("valence"),
            }
            record = enriched
        except Exception as exc:
            logger.warning("save.affect_enrich_failed", error=f"{type(exc).__name__}: {exc}")

        # P2 #7 Async enrichment deriver (non-blocking, doesn't affect response)
        try:
            from .deriver import enrich_async
            enrich_async(record.id, record.content)
        except Exception:
            pass

        def _extra() -> dict[str, object]:
            return {
                "memory_id": record.id,
                "memory_type": record.type.value,
                "scope": record.scope.value,
                "agent_id": record.agent_id,
                "project": record.project,
                "layers": [r.layer.value for r in results],
                "ok_layers": [r.layer.value for r in results if r.ok],
                "failed_layers": [r.layer.value for r in results if not r.ok],
            }

        with traced("service.save", extra=_extra):
            for layer in SAVE_ORDER:
                if layer not in self.config.enabled_layers:
                    continue
                if self.config.require_canonical_first and layer != MemoryLayer.WORKSPACE_MARKDOWN:
                    if not markdown_ok:
                        # Markdown failed — save into SQLite with fallback flag
                        result = self._fallback_save(layer, record)
                        results.append(result)
                        continue
                try:
                    results.append(self.backends[layer].save(record))
                    if layer == MemoryLayer.WORKSPACE_MARKDOWN:
                        markdown_ok = results[-1].ok
                        # ALSO write workspace_markdown row into shared SQLite table
                        # so all 4 layers are visible in a single SQL query.
                        if markdown_ok:
                            try:
                                self._save_markdown_to_sqlite(record)
                            except Exception as exc:
                                logger.warning(
                                    "workspace_markdown sqlite mirror failed (non-fatal)",
                                    memory_id=record.id,
                                    error=f"{type(exc).__name__}: {exc}",
                                )
                except Exception as exc:
                    result = SaveResult(layer=layer, ok=False, message=f"{type(exc).__name__}: {exc}")
                    if layer == MemoryLayer.WORKSPACE_MARKDOWN:
                        markdown_ok = False
                    elif not markdown_ok and self.config.require_canonical_first:
                        result.pending_canonical_sync = True
                    results.append(result)

        # Log affect stats for observability
        if arousal_log is not None:
            logger.info("save.affect", arousal=arousal_log.get("arousal"), valence=arousal_log.get("valence"), memory_id=record.id)

        # P5: Auto Deep quality check after every N saves (triggered by counter)
        try:
            # Increment save counter in meta store
            counter = int(self.store._get_meta("auto_deep_save_counter") or "0")
            counter += 1
            self.store._set_meta("auto_deep_save_counter", str(counter))
            # Run auto_deep every 50 saves
            if counter % 50 == 0:
                logger.info("save.auto_deep_trigger", save_count=counter)
                import threading
                threading.Thread(target=_run_auto_deep_background, daemon=True).start()
        except Exception:
            pass

        return results

    def dedup_check(self, record: MemoryRecord) -> dict[str, object]:
        """Check if an active record with the same content_hash already exists.

        Returns {"skipped": True, "matched_id": "..."} when a duplicate is found,
        or {"skipped": False} if the content is unique.
        """
        import hashlib

        content_hash = record.metadata.get("content_hash")
        if not content_hash:
            content_hash = hashlib.sha256(record.content.encode("utf-8", errors="replace")).hexdigest()
        FILTER_ACTIVE = (
            "(json_extract(metadata_json, '$.soft_deleted') IS NULL "
            "OR json_extract(metadata_json, '$.soft_deleted') != 1)"
        )
        try:
            with self.store.connect() as conn:
                wc_dup = _wc_find_duplicate(conn, record.content, record.metadata, source=record.source)
            if wc_dup.get("skipped"):
                return {"skipped": True, "matched_id": wc_dup["matched_id"], "matched_content": "", "matched_type": "unknown", "reason": wc_dup.get("reason")}
        except Exception:
            pass
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT id, content, type, created_at FROM memories "
                "WHERE content_hash = ? AND layer = 'workspace_markdown' AND "
                + FILTER_ACTIVE +
                " ORDER BY created_at DESC LIMIT 1",
                (content_hash,),
            ).fetchone()
        if row is not None:
            return {"skipped": True, "matched_id": row["id"], "matched_content": row["content"][:200], "matched_type": row["type"]}
        return {"skipped": False}

    def _save_markdown_to_sqlite(self, record: MemoryRecord) -> None:
        """Mirror the workspace_markdown layer into the shared SQLite memories table.

        This is a derived (non-canonical) write for visibility only.
        The canonical source remains the filesystem markdown file.
        """

        import json

        tags = record.normalized_tags()
        pending_sync = record.metadata.get("pending_canonical_sync", False)
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memories
                (id, layer, content, type, scope, agent_id, session_id, project,
                 tags_json, source, trust_score, created_at, metadata_json,
                 pending_canonical_sync, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    MemoryLayer.WORKSPACE_MARKDOWN.value,
                    record.content,
                    record.type.value,
                    record.scope.value,
                    record.agent_id,
                    record.session_id,
                    record.project,
                    json.dumps(tags, ensure_ascii=False),
                    record.source,
                    record.trust_score,
                    record.created_at.isoformat(),
                    json.dumps(record.metadata, ensure_ascii=False),
                    1 if pending_sync else 0,
                    record.metadata.get("content_hash"),
                ),
            )
            try:
                _wc_register_memory(conn, record, MemoryLayer.WORKSPACE_MARKDOWN.value)
            except Exception as exc:
                logger.warning("write_contract register failed (non-fatal)", memory_id=record.id, error=f"{type(exc).__name__}: {exc}")
            conn.commit()

    def _fallback_save(self, layer: MemoryLayer, record: MemoryRecord) -> SaveResult:
        """Save into a non-canonical layer when Markdown failed."""

        # Mark a clone as needing canonical sync without mutating the caller's record.
        pending_record = record.model_copy(deep=True)
        pending_record.metadata["pending_canonical_sync"] = True

        try:
            result = self.backends[layer].save(pending_record)
            result.pending_canonical_sync = True
            if result.ok:
                try:
                    with self.store.connect() as conn:
                        _wc_register_memory(conn, pending_record, layer.value)
                        conn.commit()
                except Exception:
                    pass
            return result
        except Exception as exc:
            return SaveResult(
                layer=layer,
                ok=False,
                message=f"fallback save failed: {type(exc).__name__}: {exc}",
                pending_canonical_sync=True,
            )

    def flush_pending(self) -> dict[str, list[SaveResult]]:
        """Re-play pending-canonical-sync records into Markdown.

        Returns a mapping of memory_id → save results.
        Useful after recovering from a Markdown permission/path issue.
        """

        flushed: dict[str, list[SaveResult]] = {}
        seen: set[str] = set()
        pending_layers = (MemoryLayer.MEMPALACE, MemoryLayer.HONCHO, MemoryLayer.NEURAL_MEMORY)
        for layer in pending_layers:
            if layer not in self.config.enabled_layers:
                continue
            pending = self.store.get_pending_sync(layer)
            for rec in pending:
                if rec.id in seen:
                    continue
                seen.add(rec.id)
                try:
                    result = self.backends[MemoryLayer.WORKSPACE_MARKDOWN].save(rec)
                    if result.ok:
                        self._save_markdown_to_sqlite(rec)
                        for pending_layer in pending_layers:
                            self.store.clear_pending_sync(rec.id, pending_layer)
                except Exception as exc:
                    result = SaveResult(
                        layer=MemoryLayer.WORKSPACE_MARKDOWN,
                        ok=False,
                        message=f"flush failed: {type(exc).__name__}: {exc}",
                    )
                flushed.setdefault(rec.id, []).append(result)
        return flushed

    def recall(self, query: str, limit: int = 10) -> dict[MemoryLayer, list[MemoryRecord]]:
        # Expand query for better coverage
        from .depth_prior import classify_query, expected_depth, record_outcome
        from .query_expansion import expand_query

        depth = expected_depth(query, store=self.store)
        # Expand query with more variants for deeper searches
        expansion_limit = max(3, min(8, depth * 3))
        expanded_queries = expand_query(query, store=self.store)[:expansion_limit]
        out: dict[MemoryLayer, list[MemoryRecord]] = {}

        def _extra() -> dict[str, object]:
            return {
                "query_chars": len(query),
                "query_type": classify_query(query),
                "depth": depth,
                "limit": limit,
                "expanded_count": len(expanded_queries),
                "layers": [layer.value for layer in out],
                "hit_count": sum(len(records) for records in out.values()),
            }

        with traced("service.recall", extra=_extra):
            for layer in SAVE_ORDER:
                if layer not in self.config.enabled_layers:
                    continue
                try:
                    layer_records: list[MemoryRecord] = []
                    seen_hashes: set[str] = set()
                    for q in expanded_queries:
                        records = self.backends[layer].recall(q, limit=max(limit, 5))
                        for rec in records:
                            ch = rec.metadata.get("content_hash") or rec.content
                            if ch not in seen_hashes:
                                seen_hashes.add(ch)
                                layer_records.append(rec)
                    out[layer] = layer_records[:limit]
                except Exception as exc:
                    logger.warning("recall.layer_failed", layer=layer.value, error=f"{type(exc).__name__}: {exc}")
                    out[layer] = []

        # Record outcome for depth adaptation
        total_hits = sum(len(v) for v in out.values())
        try:
            record_outcome(query, hit_count=total_hits, store=self.store)
        except Exception as exc:
            logger.warning("recall.outcome_failed", error=f"{type(exc).__name__}: {exc}")

        # P1 Freshness annotation on recall results
        try:
            from .safety.freshness import evaluate_freshness
            from datetime import timezone
            for layer, records in out.items():
                for r in records:
                    if r.created_at:
                        fr = evaluate_freshness(r.created_at)
                        r.metadata["_freshness"] = {
                            "level": fr.level.value, "score": fr.score,
                            "age_days": fr.age_days, "should_verify": fr.should_verify,
                        }
        except Exception as exc:
            logger.debug("recall.freshness_annotate_failed", error=f"{type(exc).__name__}: {exc}")

        # P2 Warm cache save for future recall
        try:
            from .pipeline_integration import save_warm_cache
            act_map: dict[str, float] = {}
            for layer, records in out.items():
                for idx, r in enumerate(records):
                    rid = getattr(r, "id", None) or str(idx)
                    act_map[rid] = 1.0 - (idx * 0.05)
            save_warm_cache(self.store, act_map)
        except Exception as exc:
            logger.debug("recall.cache_save_failed", error=f"{type(exc).__name__}: {exc}")

        return out

    def search_layer(self, layer: MemoryLayer, query: str, limit: int = 10) -> list[MemoryRecord]:
        """Search a single memory layer via FTS5, returning MemoryRecord list.

        Added for P0 memory-slot contract compliance — allows compat.py to
        query individual layers directly with FTS.
        """
        try:
            backend = self.backends[layer]
            records = backend.recall(query, limit=limit)
            return list(records)
        except Exception:
            return []

    def sync_turn(self, context: TurnContext) -> list[SaveResult]:
        """Store a compact post-turn event using the canonical save order.

        OpenClaw plugins can call this after a durable Boss-facing turn.
        It intentionally stores a compact event, not raw full transcripts.

        Skips save entirely when the combined content is empty (no user or
        assistant message). This prevents creating empty openclaw.turn events.
        """

        parts = []
        if context.user_message:
            parts.append(f"user: {context.user_message}")
        if context.assistant_message:
            parts.append(f"assistant: {context.assistant_message}")
        content = "\n".join(parts).strip()
        if not content:
            logger.debug("sync_turn skipped — empty content (no user or assistant message)")
            return []
        # B1: never persist runtime-appended prompt-injection / boilerplate noise
        # into the canonical store. This is the real openclaw.turn capture path
        # (source='openclaw.turn'); the capture_hook/honcho_events path is separate.
        from .sanitize import is_injection_content
        if is_injection_content(content):
            logger.debug("sync_turn skipped — injection content dropped at canonical save")
            return []
        record = MemoryRecord(
            content=content,
            type=MemoryType.EVENT,
            scope=MemoryScope.SESSION,
            agent_id=context.agent_id,
            session_id=context.session_id,
            project=context.project,
            source="openclaw.turn",
            metadata=context.metadata or {},
            tags=["turn", "openclaw"],
        )
        return self.save(record)

    def prefetch(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        """Recall + merge across layers using RRF score fusion.

        Replaces simple sequential dedup with Reciprocal Rank Fusion (RRF)
        for better multi-layer ranking. Fall back to simple merge if layers
        don't produce rankable results.
        """
        layered = self.recall(query, limit=limit)

        # RRF: assign each record a fused score from its rank across layers
        scores: dict[str, float] = {}
        records: dict[str, MemoryRecord] = {}
        k = 60  # RRF constant

        for records_in_layer in layered.values():
            for rank, rec in enumerate(records_in_layer):
                # Dedup by content_hash (canonical) or content (fallback) — across layers
                content_hash = rec.metadata.get("content_hash") or rec.content
                if content_hash not in records:
                    records[content_hash] = rec
                # RRF score: 1 / (k + rank)
                scores[content_hash] = scores.get(content_hash, 0.0) + 1.0 / (k + rank + 1)

        if not scores:
            return []

        # Sort by RRF score descending
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        result = [records[key] for key in sorted_keys[:limit]]
        return result

    def recall_graph(self, memory_id: str, depth: int = 2, limit: int = 20) -> list[MemoryRecord]:
        """Recursive graph recall over the Neural Memory projection.

        This is intentionally deterministic: breadth-first over explicit graph_edges,
        with a hard depth/limit guard for prompt safety.
        """

        if depth < 1:
            found = self.store.get_memory(memory_id, layer=MemoryLayer.NEURAL_MEMORY.value)
            return [found] if found else []
        visited = {memory_id}
        frontier = [(memory_id, 0)]
        records: list[MemoryRecord] = []
        while frontier and len(records) < limit:
            current, current_depth = frontier.pop(0)
            rec = self.store.get_memory(current, layer=MemoryLayer.NEURAL_MEMORY.value)
            if rec:
                records.append(rec)
            if current_depth >= depth:
                continue
            for edge in self.store.graph_neighbors(current, direction="out"):
                nxt = edge["target_memory_id"]
                if nxt in visited:
                    continue
                visited.add(nxt)
                frontier.append((nxt, current_depth + 1))
        return records[:limit]
