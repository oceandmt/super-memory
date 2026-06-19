from __future__ import annotations

import importlib.util as _importlib_util

from .hooks import TurnContext
from .layers import MemoryBackend, SQLiteLayerBackend, WorkspaceMarkdownBackend
from .models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType, SaveResult, SuperMemoryConfig
from .observability import traced
from .storage import SuperMemoryStore

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
            conn.commit()

    def _fallback_save(self, layer: MemoryLayer, record: MemoryRecord) -> SaveResult:
        """Save into a non-canonical layer when Markdown failed."""

        # Mark a clone as needing canonical sync without mutating the caller's record.
        pending_record = record.model_copy(deep=True)
        pending_record.metadata["pending_canonical_sync"] = True

        try:
            result = self.backends[layer].save(pending_record)
            result.pending_canonical_sync = True
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
        out: dict[MemoryLayer, list[MemoryRecord]] = {}

        def _extra() -> dict[str, object]:
            return {
                "query_chars": len(query),
                "limit": limit,
                "layers": [layer.value for layer in out],
                "hit_count": sum(len(records) for records in out.values()),
            }

        with traced("service.recall", extra=_extra):
            for layer in SAVE_ORDER:
                if layer not in self.config.enabled_layers:
                    continue
                try:
                    out[layer] = self.backends[layer].recall(query, limit=limit)
                except Exception:
                    out[layer] = []
        return out

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
        layered = self.recall(query, limit=limit)
        merged: list[MemoryRecord] = []
        seen: set[str] = set()
        for layer in SAVE_ORDER:
            for record in layered.get(layer, []):
                key = f"{record.id}:{record.content}"
                if key in seen:
                    continue
                seen.add(key)
                merged.append(record)
                if len(merged) >= limit:
                    return merged
        return merged

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
