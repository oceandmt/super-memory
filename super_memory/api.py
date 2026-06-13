from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import bridge
from . import mcp_server

app = FastAPI(title="Super Memory API", version="0.1.0")


class RememberRequest(BaseModel):
    content: str
    type: str = "context"
    scope: str = "session"
    agent_id: str = "lucas"
    session_id: str | None = None
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    trust_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    config_path: str | None = None

class RememberBatchRequest(BaseModel):
    memories: list[RememberRequest] = Field(max_length=20)
    config_path: str | None = None

class ShowRequest(BaseModel):
    memory_id: str
    config_path: str | None = None

class ContextRequest(BaseModel):
    query: str = ""
    limit: int = 10
    config_path: str | None = None

class TodoRequest(BaseModel):
    task: str
    priority: int = 5
    config_path: str | None = None

class AutoRequest(BaseModel):
    text: str
    save: bool = False
    config_path: str | None = None

class SanitizeRequest(BaseModel):
    text: str

class NormalizeMemoryRequest(BaseModel):
    memory: dict[str, Any]
    auto_capture: bool = False


class RecallRequest(BaseModel):
    query: str
    limit: int = 10
    config_path: str | None = None


class MemorySearchRequest(BaseModel):
    query: str
    max_results: int = 5
    min_score: float = 0.0
    corpus: str = "all"
    config_path: str | None = None


class MemoryGetRequest(BaseModel):
    path: str
    from_line: int = 1
    lines: int = 20
    corpus: str = "all"
    config_path: str | None = None


class SyncTurnRequest(BaseModel):
    agent_id: str = "lucas"
    session_id: str | None = None
    user_message: str | None = None
    assistant_message: str | None = None
    project: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    config_path: str | None = None


class PromoteRequest(BaseModel):
    memory_id: str
    config_path: str | None = None

class WorkingMemoryRequest(BaseModel):
    key: str = "default"
    payload: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int | None = None
    config_path: str | None = None

class CognitivePayloadRequest(BaseModel):
    payload: dict[str, Any]
    config_path: str | None = None

class RecallArbitrateRequest(BaseModel):
    query: str
    limit: int = 10
    config_path: str | None = None

class ConsolidationCycleRequest(BaseModel):
    strategy: str = "light"
    dry_run: bool = True
    config_path: str | None = None

class ConflictResolveRequest(BaseModel):
    conflict_id: str
    resolution: str
    reason: str = ""
    config_path: str | None = None

class PromotionCandidatesRequest(BaseModel):
    limit: int = 20
    config_path: str | None = None

class FeedbackOutcomeRequest(BaseModel):
    memory_id: str | None = None
    success: bool = True
    outcome: str = ""
    config_path: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "super-memory"}


@app.get("/status")
def status(config_path: str | None = None) -> dict[str, Any]:
    return bridge.status(config_path=config_path)

@app.get("/mcp-tools")
def mcp_tools() -> dict[str, Any]:
    return {"tools": mcp_server._tool_descriptors()}

@app.get("/stats")
def stats(config_path: str | None = None) -> dict[str, Any]:
    return bridge.stats(config_path=config_path)

@app.get("/memory-health")
def memory_health(config_path: str | None = None) -> dict[str, Any]:
    return bridge.health(config_path=config_path)


@app.post("/remember")
def remember(req: RememberRequest) -> dict[str, Any]:
    payload = req.model_dump(exclude={"config_path"})
    return bridge.remember(payload, config_path=req.config_path)

@app.post("/remember-batch")
def remember_batch(req: RememberBatchRequest) -> dict[str, Any]:
    config_path = req.config_path
    memories = []
    for item in req.memories:
        payload = item.model_dump(exclude={"config_path"})
        memories.append(payload)
        config_path = config_path or item.config_path
    return bridge.remember_batch(memories, config_path=config_path)

@app.post("/show")
def show(req: ShowRequest) -> dict[str, Any]:
    return bridge.show(req.memory_id, config_path=req.config_path)

@app.post("/context")
def context(req: ContextRequest) -> dict[str, Any]:
    return bridge.context(req.query, limit=req.limit, config_path=req.config_path)

@app.post("/todo")
def todo(req: TodoRequest) -> dict[str, Any]:
    return bridge.todo(req.task, priority=req.priority, config_path=req.config_path)

@app.post("/auto")
def auto(req: AutoRequest) -> dict[str, Any]:
    return bridge.auto(req.text, save=req.save, config_path=req.config_path)

@app.post("/sanitize-prompt")
def sanitize_prompt(req: SanitizeRequest) -> dict[str, Any]:
    return {"text": bridge.sanitize_prompt(req.text)}

@app.post("/sanitize-auto-capture")
def sanitize_auto_capture(req: SanitizeRequest) -> dict[str, Any]:
    return {"text": bridge.sanitize_auto_capture(req.text)}

@app.post("/normalize-memory")
def normalize_memory(req: NormalizeMemoryRequest) -> dict[str, Any]:
    return bridge.normalize_memory_payload(req.memory, auto_capture=req.auto_capture)


@app.post("/recall")
def recall(req: RecallRequest) -> dict[str, Any]:
    return bridge.recall(req.query, limit=req.limit, config_path=req.config_path)


@app.post("/memory-search")
def memory_search(req: MemorySearchRequest) -> dict[str, Any]:
    return bridge.memory_search(
        req.query,
        max_results=req.max_results,
        min_score=req.min_score,
        corpus=req.corpus,
        config_path=req.config_path,
    )


@app.post("/memory-get")
def memory_get(req: MemoryGetRequest) -> dict[str, Any]:
    return bridge.memory_get(
        req.path,
        from_line=req.from_line,
        lines=req.lines,
        corpus=req.corpus,
        config_path=req.config_path,
    )


@app.post("/prefetch")
def prefetch(req: RecallRequest) -> dict[str, Any]:
    return bridge.prefetch(req.query, limit=req.limit, config_path=req.config_path)


@app.post("/sync-turn")
def sync_turn(req: SyncTurnRequest) -> dict[str, Any]:
    payload = req.model_dump(exclude={"config_path"})
    return bridge.sync_turn(payload, config_path=req.config_path)


@app.post("/promote")
def promote(req: PromoteRequest) -> dict[str, Any]:
    result = bridge.promote(req.memory_id, config_path=req.config_path)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "promotion failed"))
    return result

@app.post("/conflicts")
def conflicts(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.conflicts(content=req.get("content"), memory_id=req.get("memory_id"), config_path=req.get("config_path"))

@app.post("/provenance")
def provenance(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.provenance(req["memory_id"], action=req.get("action", "trace"), actor=req.get("actor", "super-memory"), config_path=req.get("config_path"))

@app.post("/source")
def source(req: dict[str, Any]) -> dict[str, Any]:
    config_path = req.pop("config_path", None)
    return bridge.source(req, config_path=config_path)

@app.post("/version")
def version(req: dict[str, Any]) -> dict[str, Any]:
    config_path = req.pop("config_path", None)
    action = req.pop("action", "create")
    name = req.pop("name", "snapshot")
    return bridge.version(action=action, name=name, config_path=config_path, **req)

@app.post("/pin")
def pin(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.pin(req["memory_id"], action=req.get("action", "pin"), config_path=req.get("config_path"))

@app.post("/consolidate")
def consolidate(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.consolidate(strategy=req.get("strategy", "all"), dry_run=req.get("dry_run", True), config_path=req.get("config_path"))

@app.post("/gaps")
def gaps(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.gaps(req["topic"], action=req.get("action", "detect"), config_path=req.get("config_path"))

@app.post("/explain")
def explain(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.explain(req["from_entity"], req["to_entity"], config_path=req.get("config_path"))

@app.get("/situation")
def situation(config_path: str | None = None) -> dict[str, Any]:
    return bridge.situation(config_path=config_path)

@app.post("/reflex")
def reflex(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.reflex(req["memory_id"], action=req.get("action", "pin"), config_path=req.get("config_path"))

@app.post("/boundaries")
def boundaries(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.boundaries(domain=req.get("domain", "global"), content=req.get("content"), config_path=req.get("config_path"))

@app.post("/optional/{action}")
def optional(action: str, req: dict[str, Any] | None = None) -> dict[str, Any]:
    return bridge.optional_heavy(action, **(req or {}))

@app.get("/working-memory")
def working_memory_get(key: str = "default", config_path: str | None = None) -> dict[str, Any]:
    return bridge.working_memory_get(key=key, config_path=config_path)

@app.post("/working-memory")
def working_memory_set(req: WorkingMemoryRequest) -> dict[str, Any]:
    return bridge.working_memory_set(req.payload, key=req.key, ttl_seconds=req.ttl_seconds, config_path=req.config_path)

@app.post("/attention-score")
def attention_score(req: CognitivePayloadRequest) -> dict[str, Any]:
    return bridge.attention_score(req.payload, config_path=req.config_path)

@app.post("/route-memory")
def route_memory(req: CognitivePayloadRequest) -> dict[str, Any]:
    return bridge.route_memory(req.payload, config_path=req.config_path)

@app.post("/parallel-save")
def parallel_save(req: CognitivePayloadRequest) -> dict[str, Any]:
    return bridge.parallel_save(req.payload, config_path=req.config_path)

@app.post("/recall-arbitrate")
def recall_arbitrate(req: RecallArbitrateRequest) -> dict[str, Any]:
    return bridge.recall_arbitrate(req.query, limit=req.limit, config_path=req.config_path)

@app.post("/consolidation-cycle")
def consolidation_cycle(req: ConsolidationCycleRequest) -> dict[str, Any]:
    return bridge.consolidation_cycle(strategy=req.strategy, dry_run=req.dry_run, config_path=req.config_path)

@app.post("/conflict-resolve")
def conflict_resolve(req: ConflictResolveRequest) -> dict[str, Any]:
    return bridge.conflict_resolve(req.conflict_id, req.resolution, reason=req.reason, config_path=req.config_path)

@app.get("/promotion-candidates")
def promotion_candidates(limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    return bridge.promotion_candidates(limit=limit, config_path=config_path)

@app.post("/promotion-candidates")
def promotion_candidates_post(req: PromotionCandidatesRequest) -> dict[str, Any]:
    return bridge.promotion_candidates(limit=req.limit, config_path=req.config_path)

@app.post("/feedback-outcome")
def feedback_outcome(req: FeedbackOutcomeRequest) -> dict[str, Any]:
    return bridge.feedback_outcome(memory_id=req.memory_id, success=req.success, outcome=req.outcome, config_path=req.config_path)


def main() -> None:
    uvicorn.run("super_memory.api:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
