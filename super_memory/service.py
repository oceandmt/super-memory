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
        results: list[SaveResult] = []
        for layer in SAVE_ORDER:
            if layer not in self.config.enabled_layers:
                continue
            if self.config.require_canonical_first and layer != MemoryLayer.WORKSPACE_MARKDOWN:
                if not results or not results[0].ok:
                    results.append(SaveResult(layer=layer, ok=False, message="canonical markdown save failed/skipped"))
                    continue
            try:
                results.append(self.backends[layer].save(record))
            except Exception as exc:  # layer failure must not corrupt previous layers
                results.append(SaveResult(layer=layer, ok=False, message=f"{type(exc).__name__}: {exc}"))
        return results

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
