from __future__ import annotations

from typing import Any

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .agent import Agent
from .approval_flow import ApprovalFlow
from .runtime import Runtime
from .trace import TraceRepo
from .widget import WIDGET_HTML


class ChatBody(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
    customer_id: str | None = Field(default=None, alias="customerId", max_length=200)
    model_config = {"populate_by_name": True}


class DecisionBody(BaseModel):
    approved: bool
    by: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=1000)


class ResolveBody(BaseModel):
    by: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=1000)


class ExpireBody(BaseModel):
    older_than_seconds: float = Field(alias="olderThanSeconds", ge=0)
    model_config = {"populate_by_name": True}


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(runtime: Runtime, traces: TraceRepo, agents: dict[str, Agent], api_key: str | None = None,
               approval_ttl_seconds: float | None = None) -> FastAPI:
    flow = ApprovalFlow(runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if approval_ttl_seconds:  # periodically expire stale approvals and hand those conversations to a person
            async def sweep() -> None:
                while True:
                    await asyncio.sleep(max(1.0, min(60.0, approval_ttl_seconds / 2)))
                    try:
                        await flow.expire_stale(agents, approval_ttl_seconds)
                    except Exception:  # keep sweeping; a failed pass is retried on the next tick
                        pass

            task = asyncio.create_task(sweep())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="NorthCX", lifespan=lifespan)

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
        return {"reply": r.reply, "status": r.status, "traceId": r.trace_id, "pendingApprovals": r.pending_approvals,
                "handoffId": r.handoff_id}

    @app.get("/v1/traces/{trace_id}")
    async def get_trace(trace_id: str) -> Any:
        t = await traces.get(trace_id)
        return t.to_dict() if t else _err(404, "not_found", "Unknown trace")

    @app.get("/v1/traces")
    async def list_traces(sessionId: str | None = None, limit: int = 200) -> Any:
        items = await traces.summaries(sessionId, max(1, min(limit, 1000)))
        return {"traces": [{"id": t.id, "agentId": t.agent_id, "sessionId": t.session_id, "events": t.events,
                            "status": t.status, "startedAt": t.started_at, "tools": t.tools} for t in items]}

    @app.get("/v1/agents")
    async def list_agents() -> Any:
        return {"agents": [{"id": a.id, "instructions": a.instructions, "model": a.model, "maxSteps": a.max_steps,
                            "tools": [{"name": t.name, "description": t.description, "approval": t.requires_approval is not None}
                                      for t in a.tools],
                            "guardrails": [g.name for g in a.guardrails],
                            "inputGuardrails": [g.name for g in a.input_guardrails],
                            "forcedTopics": [t.name for t in a.forced_handoffs]} for a in agents.values()]}

    @app.get("/v1/approvals")
    async def list_approvals(state: str | None = None) -> Any:
        return {"approvals": [a.__dict__ for a in await runtime.approvals.list(state)]}

    @app.post("/v1/approvals/{approval_id}/decision")
    async def decide(approval_id: str, body: DecisionBody) -> Any:
        """Record the decision, run the action if approved, and continue the conversation. The customer receives the
        outcome through the outbox (and the webhook, if configured)."""
        try:
            res = await flow.resolve(agents, approval_id, body.approved, body.by, body.note)
        except KeyError:
            return _err(404, "not_found", "Unknown approval")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        out = dict(res.approval.__dict__)
        out["resume"] = ({"reply": res.run.reply, "status": res.run.status, "traceId": res.run.trace_id}
                         if res.run else {"error": res.error})
        if res.run and res.error:
            out["resume"]["error"] = res.error
        return out

    @app.post("/v1/approvals/expire")
    async def expire(body: ExpireBody) -> Any:
        done = await flow.expire_stale(agents, body.older_than_seconds)
        return {"expired": [a.id for a in done]}

    def handoff_json(h: Any, full: bool = False) -> dict[str, Any]:
        out = {"id": h.id, "sessionId": h.session_id, "traceId": h.trace_id, "agentId": h.agent_id, "customerId": h.customer_id,
               "trigger": h.trigger, "reason": h.reason, "topics": h.topics, "state": h.state, "createdAt": h.created_at,
               "resolvedBy": h.resolved_by, "resolvedAt": h.resolved_at, "note": h.note, "summary": h.package.get("summary")}
        if full:
            out["package"] = h.package
        return out

    @app.get("/v1/handoffs")
    async def list_handoffs(state: str | None = None, sessionId: str | None = None, limit: int = 200) -> Any:
        items = await runtime.handoffs.list(state, sessionId, max(1, min(limit, 1000)))
        return {"handoffs": [handoff_json(h) for h in items]}

    @app.get("/v1/handoffs/{handoff_id}")
    async def get_handoff(handoff_id: str) -> Any:
        h = await runtime.handoffs.get(handoff_id)
        return handoff_json(h, full=True) if h else _err(404, "not_found", "Unknown handoff")

    @app.post("/v1/handoffs/{handoff_id}/resolve")
    async def resolve_handoff(handoff_id: str, body: ResolveBody) -> Any:
        try:
            return handoff_json(await runtime.handoffs.resolve(handoff_id, body.by, body.note))
        except KeyError:
            return _err(404, "not_found", "Unknown handoff")
        except ValueError as e:
            return _err(409, "conflict", str(e))

    @app.get("/v1/sessions/{session_id}/outbox")
    async def outbox(session_id: str, after: int = 0) -> Any:
        items = await runtime.outbox.list(session_id, after)
        return {"messages": [{"id": m.id, "kind": m.kind, "createdAt": m.created_at, **m.payload} for m in items]}

    return app
