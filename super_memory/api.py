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


def main() -> None:
    uvicorn.run("super_memory.api:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
