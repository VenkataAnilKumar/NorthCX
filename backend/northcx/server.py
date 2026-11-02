from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .agent import Agent
from .runtime import Runtime
from .trace import TraceStore
from .widget import WIDGET_HTML


class ChatBody(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
    customer_id: str | None = Field(default=None, alias="customerId", max_length=200)
    model_config = {"populate_by_name": True}


class DecisionBody(BaseModel):
    approved: bool
    by: str = Field(min_length=1)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(runtime: Runtime, traces: TraceStore, agents: dict[str, Agent], api_key: str | None = None) -> FastAPI:
    app = FastAPI(title="NorthCX")

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if api_key and request.url.path.startswith("/v1/") and request.headers.get("authorization") != f"Bearer {api_key}":
            return _err(401, "unauthorized", "Missing or invalid API key")
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return _err(400, "bad_request", str(exc.errors()))

    @app.get("/", response_class=HTMLResponse)
    async def widget() -> str:
        return WIDGET_HTML

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/agents/{agent_id}/chat")
    async def chat(agent_id: str, body: ChatBody) -> Any:
        agent = agents.get(agent_id)
        if agent is None:
            return _err(404, "not_found", "Unknown agent")
        try:
            r = await runtime.run(agent, body.session_id, body.message, body.customer_id)
        except Exception:
            return _err(500, "internal", "Run failed")
        return {"reply": r.reply, "status": r.status, "traceId": r.trace_id, "pendingApprovals": r.pending_approvals}

    @app.get("/v1/traces/{trace_id}")
    async def get_trace(trace_id: str) -> Any:
        t = traces.get(trace_id)
        return t.to_dict() if t else _err(404, "not_found", "Unknown trace")

    @app.get("/v1/traces")
    async def list_traces(sessionId: str | None = None) -> Any:
        return {"traces": [{"id": t.id, "agentId": t.agent_id, "sessionId": t.session_id, "events": len(t.events)}
                           for t in traces.list(sessionId)]}

    @app.get("/v1/approvals")
    async def list_approvals(state: str | None = None) -> Any:
        return {"approvals": [a.__dict__ for a in runtime.approvals.list(state)]}

    # Records the decision only. Resuming the run is a Phase 2 feature.
    @app.post("/v1/approvals/{approval_id}/decision")
    async def decide(approval_id: str, body: DecisionBody) -> Any:
        try:
            return runtime.approvals.decide(approval_id, body.approved, body.by).__dict__
        except KeyError:
            return _err(404, "not_found", "Unknown approval")
        except ValueError as e:
            return _err(409, "conflict", str(e))

    return app
