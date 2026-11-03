from __future__ import annotations

from typing import Any

import asyncio
import json
import logging
import re
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .access import ROLES, AccessControl, Identity, LimitConfig, OPEN_IDENTITY
from .channels.email import EmailChannel, EmailParseError
from .tokens import DEFAULT_TTL, MAX_TTL, MIN_TTL, TokenSigner, derive_secret
from .approval_flow import ApprovalFlow
from .channels.sms import SmsChannel, parse_form
from .privacy import InMemoryPrivacy, PrivacyService, customer_ref
from .knowledge import InMemoryKnowledge, KnowledgeError, KnowledgeStore, Source
from .idempotency import IdempotencyStore, InMemoryIdempotency, scope_hash, request_hash, valid_key
from .audit import AuditEntry, AuditRepo, InMemoryAudit
from .catalog import AgentUnavailable, as_provider
from .runtime import Runtime
from .simulation import Busy, SimulationService
from .spec import AgentSpec, SpecError, parse_spec
from .versions import Conflict, GateBlocked, InvalidSpec, NotFound, ReleaseService, diff_specs, spec_yaml
from .trace import TraceRepo
from .widget import WIDGET_HTML


class ChatBody(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
    customer_id: str | None = Field(default=None, alias="customerId", max_length=200)
    channel: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{1,19}$")
    model_config = {"populate_by_name": True}


class SourceBody(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    stale_after_days: int | None = Field(default=None, alias="staleAfterDays")
    model_config = {"populate_by_name": True}


class DocumentBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=500_000)
    url: str | None = Field(default=None, max_length=2000)
    source_updated_at: float | None = Field(default=None, alias="sourceUpdatedAt")
    model_config = {"populate_by_name": True}


class RetentionBody(BaseModel):
    older_than_days: float = Field(alias="olderThanDays", ge=1, le=3650)
    model_config = {"populate_by_name": True}


class DecisionBody(BaseModel):
    approved: bool
    by: str | None = Field(default=None, max_length=200)  # only used when the server has no authentication configured
    note: str | None = Field(default=None, max_length=1000)


class ResolveBody(BaseModel):
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class SimRunBody(BaseModel):
    mode: str = "scripted"
    only: str | None = Field(default=None, max_length=100)
    skip_judge: bool = Field(default=False, alias="skipJudge")
    agent: str | None = None
    version: int | None = Field(default=None, ge=1)  # run against this saved version of `agent`
    model_config = {"populate_by_name": True}


class VersionBody(BaseModel):
    spec: dict[str, Any] | None = None
    spec_yaml: str | None = Field(default=None, alias="specYaml", max_length=100_000)
    from_baseline: bool = Field(default=False, alias="fromBaseline")
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class PublishBody(BaseModel):
    version: int = Field(ge=1)
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class RollbackBody(BaseModel):
    to_version: int | None = Field(default=None, alias="toVersion", ge=1)
    by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class TokenBody(BaseModel):
    session_id: str | None = Field(default=None, alias="sessionId", pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    customer_id: str | None = Field(default=None, alias="customerId", max_length=200)
    agent: str | None = Field(default=None, max_length=200)
    ttl_seconds: float = Field(default=DEFAULT_TTL, alias="ttlSeconds")
    model_config = {"populate_by_name": True}


class KeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str
    expires_in_days: float | None = Field(default=None, alias="expiresInDays")
    model_config = {"populate_by_name": True}


class ExpireBody(BaseModel):
    older_than_seconds: float = Field(alias="olderThanSeconds", ge=0)
    model_config = {"populate_by_name": True}


def _pieces(reply: str, size: int = 40) -> list[str]:
    """Split a reply at word boundaries into pieces of about `size` characters; joining them gives the reply back exactly."""
    out, cur = [], ""
    for part in re.findall(r"\S+\s*|\s+", reply):
        if cur and len(cur) + len(part) > size:
            out.append(cur)
            cur = ""
        cur += part
    return out + ([cur] if cur else [])


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


# Every /v1 route must appear here. A route that is not listed is refused (a test checks the table against the app).
ROUTE_PERMISSIONS: list[tuple[str, str, str]] = [
    ("GET", r"/v1/me", "authenticated"),
    ("POST", r"/v1/chat-tokens", "chat:mint"),
    ("POST", r"/v1/channels/email/inbound", "channel:inbound"),
    ("POST", r"/v1/agents/[^/]+/chat", "chat:send"),
    ("POST", r"/v1/agents/[^/]+/chat/stream", "chat:send"),
    ("GET", r"/v1/sessions/[^/]+/outbox", "outbox:read"),
    ("GET", r"/v1/memories", "memory:read"),
    ("DELETE", r"/v1/memories", "memory:manage"),
    ("DELETE", r"/v1/memories/[^/]+", "memory:manage"),
    ("GET", r"/v1/privacy/customers/.+/export", "privacy:manage"),
    ("DELETE", r"/v1/privacy/customers/.+", "privacy:manage"),
    ("DELETE", r"/v1/privacy/sessions/.+", "privacy:manage"),
    ("POST", r"/v1/privacy/retention/run", "privacy:manage"),
    ("GET", r"/v1/knowledge/sources", "knowledge:read"),
    ("POST", r"/v1/knowledge/sources", "knowledge:write"),
    ("DELETE", r"/v1/knowledge/sources/[^/]+", "knowledge:write"),
    ("PUT", r"/v1/knowledge/sources/[^/]+/documents/.+", "knowledge:write"),
    ("DELETE", r"/v1/knowledge/sources/[^/]+/documents/.+", "knowledge:write"),
    ("GET", r"/v1/knowledge/documents", "knowledge:read"),
    ("GET", r"/v1/knowledge/search", "knowledge:read"),
    ("GET", r"/v1/monitor/findings", "monitor:read"),
    ("GET", r"/v1/monitor/summary", "monitor:read"),
    ("GET", r"/v1/traces", "traces:read"),
    ("GET", r"/v1/traces/[^/]+", "traces:read"),
    ("GET", r"/v1/agents", "agents:read"),
    ("GET", r"/v1/agents/[^/]+/live", "agents:read"),
    ("GET", r"/v1/agents/[^/]+/versions", "versions:read"),
    ("GET", r"/v1/agents/[^/]+/versions/[^/]+", "versions:read"),
    ("GET", r"/v1/agents/[^/]+/versions/[^/]+/diff/[^/]+", "versions:read"),
    ("GET", r"/v1/agents/[^/]+/releases", "versions:read"),
    ("POST", r"/v1/agents/[^/]+/versions", "versions:create"),
    ("POST", r"/v1/agents/[^/]+/releases", "releases:publish"),
    ("POST", r"/v1/agents/[^/]+/rollback", "releases:rollback"),
    ("GET", r"/v1/approvals", "approvals:read"),
    ("POST", r"/v1/approvals/expire", "approvals:decide"),
    ("POST", r"/v1/approvals/[^/]+/decision", "approvals:decide"),
    ("GET", r"/v1/routing", "handoffs:read"),
    ("GET", r"/v1/handoffs", "handoffs:read"),
    ("GET", r"/v1/handoffs/[^/]+/inbox", "handoffs:read"),
    ("GET", r"/v1/handoffs/[^/]+", "handoffs:read"),
    ("POST", r"/v1/handoffs/[^/]+/resolve", "handoffs:resolve"),
    ("GET", r"/v1/simulations/(scenarios|runs|gate)", "simulations:read"),
    ("GET", r"/v1/simulations/runs/[^/]+", "simulations:read"),
    ("POST", r"/v1/simulations/runs", "simulations:run"),
    ("GET", r"/v1/keys", "keys:manage"),
    ("POST", r"/v1/keys", "keys:manage"),
    ("POST", r"/v1/keys/[^/]+/revoke", "keys:manage"),
    ("GET", r"/v1/audit", "audit:read"),
    ("GET", r"/v1/audit/verify", "audit:read"),
]
PUBLIC_ROUTES = {("GET", "/"), ("GET", "/health"), ("GET", "/ready")}
_COMPILED = [(m, re.compile(p), perm) for m, p, perm in ROUTE_PERMISSIONS]
log = logging.getLogger("northcx.server")


def permission_for(method: str, path: str) -> str | None:
    return next((perm for m, rx, perm in _COMPILED if m == method and rx.fullmatch(path)), None)


def create_app(runtime: Runtime, traces: TraceRepo, agents: dict[str, Agent], api_key: str | None = None,
               approval_ttl_seconds: float | None = None, simulations: SimulationService | None = None,
               releases: ReleaseService | None = None, access: AccessControl | None = None,
               audit: AuditRepo | None = None, email: EmailChannel | None = None,
               idempotency: IdempotencyStore | None = None, knowledge: KnowledgeStore | None = None,
               retention_days: float | None = None, sms: SmsChannel | None = None) -> FastAPI:
    if access is None:  # `api_key` is the single bootstrap admin key; with neither, the server is open (development)
        access = AccessControl(bootstrap_key=api_key)
    if access.signer is None:  # chat tokens need a signing secret: derive it from the bootstrap key, else use a random one
        secret = derive_secret(None, api_key) or secrets.token_bytes(32)
        access.signer = TokenSigner(secret)
    audit = audit or InMemoryAudit()
    idem = idempotency or InMemoryIdempotency()
    kb = knowledge or InMemoryKnowledge()
    privacy = PrivacyService(runtime.privacy)
    if isinstance(runtime.privacy, InMemoryPrivacy):  # the in-memory backend reaches the other in-memory stores through these
        runtime.privacy.idempotency = idem
        if email is not None:
            runtime.privacy.email = email.repo
        if sms is not None:
            runtime.privacy.sms = sms.repo
    provider = as_provider(agents)
    agents = provider  # everything below resolves agents through the provider
    flow = ApprovalFlow(runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = flusher = None
        if runtime.outbox.notifier is not None:  # retry deliveries that failed (email, webhooks) with back-off
            async def flush_loop() -> None:
                while True:
                    await asyncio.sleep(15)
                    try:
                        await runtime.outbox.flush()
                    except Exception:
                        log.exception("outbox flush failed")

            flusher = asyncio.create_task(flush_loop())
        if approval_ttl_seconds:  # periodically expire stale approvals and hand those conversations to a person
            async def sweep() -> None:
                while True:
                    await asyncio.sleep(max(1.0, min(60.0, approval_ttl_seconds / 2)))
                    try:
                        await flow.expire_stale(agents, approval_ttl_seconds)
                    except Exception:  # keep sweeping; a failed pass is retried on the next tick
                        pass

            task = asyncio.create_task(sweep())
        inbox_task = None
        if runtime.inbox is not None:
            async def inbox_loop() -> None:
                while True:
                    await asyncio.sleep(10)
                    try:
                        await runtime.inbox.flush(runtime.handoffs)
                    except Exception:
                        log.exception("inbox delivery pass failed")

            inbox_task = asyncio.create_task(inbox_loop())
        retention = None
        if retention_days:  # age out old conversations once an hour
            async def retain() -> None:
                while True:
                    await asyncio.sleep(3600)
                    try:
                        r = await privacy.purge_idle(retention_days)
                        if r["sessions"]:
                            await audit.append(AuditEntry(actor="system", role="system", key_id=None, action="privacy.retention", target=f"older than {retention_days:g} days",
                                                          outcome="success", detail=r))
                    except Exception:
                        log.exception("retention sweep failed")

            retention = asyncio.create_task(retain())
        yield
        for t in (task, flusher, retention, inbox_task):
            if t:
                t.cancel()

    # The interactive API docs are off: they would describe the API to anyone who can reach the server.
    app = FastAPI(title="NorthCX", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    limits = access.limits

    def too_many(retry: float, what: str) -> JSONResponse:
        r = _err(429, "rate_limited", f"Too many {what}; retry in {max(1, round(retry))} s")
        r.headers["Retry-After"] = str(max(1, round(retry)))
        return r

    async def record(request: Request | None, action: str, target: str = "", outcome: str = "success", **detail: Any) -> None:
        """Write an audit entry for the caller. A failure to record is raised: a privileged action must not go unrecorded."""
        who: Identity = getattr(request.state, "identity", OPEN_IDENTITY) if request is not None else OPEN_IDENTITY
        try:
            await audit.append(AuditEntry(actor=who.name, role=who.role, key_id=who.key_id, action=action, target=target,
                                          outcome=outcome, detail=detail))
        except Exception:
            log.exception("AUDIT FAILURE: could not record %s on %s", action, target)
            raise

    def actor(request: Request, claimed: str | None) -> str:
        """Who is acting. With authentication it is the key's name; a name in the body is only trusted without it."""
        who: Identity = request.state.identity
        return (claimed.strip() if claimed and claimed.strip() else "anonymous") if who.open_mode else who.name

    @app.middleware("http")
    async def guard(request: Request, call_next):
        method, path = request.method, request.url.path
        if (method, path) in PUBLIC_ROUTES or not path.startswith("/v1/"):
            return await call_next(request)
        perm = permission_for(method, path)
        if perm is None:  # an unlisted route is refused, never served
            return _err(404, "not_found", "No such endpoint")
        ip = request.client.host if request.client else "unknown"
        if await access.enabled():
            header = request.headers.get("authorization", "")
            ident, why = await access.authenticate_detail(header[7:] if header.startswith("Bearer ") else None)
            if ident is None:
                if limits and not access.limiter.allow(f"authfail:{ip}", limits.auth_failures_per_minute)[0]:
                    return too_many(60, "failed sign-in attempts")
                if access.limiter.allow(f"authlog:{ip}", 6)[0]:  # sampled, so guessing cannot flood the log
                    await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target=path,
                                                  outcome="denied", detail={"client": ip}))
                if why == "expired":
                    return _err(401, "token_expired", "This chat session has expired; ask the site for a new one")
                return _err(401, "unauthorized", "Missing or invalid API key")
        else:
            ident = OPEN_IDENTITY
        request.state.identity = ident
        if limits:
            ok, retry = access.limiter.allow(f"key:{ident.key_id or ip}", limits.per_key_per_minute)
            if not ok:
                return too_many(retry, "requests")
        if perm != "authenticated" and not ident.can(perm):
            await record(request, "auth.denied", f"{method} {path}", "denied", permission=perm)
            return _err(403, "forbidden", f"The '{ident.role}' role cannot do this (needs {perm})")
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return _err(400, "bad_request", str(exc.errors()))

    @app.get("/", response_class=HTMLResponse)
    async def widget() -> str:
        return WIDGET_HTML

    @app.get("/health")
    async def health() -> dict[str, bool]:
        """Liveness: the process is up."""
        return {"ok": True}

    @app.get("/ready")
    async def ready() -> Any:
        """Readiness: the stores answer (for Postgres, the database is reachable). Used by load balancers and orchestrators."""
        try:
            await runtime.store.load_messages("__readiness_probe__")
            await traces.summaries(limit=1)
        except Exception:
            log.exception("readiness check failed")
            return JSONResponse({"ready": False}, status_code=503)
        return {"ready": True}

    @app.post("/v1/agents/{agent_id}/chat/stream")
    async def chat_stream(agent_id: str, body: ChatBody, request: Request) -> Any:
        """Server-sent events: `progress` while tools run, then the reply in `delta` pieces, then `done`.

        The reply is released only after every supervisor has approved it, so the customer never sees text that a
        check could still reject; `delta` pieces are the approved reply, delivered progressively.
        """
        who: Identity = request.state.identity
        customer_id = body.customer_id
        if request.headers.get("idempotency-key"):
            return _err(400, "unsupported", "Idempotency-Key is not supported on the streaming endpoint; use /chat")
        if who.session_id is not None:
            if body.session_id != who.session_id or (who.agent and agent_id != who.agent):
                await record(request, "auth.denied", f"POST /v1/agents/{agent_id}/chat/stream", "denied", reason="outside the token's scope")
                return _err(403, "forbidden", "This chat token cannot be used for that conversation or agent")
            customer_id = who.customer_id
        if limits:
            ok, retry = access.limiter.allow(f"session:{body.session_id}", limits.chat_per_session_per_minute)
            if not ok:
                return too_many(retry, "messages in this conversation")
        try:
            agent = await provider.get(agent_id)
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            return _err(404, "not_found", "Unknown agent")
        queue: asyncio.Queue = asyncio.Queue()

        async def work() -> None:
            try:
                r = await runtime.run(agent, body.session_id, body.message, customer_id, progress=lambda e: queue.put_nowait(("progress", e)),
                                      channel=body.channel or ("web" if who.session_id else None))
                queue.put_nowait(("result", r))
            except Exception:
                queue.put_nowait(("error", {"code": "internal", "message": "Run failed"}))

        def sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        async def events() -> Any:
            task = asyncio.create_task(work())
            try:
                yield sse("started", {"agent": agent_id})
                while True:
                    kind, payload = await queue.get()
                    if kind == "progress":
                        yield sse("progress", payload)
                    elif kind == "error":
                        yield sse("error", payload)
                        return
                    else:
                        for piece in _pieces(payload.reply):
                            yield sse("delta", {"text": piece})
                        yield sse("done", {"reply": payload.reply, "status": payload.status, "traceId": payload.trace_id,
                                           "pendingApprovals": payload.pending_approvals, "handoffId": payload.handoff_id,
                                           "agentVersion": agent.version})
                        return
            finally:
                if not task.done():
                    await task  # the customer's message is always handled and saved, even if the client disconnects

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/v1/agents/{agent_id}/chat")
    async def chat(agent_id: str, body: ChatBody, request: Request) -> Any:
        who: Identity = request.state.identity
        customer_id = body.customer_id
        if who.session_id is not None:  # a chat token: one conversation, one customer, one agent
            if body.session_id != who.session_id or (who.agent and agent_id != who.agent):
                await record(request, "auth.denied", f"POST /v1/agents/{agent_id}/chat", "denied", reason="outside the token's scope")
                return _err(403, "forbidden", "This chat token cannot be used for that conversation or agent")
            customer_id = who.customer_id  # set by the company's server; the customer cannot choose it
        if limits:
            ok, retry = access.limiter.allow(f"session:{body.session_id}", limits.chat_per_session_per_minute)
            if not ok:
                return too_many(retry, "messages in this conversation")
        ikey = request.headers.get("idempotency-key")
        scope = None
        if ikey is not None:
            if not valid_key(ikey):
                return _err(400, "bad_idempotency_key", "Idempotency-Key must be 1-200 visible ASCII characters")
            scope = scope_hash(who.key_id or who.name, agent_id, body.session_id, ikey)
            out = await idem.begin(scope, request_hash([body.message, customer_id]), session_id=body.session_id)
            if out.state == "replay":
                return JSONResponse(out.response, headers={"Idempotent-Replay": "true"})
            if out.state == "conflict":
                return _err(422, "idempotency_key_reused", "This Idempotency-Key was used with a different request")
            if out.state == "in_progress":
                return _err(409, "request_in_progress", "A request with this Idempotency-Key is still being processed; retry shortly")
        try:
            agent = await provider.get(agent_id)
        except AgentUnavailable as e:
            if scope:
                await idem.abandon(scope)
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            if scope:
                await idem.abandon(scope)
            return _err(404, "not_found", "Unknown agent")
        try:
            r = await runtime.run(agent, body.session_id, body.message, customer_id, channel=body.channel or ("web" if who.session_id else None))
        except Exception:
            if scope:
                await idem.abandon(scope)
            return _err(500, "internal", "Run failed")
        result = {"reply": r.reply, "status": r.status, "traceId": r.trace_id, "pendingApprovals": r.pending_approvals,
                  "handoffId": r.handoff_id, "agentVersion": agent.version}
        if scope:
            await idem.complete(scope, result)
        return result

    @app.get("/v1/traces/{trace_id}")
    async def get_trace(trace_id: str) -> Any:
        t = await traces.get(trace_id)
        return t.to_dict() if t else _err(404, "not_found", "Unknown trace")

    # ---- long-term memory ----
    @app.get("/v1/memories")
    async def memories_list(customerId: str, request: Request) -> Any:
        if runtime.memories is None:
            return _err(501, "not_configured", "Memory is not enabled")
        items = await runtime.memories.list(customerId)
        await record(request, "memory.read", customer_ref(customerId), count=len(items))
        return JSONResponse({"customerId": customerId, "memories": [m.to_dict() for m in items]}, headers={"Cache-Control": "no-store"})

    @app.delete("/v1/memories/{memory_id}")
    async def memories_forget(memory_id: str, customerId: str, request: Request) -> Any:
        if runtime.memories is None:
            return _err(501, "not_configured", "Memory is not enabled")
        if not await runtime.memories.forget(customerId, memory_id):
            return _err(404, "not_found", "Unknown memory")
        await record(request, "memory.forget", customer_ref(customerId), memory=memory_id)
        return {"deleted": True}

    @app.delete("/v1/memories")
    async def memories_forget_all(customerId: str, request: Request) -> Any:
        if runtime.memories is None:
            return _err(501, "not_configured", "Memory is not enabled")
        n = await runtime.memories.forget_all(customerId)
        await record(request, "memory.forget_all", customer_ref(customerId), count=n)
        return {"deleted": n}

    # ---- privacy: export, erasure, retention ----
    @app.get("/v1/privacy/customers/{customer_id:path}/export")
    async def privacy_export(customer_id: str, request: Request) -> Any:
        data = await privacy.export_customer(customer_id)
        await record(request, "privacy.export", customer_ref(customer_id), sessions=len(data["sessions"]))
        return JSONResponse(data, headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="customer-export.json"'})

    @app.delete("/v1/privacy/customers/{customer_id:path}")
    async def privacy_erase_customer(customer_id: str, request: Request) -> Any:
        r = await privacy.erase_customer(customer_id)
        if runtime.context is not None:
            runtime.context.forget(customer_id)  # do not keep serving the cached copy
        await record(request, "privacy.erase.customer", customer_ref(customer_id), **r)
        return r

    @app.delete("/v1/privacy/sessions/{session_id:path}")
    async def privacy_erase_session(session_id: str, request: Request) -> Any:
        r = await privacy.erase_session(session_id)
        await record(request, "privacy.erase.session", customer_ref(session_id), removed=r)
        return {"removed": r}

    @app.post("/v1/privacy/retention/run")
    async def privacy_retention(body: RetentionBody, request: Request) -> Any:
        r = await privacy.purge_idle(body.older_than_days)
        await record(request, "privacy.retention", f"older than {body.older_than_days:g} days", **r)
        return r

    # ---- knowledge ----
    @app.get("/v1/knowledge/sources")
    async def kb_sources() -> Any:
        return {"sources": [{"id": s.id, "name": s.name, "staleAfterDays": s.stale_after_days, "createdAt": s.created_at} for s in await kb.list_sources()]}

    @app.post("/v1/knowledge/sources", status_code=201)
    async def kb_create_source(body: SourceBody, request: Request) -> Any:
        try:
            s = await kb.create_source(Source(body.id, body.name, body.stale_after_days))
        except KnowledgeError as e:
            return _err(400 if "already exists" not in str(e) else 409, "bad_request" if "already exists" not in str(e) else "conflict", str(e))
        await record(request, "knowledge.source.create", s.id, name=s.name)
        return {"id": s.id, "name": s.name, "staleAfterDays": s.stale_after_days}

    @app.delete("/v1/knowledge/sources/{source_id}")
    async def kb_delete_source(source_id: str, request: Request) -> Any:
        if await kb.get_source(source_id) is None:
            return _err(404, "not_found", "Unknown source")
        n = await kb.delete_source(source_id)
        await record(request, "knowledge.source.delete", source_id, documents=n)
        return {"deleted": True, "documents": n}

    @app.put("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_put_document(source_id: str, external_id: str, body: DocumentBody, request: Request) -> Any:
        try:
            r = await kb.upsert(source_id, external_id, body.title, body.url, body.text, body.source_updated_at)
        except KnowledgeError as e:
            return _err(404 if str(e).startswith("Unknown source") else 400, "not_found" if str(e).startswith("Unknown source") else "bad_request", str(e))
        if r.status != "unchanged":
            await record(request, "knowledge.document.put", f"{source_id}/{external_id}", status=r.status, chunks=r.document.chunks)
        return {"status": r.status, "document": r.document.to_dict()}

    @app.delete("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_delete_document(source_id: str, external_id: str, request: Request) -> Any:
        if not await kb.delete(source_id, external_id):
            return _err(404, "not_found", "Unknown document")
        await record(request, "knowledge.document.delete", f"{source_id}/{external_id}")
        return {"deleted": True}

    @app.get("/v1/knowledge/documents")
    async def kb_documents(source: str | None = None, stale: bool = False, limit: int = 200) -> Any:
        rows = await kb.documents(source, stale, max(1, min(limit, 1000)))
        return {"documents": [d.to_dict(days) for d, days in rows]}

    @app.get("/v1/knowledge/search")
    async def kb_search(q: str, source: str | None = None, limit: int = 5) -> Any:
        found = await kb.search(q, max(1, min(limit, 20)), source)
        return {"passages": [{"documentId": p.document_id, "sourceId": p.source_id, "title": p.title, "url": p.url, "section": p.heading,
                              "text": p.text, "score": p.score, "updatedAt": p.updated_at, "stale": p.stale} for p in found]}

    @app.get("/v1/monitor/findings")
    async def monitor_findings(rule: str | None = None, severity: str | None = None, agentId: str | None = None,
                               sessionId: str | None = None, since: float | None = None, limit: int = 100) -> Any:
        items = await runtime.monitor.repo.list(rule=rule, severity=severity, agent_id=agentId, session_id=sessionId,
                                                since=since, limit=max(1, min(limit, 500)))
        return {"findings": [f.to_dict() for f in items]}

    @app.get("/v1/monitor/summary")
    async def monitor_summary(since: float | None = None) -> Any:
        counts = await runtime.monitor.repo.counts(since)
        return {"rules": sorted(runtime.monitor.rules), "counts": counts,
                "total": sum(n for by in counts.values() for n in by.values())}

    @app.get("/v1/traces")
    async def list_traces(sessionId: str | None = None, limit: int = 200) -> Any:
        items = await traces.summaries(sessionId, max(1, min(limit, 1000)))
        return {"traces": [{"id": t.id, "agentId": t.agent_id, "sessionId": t.session_id, "events": t.events,
                            "status": t.status, "startedAt": t.started_at, "tools": t.tools,
                            "agentVersion": t.agent_version} for t in items]}

    @app.get("/v1/agents")
    async def list_agents() -> Any:
        try:
            live = await provider.all()
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        return {"agents": [{"id": a.id, "version": a.version, "digest": a.digest, "instructions": a.instructions, "model": a.model, "maxSteps": a.max_steps,
                            "tools": [{"name": t.name, "description": t.description, "approval": t.requires_approval is not None}
                                      for t in a.tools],
                            "guardrails": [g.name for g in a.guardrails],
                            "inputGuardrails": [g.name for g in a.input_guardrails],
                            "outputGuardrails": [g.name for g in a.output_guardrails],
                            "forcedTopics": [t.name for t in a.forced_handoffs]} for a in live]}

    @app.get("/v1/approvals")
    async def list_approvals(state: str | None = None) -> Any:
        return {"approvals": [a.__dict__ for a in await runtime.approvals.list(state)]}

    @app.post("/v1/approvals/{approval_id}/decision")
    async def decide(approval_id: str, body: DecisionBody, request: Request) -> Any:
        """Record the decision, run the action if approved, and continue the conversation. The customer receives the
        outcome through the outbox (and the webhook, if configured)."""
        try:
            res = await flow.resolve(agents, approval_id, body.approved, actor(request, body.by), body.note)
        except KeyError:
            return _err(404, "not_found", "Unknown approval")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        await record(request, "approval.decide", approval_id, tool=res.approval.tool, approved=body.approved,
                     state=res.approval.state, note=bool(body.note), follow_up=res.run.status if res.run else "none")
        out = dict(res.approval.__dict__)
        out["resume"] = ({"reply": res.run.reply, "status": res.run.status, "traceId": res.run.trace_id}
                         if res.run else {"error": res.error})
        if res.run and res.error:
            out["resume"]["error"] = res.error
        return out

    @app.post("/v1/approvals/expire")
    async def expire(body: ExpireBody, request: Request) -> Any:
        done = await flow.expire_stale(agents, body.older_than_seconds)
        await record(request, "approval.expire", "", older_than_seconds=body.older_than_seconds, approvals=[a.id for a in done])
        return {"expired": [a.id for a in done]}

    def handoff_json(h: Any, full: bool = False) -> dict[str, Any]:
        out = {"id": h.id, "sessionId": h.session_id, "traceId": h.trace_id, "agentId": h.agent_id, "customerId": h.customer_id,
               "trigger": h.trigger, "reason": h.reason, "topics": h.topics, "state": h.state, "createdAt": h.created_at,
               "resolvedBy": h.resolved_by, "resolvedAt": h.resolved_at, "note": h.note, "summary": h.package.get("summary"),
               "queue": h.queue, "afterHours": h.after_hours}
        if full:
            out["package"] = h.package
        return out

    @app.get("/v1/routing")
    async def routing_status() -> Any:
        """Queues, their hours and whether each is open right now."""
        return runtime.router.describe()

    @app.get("/v1/handoffs")
    async def list_handoffs(state: str | None = None, sessionId: str | None = None, limit: int = 200, queue: str | None = None) -> Any:
        items = await runtime.handoffs.list(state, sessionId, max(1, min(limit, 1000)), queue)
        return {"handoffs": [handoff_json(h) for h in items]}

    @app.get("/v1/handoffs/{handoff_id}/inbox")
    async def handoff_inbox(handoff_id: str) -> Any:
        """Where this hand-off has been sent (helpdesk reference, attempts, last error)."""
        if await runtime.handoffs.get(handoff_id) is None:
            return _err(404, "not_found", "Unknown handoff")
        events = await runtime.inbox.repo.for_handoff(handoff_id) if runtime.inbox is not None else []
        return {"configured": runtime.inbox is not None, "deliveries": [e.to_dict() for e in events]}

    @app.get("/v1/handoffs/{handoff_id}")
    async def get_handoff(handoff_id: str) -> Any:
        h = await runtime.handoffs.get(handoff_id)
        return handoff_json(h, full=True) if h else _err(404, "not_found", "Unknown handoff")

    @app.post("/v1/handoffs/{handoff_id}/resolve")
    async def resolve_handoff(handoff_id: str, body: ResolveBody, request: Request) -> Any:
        try:
            done = await runtime.handoffs.resolve(handoff_id, actor(request, body.by), body.note)
            if runtime.inbox is not None:
                try:
                    await runtime.inbox.enqueue(done, "resolved")
                except Exception:
                    log.exception("could not queue the resolution for the inbox")
            await record(request, "handoff.resolve", handoff_id, trigger=done.trigger, note=bool(body.note))
            return handoff_json(done)
        except KeyError:
            return _err(404, "not_found", "Unknown handoff")
        except ValueError as e:
            return _err(409, "conflict", str(e))

    def need_sim() -> SimulationService | JSONResponse:
        return simulations or _err(501, "not_configured", "Simulations are not configured on this server")

    def run_json(r: Any, full: bool = False) -> dict[str, Any]:
        out = {"id": r.id, "createdAt": r.created_at, "mode": r.mode, "source": r.source, "passed": r.passed,
               "counts": r.counts, "seconds": r.seconds, "meta": r.meta, "agentDigests": r.agent_digests}
        if full:
            out["results"] = r.results
        return out

    @app.get("/v1/simulations/scenarios")
    async def sim_scenarios() -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        return {"modes": sim.modes, "scenarios": [
            {"name": s.name, "agent": s.agent, "required": s.required, "description": s.description, "steps": len(s.turns),
             "judge": s.judge is not None, "digest": s.digest()} for s in sim.scenarios]}

    @app.post("/v1/simulations/runs")
    async def sim_run(body: SimRunBody, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        spec = None
        if body.version is not None:
            if releases is None or not body.agent:
                return _err(400, "bad_request", "Running a saved version needs 'agent' and a configured version store")
            v = await releases.versions.get_number(body.agent, body.version)
            if v is None:
                return _err(404, "not_found", f"Agent '{body.agent}' has no version {body.version}")
            spec = AgentSpec.model_validate(v.spec)
        try:
            run = await sim.run(body.mode, body.only, body.skip_judge, source="api",
                                meta={"version": body.version} if body.version else None, spec=spec)
        except Busy as e:
            return _err(409, "busy", str(e))
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "simulation.run", run.id, mode=run.mode, passed=run.passed, counts=run.counts,
                     agent=body.agent, version=body.version)
        return run_json(run)

    @app.get("/v1/simulations/runs")
    async def sim_runs(limit: int = 50) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        return {"runs": [run_json(r) for r in await sim.runs.list(max(1, min(limit, 200)))]}

    @app.get("/v1/simulations/runs/{run_id}")
    async def sim_run_detail(run_id: str) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        r = await sim.runs.get(run_id)
        return run_json(r, full=True) if r else _err(404, "not_found", "Unknown run")

    @app.get("/v1/simulations/gate")
    async def sim_gate(agent: str | None = None, version: int | None = None) -> Any:
        """Has each agent's current version passed every required scenario? (Used to gate releases.)"""
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        ids = [agent] if agent else sorted(sim.agent_digests)
        out = []
        for a in ids:
            if version is not None:
                v = await releases.versions.get_number(a, version) if releases else None
                if v is None:
                    return _err(404, "not_found", f"Agent '{a}' has no version {version}")
                g = await sim.gate_for(a, v.digest)
            else:
                g = await sim.gate(a)
            out.append({"agent": g.agent_id, "agentDigest": g.agent_digest, "satisfied": g.satisfied, "required": g.required,
                        "covered": g.covered, "reasons": g.reasons, "runIds": g.run_ids})
        return {"gates": out}

    # ---------------- email channel ----------------
    MAX_EMAIL_BYTES = 1_000_000

    @app.post("/v1/channels/email/inbound")
    async def email_inbound(request: Request) -> Any:
        """The company's mail system forwards each raw message here (Content-Type message/rfc822)."""
        if email is None:
            return _err(501, "not_configured", "The email channel is not configured (set NORTHCX_EMAIL_FROM and NORTHCX_SMTP_URL)")
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_EMAIL_BYTES:
            return _err(413, "too_large", "Message is too large")
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_EMAIL_BYTES:
                return _err(413, "too_large", "Message is too large")
        try:
            res = await email.receive(raw)
        except EmailParseError as e:
            return _err(400, "bad_message", str(e))
        except Exception:
            log.exception("email inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return {"status": res.status, "sessionId": res.session_id, "reason": res.reason, "traceId": res.trace_id,
                "handoffId": res.handoff_id}

    # ---------------- SMS ----------------
    @app.post("/channels/sms/twilio")
    async def sms_inbound(request: Request) -> Any:
        """Public webhook for the SMS provider. It is not behind an API key: every request must carry the provider's signature."""
        if sms is None:
            return _err(501, "not_configured", "The SMS channel is not configured")
        ip = request.client.host if request.client else "unknown"
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 65536:
                return _err(413, "too_large", "Request is too large")
        try:
            params = parse_form(raw)
        except ValueError:
            return _err(400, "bad_request", "Unreadable request")
        if not sms.authentic(params, request.headers.get("x-twilio-signature", "")):
            if limits and not access.limiter.allow(f"smsfail:{ip}", limits.auth_failures_per_minute)[0]:
                return too_many(60, "unsigned requests")  # only failures count, so real traffic is never throttled by this
            if access.limiter.allow(f"smslog:{ip}", 6)[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/channels/sms/twilio", outcome="denied", detail={"client": ip}))
            return _err(403, "forbidden", "Invalid signature")
        try:
            await sms.receive(params)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        except Exception:
            log.exception("sms inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return Response(content="<Response></Response>", media_type="text/xml")  # replies go out through the outbox

    # ---------------- chat tokens ----------------
    @app.post("/v1/chat-tokens", status_code=201)
    async def mint_chat_token(body: TokenBody, request: Request) -> Any:
        """Called by the company's server (holding a channel key), never by the customer's browser. Returns a token that
        lets one browser talk in one conversation as one customer until it expires."""
        who: Identity = request.state.identity
        if access.signer is None:
            return _err(501, "not_configured", "Chat tokens are not configured: set NORTHCX_TOKEN_SECRET or NORTHCX_API_KEY")
        if not MIN_TTL <= body.ttl_seconds <= MAX_TTL:
            return _err(400, "bad_request", f"ttlSeconds must be between {MIN_TTL} and {MAX_TTL}")
        sid = body.session_id or f"web-{uuid.uuid4().hex}"
        token, claims = access.signer.mint(sid=sid, kid=who.key_id or "open", cid=body.customer_id, agent=body.agent, ttl=body.ttl_seconds)
        return JSONResponse({"token": token, "sessionId": sid, "customerId": body.customer_id, "agent": body.agent,
                             "expiresAt": claims.exp, "ttlSeconds": body.ttl_seconds}, status_code=201)

    # ---------------- identity, keys and audit ----------------
    @app.get("/v1/me")
    async def me(request: Request) -> Any:
        who: Identity = request.state.identity
        return {"name": who.name, "role": who.role, "openMode": who.open_mode, "keyId": who.key_id,
                "permissions": sorted(who.permissions)}

    def key_json(k: Any) -> dict[str, Any]:
        return {"id": k.key_id, "prefix": k.prefix, "name": k.name, "role": k.role, "createdBy": k.created_by,
                "createdAt": k.created_at, "expiresAt": k.expires_at, "revokedAt": k.revoked_at, "revokedBy": k.revoked_by,
                "lastUsedAt": k.last_used_at, "active": k.active()}

    @app.get("/v1/keys")
    async def list_keys() -> Any:
        return {"roles": {r: sorted(p) for r, p in ROLES.items()}, "keys": [key_json(k) for k in await access.keys.list()]}

    @app.post("/v1/keys", status_code=201)
    async def create_key(body: KeyBody, request: Request) -> Any:
        try:
            key, secret = await access.issue(body.name, body.role, actor(request, None), body.expires_in_days)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "key.create", key.prefix, name=key.name, role=key.role, expires=key.expires_at)
        return JSONResponse({**key_json(key), "key": secret}, status_code=201)  # the only time the secret is shown

    @app.post("/v1/keys/{key_id}/revoke")
    async def revoke_key(key_id: str, request: Request) -> Any:
        try:
            key = await access.revoke(key_id, actor(request, None))
        except KeyError:
            return _err(404, "not_found", "Unknown key")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        await record(request, "key.revoke", key.prefix, name=key.name, role=key.role)
        return key_json(key)

    @app.get("/v1/audit")
    async def audit_log(limit: int = 100, before: int | None = None, actor_name: str | None = None, action: str | None = None) -> Any:
        rows = await audit.list(max(1, min(limit, 500)), before, actor_name, action)
        return {"entries": [{"id": e.id, "at": e.at, "actor": e.actor, "role": e.role, "keyId": e.key_id, "action": e.action,
                             "target": e.target, "outcome": e.outcome, "detail": e.detail} for e in rows]}

    @app.get("/v1/audit/verify")
    async def audit_verify() -> Any:
        v = await audit.verify()
        return {"ok": v.ok, "checked": v.checked, "brokenAt": v.broken_at, "reason": v.reason, "head": v.head}

    # ---------------- versions and releases ----------------
    def need_rel() -> ReleaseService | JSONResponse:
        return releases or _err(501, "not_configured", "Versions and releases are not configured on this server")

    def version_json(v: Any, live_number: int | None = None, released: set[int] | None = None, full: bool = False) -> dict[str, Any]:
        out = {"id": v.id, "agentId": v.agent_id, "number": v.number, "digest": v.digest, "author": v.author, "note": v.note,
               "createdAt": v.created_at, "live": live_number == v.number, "everReleased": v.number in (released or set())}
        if full:
            out["spec"] = v.spec
            out["specYaml"] = spec_yaml(v.spec)
        return out

    def release_json(r: Any) -> dict[str, Any]:
        return {"id": r.id, "agentId": r.agent_id, "environment": r.environment, "action": r.action, "version": r.number,
                "versionId": r.version_id, "previousVersion": r.previous_number, "by": r.by, "note": r.note, "gate": r.gate,
                "createdAt": r.created_at, "toBaseline": r.version_id is None}

    def rel_error(e: Exception) -> JSONResponse:
        if isinstance(e, NotFound):
            return _err(404, "not_found", str(e))
        if isinstance(e, GateBlocked):
            resp = _err(409, "gate_not_satisfied", str(e))
            resp.body = json.dumps({"error": {"code": "gate_not_satisfied", "message": str(e), "reasons": e.reasons}}).encode()
            resp.headers["content-length"] = str(len(resp.body))
            return resp
        if isinstance(e, Conflict):
            return _err(409, "conflict", str(e))
        return _err(400, "bad_request", str(e))

    @app.post("/v1/agents/{agent_id}/versions", status_code=201)
    async def create_version(agent_id: str, body: VersionBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        given = [x for x in (body.spec is not None, body.spec_yaml is not None, body.from_baseline) if x]
        if len(given) != 1:
            return _err(400, "bad_request", "Give exactly one of 'spec', 'specYaml' or 'fromBaseline'")
        try:
            if body.from_baseline:
                spec = svc.baseline(agent_id)
                if spec is None:
                    return _err(404, "not_found", f"Agent '{agent_id}' has no baseline spec file")
            elif body.spec_yaml is not None:
                spec = parse_spec(body.spec_yaml)
            else:
                spec = AgentSpec.model_validate(body.spec)
            v = await svc.create_version(agent_id, spec, actor(request, body.by), body.note)
        except (SpecError, InvalidSpec, Conflict, ValueError) as e:
            return rel_error(e if isinstance(e, (InvalidSpec, Conflict)) else InvalidSpec(str(e)))
        await record(request, "version.create", f"{agent_id}@{v.number}", digest=v.digest[:12])
        return JSONResponse(version_json(v, full=True), status_code=201)

    @app.get("/v1/agents/{agent_id}/versions")
    async def list_versions(agent_id: str) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        live_v, _ = await svc.live(agent_id)
        history = await svc.releases.list(agent_id)
        released = {r.number for r in history if r.number is not None}
        return {"versions": [version_json(v, live_v.number if live_v else None, released) for v in await svc.versions.list(agent_id)]}

    @app.get("/v1/agents/{agent_id}/versions/{number}")
    async def get_version(agent_id: str, number: int) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        v = await svc.versions.get_number(agent_id, number)
        if v is None:
            return _err(404, "not_found", f"Agent '{agent_id}' has no version {number}")
        live_v, _ = await svc.live(agent_id)
        return version_json(v, live_v.number if live_v else None, {r.number for r in await svc.releases.list(agent_id) if r.number}, True)

    @app.get("/v1/agents/{agent_id}/versions/{a}/diff/{b}")
    async def version_diff(agent_id: str, a: int, b: int) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        va, vb = await svc.versions.get_number(agent_id, a), await svc.versions.get_number(agent_id, b)
        if va is None or vb is None:
            return _err(404, "not_found", f"Agent '{agent_id}' needs both versions {a} and {b}")
        return {"from": a, "to": b, **diff_specs(va.spec, vb.spec)}

    @app.post("/v1/agents/{agent_id}/releases")
    async def publish(agent_id: str, body: PublishBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            rel = await svc.publish(agent_id, body.version, actor(request, body.by), body.note)
        except GateBlocked as e:  # an attempt to release something unproven is itself worth recording
            await record(request, "release.publish", f"{agent_id}@{body.version}", "blocked", reasons=e.reasons[:10])
            return rel_error(e)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.publish", f"{agent_id}@{rel.number}", previous=rel.previous_number, gate=rel.gate,
                     note=bool(body.note))
        return release_json(rel)

    @app.post("/v1/agents/{agent_id}/rollback")
    async def rollback(agent_id: str, body: RollbackBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            rel = await svc.rollback(agent_id, actor(request, body.by), body.note, body.to_version)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.rollback", f"{agent_id}@{rel.number if rel.number else 'spec-file'}",
                     previous=rel.previous_number, note=bool(body.note))
        return release_json(rel)

    @app.get("/v1/agents/{agent_id}/releases")
    async def release_history(agent_id: str) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        return {"releases": [release_json(r) for r in await svc.releases.list(agent_id)]}

    @app.get("/v1/agents/{agent_id}/live")
    async def live(agent_id: str) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        v, rel = await svc.live(agent_id)
        base = svc.baseline(agent_id)
        if v is None and base is None:
            return _err(404, "not_found", f"Unknown agent '{agent_id}'")
        spec = v.spec if v else json.loads(base.canonical())
        return {"agentId": agent_id, "source": "release" if v else "baseline", "version": v.number if v else None,
                "digest": v.digest if v else base.digest(), "release": release_json(rel) if rel else None,
                "spec": spec, "specYaml": spec_yaml(spec)}

    @app.get("/v1/sessions/{session_id}/outbox")
    async def outbox(session_id: str, request: Request, after: int = 0) -> Any:
        who: Identity = request.state.identity
        if who.session_id is not None and session_id != who.session_id:
            await record(request, "auth.denied", f"GET /v1/sessions/{session_id}/outbox", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot read another conversation")
        items = await runtime.outbox.list(session_id, after)
        return {"messages": [{"id": m.id, "kind": m.kind, "createdAt": m.created_at, **m.payload} for m in items]}

    return app
