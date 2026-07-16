from __future__ import annotations

import threading
import time
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import structlog

from . import __version__, bridge, mcp_server
from .config import load_config
from .observability import metrics as _metrics_snapshot, prometheus_metrics as _prometheus_metrics

_logger = structlog.get_logger("super-memory.api")

app = FastAPI(title="Super Memory API", version=__version__)

# ── In-memory rate limiter ──────────────────────────────────────────────────
_RATE_LIMIT_WINDOW_S = 60
_RATE_LIMIT_MAX = 200
_rate_buckets: dict[str, list[float]] = {}
_rate_lock = threading.Lock()

_rate_exempt_ips = {"127.0.0.1", "::1", "localhost"}

def _rate_limit_ip(client_ip: str) -> tuple[bool, int]:
    """Returns (allowed, remaining)."""
    if client_ip in _rate_exempt_ips:
        return True, _RATE_LIMIT_MAX
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW_S
    with _rate_lock:
        if client_ip not in _rate_buckets:
            _rate_buckets[client_ip] = []
        # Prune expired timestamps
        _rate_buckets[client_ip] = [t for t in _rate_buckets[client_ip] if t > window_start]
        used = len(_rate_buckets[client_ip])
        remaining = _RATE_LIMIT_MAX - used
        if remaining <= 0:
            return False, 0
        _rate_buckets[client_ip].append(now)
    return True, remaining - 1

# ── Bearer token auth ────────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)

def _get_auth_dependency():

    def verify_token(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
        cfg = load_config(None)
        if not cfg.api_token:
            return  # No token configured → open access (backward compat)
        if credentials is None or credentials.credentials != cfg.api_token:
            raise HTTPException(status_code=401, detail="Unauthorized — invalid or missing Bearer token")

    return verify_token

_auth = _get_auth_dependency()  # callable dependency


# ── Middleware for rate limiting and auth ────────────────────────────────────
_HEALTH_PATHS = {"/health", "/mcp-tools"}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # ── Rate limiting ───────────────────────────────────────────────────────
    client_ip = request.client.host if request.client else "unknown"
    allowed, remaining = _rate_limit_ip(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
            headers={"X-RateLimit-Remaining": "0"},
        )

    # ── Bearer token auth (skips health endpoints) ──────────────────────────
    if request.url.path not in _HEALTH_PATHS:
        cfg = load_config(None)
        if cfg.api_token:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer ") or auth_header[7:] != cfg.api_token:
                _logger.warning("auth.failed", ip=client_ip, path=request.url.path, method=request.method)
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized — invalid or missing Bearer token"},
                    headers={"X-RateLimit-Remaining": str(remaining)},
                )

    response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response




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

class CallerContextRequest(BaseModel):
    agent_id: str | None = None
    session_id: str | None = None
    project: str | None = None
    scope: str | None = None

    def caller_context(self) -> dict[str, str]:
        return {
            key: value
            for key in ("agent_id", "session_id", "project", "scope")
            if (value := getattr(self, key)) is not None
        }

class ShowRequest(CallerContextRequest):
    memory_id: str | None = None
    id: str | None = None
    config_path: str | None = None

class ContextRequest(CallerContextRequest):
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


class RecallRequest(CallerContextRequest):
    query: str
    limit: int = 10
    config_path: str | None = None


class RecallRecordEventRequest(BaseModel):
    query: str
    selected_memory_ids: list[str] = Field(default_factory=list)
    shown_to_user: bool = True
    source: str = "plugin_auto"
    config_path: str | None = None

class RecallRecordFeedbackRequest(BaseModel):
    recall_event_id: str
    memory_id: str
    outcome: str
    confidence: float = 1.0
    notes: str = ""
    config_path: str | None = None

class MemorySearchRequest(CallerContextRequest):
    query: str
    max_results: int = 5
    min_score: float = 0.0
    corpus: str = "all"
    config_path: str | None = None


class MemoryGetRequest(CallerContextRequest):
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


class DurablePackRequest(BaseModel):
    pack_name: str = "openclaw-super-memory-durable-pack-v1"
    project: str = "super-memory"
    agents: list[str] = Field(default_factory=lambda: ["lucas", "alex", "max", "isol"])
    qualify: bool = True
    debug: bool = True
    dedupe: bool = True
    config_path: str | None = None

class DurablePackAuditRequest(BaseModel):
    pack_name: str = "openclaw-super-memory-durable-pack-v1"
    project: str = "super-memory"
    fix: bool = False
    config_path: str | None = None

class PromoteRequest(BaseModel):
    memory_id: str
    config_path: str | None = None

class ForgetRequest(BaseModel):
    memory_id: str
    hard: bool = False
    reason: str = ""
    config_path: str | None = None

class EditRequest(BaseModel):
    memory_id: str
    content: str | None = None
    type: str | None = None
    priority: int | None = None
    tier: str | None = None
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

class GraphNeighborsRequest(BaseModel):
    id: str
    direction: str = "out"
    limit: int = 20
    config_path: str | None = None

class GraphRecallRequest(BaseModel):
    query: str
    limit: int = 10
    config_path: str | None = None

class SpreadingActivationRecallRequest(BaseModel):
    query: str
    depth: int = 2
    top_k: int = 20
    seed_limit: int = 30
    config_path: str | None = None

class HypothesisCreateRequest(BaseModel):
    content: str
    confidence: float = 0.5
    tags: list[str] = Field(default_factory=list)
    config_path: str | None = None

class EvidenceAddRequest(BaseModel):
    hypothesis_id: str
    content: str
    direction: str = "for"
    weight: float = 0.5
    source_id: str | None = None
    source_type: str | None = None
    source_hash: str | None = None
    source_revision: str | None = None
    source_trust: float | None = None
    config_path: str | None = None

class PredictionCreateRequest(BaseModel):
    content: str
    confidence: float = 0.7
    hypothesis_id: str | None = None
    deadline: str | None = None
    config_path: str | None = None

class VerifyPredictionRequest(BaseModel):
    prediction_id: str
    outcome: str
    content: str = ""
    config_path: str | None = None

class LifecycleRequest(BaseModel):
    action: str = "status"
    dry_run: bool = True
    limit: int = 500
    config_path: str | None = None


class LeitnerRequest(BaseModel):
    action: str = "queue"
    memory_id: str | None = None
    success: bool = True
    box: int = 0
    limit: int = 50
    config_path: str | None = None

class Phase8Request(BaseModel):
    config_path: str | None = None

class McpContractRequest(BaseModel):
    profile: str = "admin"
    config_path: str | None = None

class LocalFlowRequest(BaseModel):
    path: str
    domain_tag: str = "local"
    source_name: str = "local-import"
    recursive: bool = True
    limit: int = 200
    save: bool = True
    config_path: str | None = None

class IndexRequest(BaseModel):
    path: str
    extensions: list[str] | None = None
    recursive: bool = True
    limit: int = 500
    save: bool = True
    config_path: str | None = None


@app.get("/health")
def health(config_path: str | None = None) -> dict[str, Any]:
    """Liveness-compatible, read-only readiness evidence."""
    return bridge.health(config_path=config_path)


@app.get("/status")
def status(config_path: str | None = None) -> dict[str, Any]:
    return bridge.status(config_path=config_path)

@app.get("/mcp-tools")
def mcp_tools() -> dict[str, Any]:
    return {"tools": mcp_server._tool_descriptors()}

@app.get("/stats")
def stats(config_path: str | None = None) -> dict[str, Any]:
    return bridge.stats(config_path=config_path)

@app.get("/metrics")
def metrics() -> dict[str, Any]:
    m = _metrics_snapshot()
    stats_snapshot = bridge.status()
    return {**m, "service": stats_snapshot}

@app.get("/metrics/prometheus", response_class=PlainTextResponse)
def metrics_prometheus() -> str:
    return _prometheus_metrics()


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
    memory_id = req.memory_id or req.id
    if not memory_id:
        raise HTTPException(status_code=422, detail="memory_id or id is required")
    return bridge.show(memory_id, config_path=req.config_path, **req.caller_context())

@app.post("/context")
def context(req: ContextRequest) -> dict[str, Any]:
    return bridge.context(
        req.query, limit=req.limit, config_path=req.config_path,
        **req.caller_context(),
    )

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
    return bridge.recall(
        req.query, limit=req.limit, config_path=req.config_path,
        **req.caller_context(),
    )


@app.post("/recall-record-event")
def recall_record_event(req: RecallRecordEventRequest) -> dict[str, Any]:
    return bridge.recall_record_event(
        req.query,
        req.selected_memory_ids,
        shown_to_user=req.shown_to_user,
        source=req.source,
        config_path=req.config_path,
    )

@app.post("/recall-record-feedback")
def recall_record_feedback(req: RecallRecordFeedbackRequest) -> dict[str, Any]:
    return bridge.recall_record_feedback(
        req.recall_event_id,
        req.memory_id,
        req.outcome,
        confidence=req.confidence,
        notes=req.notes,
        config_path=req.config_path,
    )

@app.post("/memory-search")
def memory_search(req: MemorySearchRequest) -> dict[str, Any]:
    return bridge.memory_search(
        req.query,
        max_results=req.max_results,
        min_score=req.min_score,
        corpus=req.corpus,
        config_path=req.config_path,
        **req.caller_context(),
    )


@app.post("/memory-get")
def memory_get(req: MemoryGetRequest) -> dict[str, Any]:
    return bridge.memory_get(
        req.path,
        from_line=req.from_line,
        lines=req.lines,
        corpus=req.corpus,
        config_path=req.config_path,
        **req.caller_context(),
    )


@app.post("/prefetch")
def prefetch(req: RecallRequest) -> dict[str, Any]:
    return bridge.prefetch(
        req.query, limit=req.limit, config_path=req.config_path,
        **req.caller_context(),
    )


@app.post("/sync-turn")
def sync_turn(req: SyncTurnRequest) -> dict[str, Any]:
    payload = req.model_dump(exclude={"config_path"})
    return bridge.sync_turn(payload, config_path=req.config_path)


@app.post("/durable-pack")
def durable_pack(req: DurablePackRequest) -> dict[str, Any]:
    return bridge.durable_pack(
        pack_name=req.pack_name,
        project=req.project,
        agents=req.agents,
        qualify=req.qualify,
        debug=req.debug,
        dedupe=req.dedupe,
        config_path=req.config_path,
    )

@app.post("/durable-pack/status")
def durable_pack_status(req: DurablePackAuditRequest) -> dict[str, Any]:
    return bridge.durable_pack_status(
        pack_name=req.pack_name,
        project=req.project,
        config_path=req.config_path,
    )

@app.post("/durable-pack/audit")
def durable_pack_audit(req: DurablePackAuditRequest) -> dict[str, Any]:
    return bridge.durable_pack_audit(
        pack_name=req.pack_name,
        project=req.project,
        fix=req.fix,
        config_path=req.config_path,
    )

@app.post("/promote")
def promote(req: dict[str, Any]) -> dict[str, Any]:
    memory_id = req.get("memory_id") or req.get("id")
    if not memory_id:
        raise HTTPException(status_code=422, detail="memory_id or id is required")
    result = bridge.promote(memory_id, config_path=req.get("config_path"))
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "promotion failed"))
    return result

@app.post("/forget")
def forget(req: ForgetRequest) -> dict[str, Any]:
    result = bridge.forget(req.memory_id, hard=req.hard, reason=req.reason, config_path=req.config_path)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "forget failed"))
    return result

@app.post("/edit")
def edit(req: EditRequest) -> dict[str, Any]:
    result = bridge.edit(
        req.memory_id,
        content=req.content,
        type=req.type,
        priority=req.priority,
        tier=req.tier,
        config_path=req.config_path,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "edit failed"))
    return result

@app.post("/conflicts")
def conflicts(req: dict[str, Any]) -> dict[str, Any]:
    return bridge.conflicts(content=req.get("content"), memory_id=req.get("memory_id"), config_path=req.get("config_path"))

@app.post("/provenance")
def provenance(req: dict[str, Any]) -> dict[str, Any]:
    memory_id = req.get("memory_id") or req.get("id")
    if not memory_id:
        raise HTTPException(status_code=422, detail="memory_id is required")
    return bridge.provenance(memory_id, action=req.get("action", "trace"), actor=req.get("actor", "super-memory"), config_path=req.get("config_path"))

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
    memory_id = req.get("memory_id") or req.get("id")
    if not memory_id:
        raise HTTPException(status_code=422, detail="memory_id is required")
    return bridge.pin(memory_id, action=req.get("action", "pin"), config_path=req.get("config_path"))

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

@app.post("/situation")
def situation_post(req: dict[str, Any] | None = None) -> dict[str, Any]:
    return bridge.situation(config_path=(req or {}).get("config_path"))

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

@app.post("/semantic/doctor")
def api_semantic_doctor(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    return bridge.semantic_doctor(config_path=req.get("config_path"), query=req.get("query", "semantic recall smoke test"))

@app.post("/semantic/index")
def api_semantic_index(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    return bridge.semantic_index(config_path=req.get("config_path"), rebuild=req.get("rebuild", False), batch_size=req.get("batch_size", 8), limit=req.get("limit"))

@app.post("/semantic/verify")
def api_semantic_verify(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    return bridge.semantic_verify(config_path=req.get("config_path"), query=req.get("query", "semantic recall smoke test"), limit=req.get("limit", 5))

@app.post("/maintenance/run")
def api_maintenance_run(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    return bridge.maintenance_run(dry_run=req.get("dry_run", True), limit=req.get("limit", 500), config_path=req.get("config_path"))

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


@app.get("/graph/stats")
def graph_stats(config_path: str | None = None) -> dict[str, Any]:
    return bridge.graph_stats(config_path=config_path)

@app.post("/graph/neighbors")
def graph_neighbors(req: GraphNeighborsRequest) -> dict[str, Any]:
    return bridge.graph_neighbors(req.id, direction=req.direction, limit=req.limit, config_path=req.config_path)

@app.post("/graph/recall")
def graph_recall(req: GraphRecallRequest) -> dict[str, Any]:
    return bridge.graph_recall(req.query, limit=req.limit, config_path=req.config_path)

@app.post("/graph/spreading-recall")
def spreading_activation_recall(req: SpreadingActivationRecallRequest) -> dict[str, Any]:
    return bridge.spreading_activation_recall(req.query, depth=req.depth, top_k=req.top_k, seed_limit=req.seed_limit, config_path=req.config_path)

@app.post("/nmem/recall")
def nmem_recall(req: SpreadingActivationRecallRequest) -> dict[str, Any]:
    result = bridge.spreading_activation_recall(req.query, depth=req.depth, top_k=req.top_k, seed_limit=req.seed_limit, config_path=req.config_path)
    return {
        "answer": result.get("results", []),
        "confidence": 1.0 if result.get("results") else 0.0,
        "neurons_activated": result.get("total_activated", 0),
        "depth_used": result.get("depth", req.depth),
        "elapsed_ms": result.get("elapsed_ms", 0),
        "raw": result,
    }

@app.post("/graph/rebuild")
def graph_rebuild(req: PromotionCandidatesRequest) -> dict[str, Any]:
    return bridge.graph_rebuild(limit=req.limit, config_path=req.config_path)

@app.post("/hypothesis")
def hypothesis_create(req: HypothesisCreateRequest) -> dict[str, Any]:
    return bridge.hypothesis_create(req.content, confidence=req.confidence, tags=req.tags, config_path=req.config_path)

@app.get("/hypothesis/{hypothesis_id}")
def hypothesis_get(hypothesis_id: str, config_path: str | None = None) -> dict[str, Any]:
    return bridge.hypothesis_get(hypothesis_id, config_path=config_path)

@app.get("/hypotheses")
def hypothesis_list(status: str | None = None, limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    return bridge.hypothesis_list(status=status, limit=limit, config_path=config_path)

@app.post("/evidence")
def evidence_add(req: EvidenceAddRequest) -> dict[str, Any]:
    return bridge.evidence_add(req.hypothesis_id, req.content, direction=req.direction, weight=req.weight, config_path=req.config_path, source_id=req.source_id, source_type=req.source_type, source_hash=req.source_hash, source_revision=req.source_revision, source_trust=req.source_trust)

@app.post("/prediction")
def prediction_create(req: PredictionCreateRequest) -> dict[str, Any]:
    return bridge.prediction_create(req.content, confidence=req.confidence, hypothesis_id=req.hypothesis_id, deadline=req.deadline, config_path=req.config_path)

@app.get("/predictions")
def prediction_list(status: str | None = None, limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    return bridge.prediction_list(status=status, limit=limit, config_path=config_path)

@app.post("/verify-prediction")
def verify_prediction(req: VerifyPredictionRequest) -> dict[str, Any]:
    return bridge.verify_prediction(req.prediction_id, req.outcome, content=req.content, config_path=req.config_path)

@app.post("/lifecycle/review")
def lifecycle_review(req: LifecycleRequest) -> dict[str, Any]:
    return bridge.lifecycle_review(limit=req.limit, config_path=req.config_path)

@app.post("/lifecycle/cache")
def lifecycle_cache(req: LifecycleRequest) -> dict[str, Any]:
    return bridge.lifecycle_cache(action=req.action, config_path=req.config_path)

@app.post("/lifecycle/tier")
def lifecycle_tier(req: LifecycleRequest) -> dict[str, Any]:
    return bridge.lifecycle_tier(action=req.action, dry_run=req.dry_run, limit=req.limit, config_path=req.config_path)

@app.post("/lifecycle/compression")
def lifecycle_compression(req: LifecycleRequest) -> dict[str, Any]:
    return bridge.lifecycle_compression(action=req.action, dry_run=req.dry_run, limit=req.limit, config_path=req.config_path)

@app.get("/reflex/status")
def reflex_status(config_path: str | None = None) -> dict[str, Any]:
    return bridge.reflex_status(config_path=config_path)

@app.post("/leitner")
def leitner(req: LeitnerRequest) -> dict[str, Any]:
    """Leitner 5-box: queue|mark|schedule|stats|auto_seed"""
    if req.action == "queue":
        return bridge.leitner_queue(limit=req.limit, config_path=req.config_path)
    elif req.action == "mark":
        if not req.memory_id:
            raise HTTPException(status_code=422, detail="memory_id required for mark")
        return bridge.leitner_mark(req.memory_id, success=req.success, config_path=req.config_path)
    elif req.action == "schedule":
        if not req.memory_id:
            raise HTTPException(status_code=422, detail="memory_id required for schedule")
        return bridge.leitner_schedule(req.memory_id, box=req.box, config_path=req.config_path)
    elif req.action == "stats":
        return bridge.leitner_stats(config_path=req.config_path)
    elif req.action == "auto_seed":
        return bridge.leitner_auto_seed(limit=req.limit, config_path=req.config_path)
    else:
        raise HTTPException(status_code=422, detail=f"unknown leitner action: {req.action}")

@app.post("/train-local")
def train_local(req: LocalFlowRequest) -> dict[str, Any]:
    return bridge.train_local(req.path, domain_tag=req.domain_tag, recursive=req.recursive, limit=req.limit, save=req.save, config_path=req.config_path)

@app.post("/index-local")
def index_local(req: IndexRequest) -> dict[str, Any]:
    return bridge.index_local(req.path, extensions=req.extensions, recursive=req.recursive, limit=req.limit, save=req.save, config_path=req.config_path)

@app.get("/index-status")
def index_status(config_path: str | None = None) -> dict[str, Any]:
    return bridge.index_status(config_path=config_path)

@app.post("/import-local")
def import_local(req: LocalFlowRequest) -> dict[str, Any]:
    return bridge.import_local(req.path, source_name=req.source_name, recursive=req.recursive, limit=req.limit, save=req.save, config_path=req.config_path)

@app.post("/watch-scan")
def watch_scan(req: LocalFlowRequest) -> dict[str, Any]:
    return bridge.watch_scan(req.path, recursive=req.recursive, limit=req.limit, save=req.save, config_path=req.config_path)

@app.get("/sync-status")
def sync_status(config_path: str | None = None) -> dict[str, Any]:
    return bridge.sync_status(config_path=config_path)

@app.get("/store-status")
def store_status(config_path: str | None = None) -> dict[str, Any]:
    return bridge.store_status(config_path=config_path)

def get_db() -> str:
    """Return the configured database backend name."""
    cfg = load_config(None)
    return cfg.db_backend


def main() -> None:
    uvicorn.run("super_memory.api:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()


@app.get("/cross-layer-health")
@app.post("/cross-layer-health")
def cross_layer_health(config_path: str | None = None) -> dict[str, Any]:
    return bridge.cross_layer_health(config_path=config_path)

@app.post("/diagnostics")
def diagnostics(req: Phase8Request) -> dict[str, Any]:
    return bridge.diagnostics(config_path=req.config_path)

@app.post("/memory-slot-contract")
def memory_slot_contract(req: Phase8Request) -> dict[str, Any]:
    return bridge.memory_slot_contract(config_path=req.config_path)

@app.post("/mcp-contract")
def mcp_contract(req: McpContractRequest) -> dict[str, Any]:
    return bridge.mcp_contract(profile=req.profile, config_path=req.config_path)

@app.post("/supervised-runtime-smoke")
def supervised_runtime_smoke(req: Phase8Request) -> dict[str, Any]:
    return bridge.supervised_runtime_smoke(config_path=req.config_path)
