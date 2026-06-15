from __future__ import annotations

from .layers import MemoryBackend, SQLiteLayerBackend, WorkspaceMarkdownBackend
from .models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType, SaveResult, SuperMemoryConfig
from .hooks import TurnContext
from .storage import SuperMemoryStore


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
        """

        results: list[SaveResult] = []
        markdown_ok = False

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
            except Exception as exc:
                result = SaveResult(layer=layer, ok=False, message=f"{type(exc).__name__}: {exc}")
                if layer == MemoryLayer.WORKSPACE_MARKDOWN:
                    markdown_ok = False
                elif not markdown_ok and self.config.require_canonical_first:
                    result.pending_canonical_sync = True
                results.append(result)

        return results

    def _fallback_save(self, layer: MemoryLayer, record: MemoryRecord) -> SaveResult:
        """Save into a non-canonical layer when Markdown failed."""

        # Mark record as needing canonical sync
        record.metadata["pending_canonical_sync"] = True

        try:
            result = self.backends[layer].save(record)
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
        for layer in (MemoryLayer.MEMPALACE, MemoryLayer.HONCHO, MemoryLayer.NEURAL_MEMORY):
            if layer not in self.config.enabled_layers:
                continue
            pending = self.store.get_pending_sync(layer)
            for rec in pending:
                try:
                    result = self.backends[MemoryLayer.WORKSPACE_MARKDOWN].save(rec)
                    if result.ok:
                        self.store.clear_pending_sync(rec.id, layer)
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
        """

        parts = []
        if context.user_message:
            parts.append(f"user: {context.user_message}")
        if context.assistant_message:
            parts.append(f"assistant: {context.assistant_message}")
        content = "\n".join(parts).strip()
        record = MemoryRecord(
            content=content,
            type=MemoryType.EVENT,
            scope=MemoryScope.SESSION,
            agent_id=context.agent_id,
            session_id=context.session_id,
            project=context.project,
            source="openclaw.turn",
            metadata=context.metadata,
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
