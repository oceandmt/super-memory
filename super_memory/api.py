from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import bridge

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


class RecallRequest(BaseModel):
    query: str
    limit: int = 10
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


@app.post("/remember")
def remember(req: RememberRequest) -> dict[str, Any]:
    payload = req.model_dump(exclude={"config_path"})
    return bridge.remember(payload, config_path=req.config_path)


@app.post("/recall")
def recall(req: RecallRequest) -> dict[str, Any]:
    return bridge.recall(req.query, limit=req.limit, config_path=req.config_path)


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


def main() -> None:
    uvicorn.run("super_memory.api:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
