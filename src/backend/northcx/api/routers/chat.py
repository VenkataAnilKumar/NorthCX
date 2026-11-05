"""Routes for chat: streamed and plain replies, attachments and the outbox."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from northcx.access import Identity
from northcx.api.common import _err, _pieces
from northcx.api.deps import AppDeps
from northcx.api.models import ChatBody
from northcx.attachments import accept as accept_attachment, AttachmentError, check_accepted, MAX_BYTES
from northcx.catalog import AgentUnavailable
from northcx.idempotency import request_hash, scope_hash, valid_key
from northcx.privacy import customer_ref


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    attachment_repo = d.attachment_repo
    attachment_scanner = d.attachment_scanner
    idem = d.idem
    limits = d.limits
    provider = d.provider
    record = d.record
    runtime = d.runtime
    too_many = d.too_many

    async def chat_environment(request: Request, body: ChatBody) -> JSONResponse | None:
        """Only people with developer access may talk to dev or staging; customers and channels always get production."""
        if body.environment and body.environment != "production":
            who: Identity = request.state.identity
            if who.session_id is not None or not who.can("simulations:run"):
                await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", permission="simulations:run", environment=body.environment)
                return _err(403, "forbidden", f"The '{who.role}' role cannot use the {body.environment} environment (needs simulations:run)")
        return None

    async def load_attachments(body: ChatBody, agent: Any) -> list[Any] | JSONResponse:
        """The files a message refers to: they must belong to this conversation and be of a kind the agent accepts."""
        if not body.attachments:
            return []
        found = []
        for aid in dict.fromkeys(body.attachments):
            a = await attachment_repo.get(aid)
            if a is None or a.session_id != body.session_id:
                return _err(400, "bad_request", "Unknown attachment for this conversation")
            found.append(a)
        try:
            check_accepted(found, agent.attachments)
        except AttachmentError as e:
            return _err(400, "attachment_not_accepted", str(e))
        return found

    @app.put("/v1/sessions/{session_id}/attachments", status_code=201)
    async def upload_attachment(session_id: str, request: Request, filename: str | None = None) -> Any:
        """Upload one file (the request body is the file itself). It is identified by its content, size-limited, optionally scanned, and kept with the conversation."""
        who: Identity = request.state.identity
        if who.session_id is not None and who.session_id != session_id:
            await record(request, "auth.denied", f"PUT /v1/sessions/{session_id}/attachments", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot be used for that conversation")
        if not access.limiter.allow(f"upload:{session_id}", 20)[0]:
            return too_many(60, "uploads")
        cap = max(MAX_BYTES.values())
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            return _err(413, "too_large", "The file is too large")
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > cap:
                return _err(413, "too_large", "The file is too large")
        try:
            a = await accept_attachment(attachment_repo, session_id, filename, data, who.name, attachment_scanner)
        except AttachmentError as e:
            await record(request, "attachment.refused", customer_ref(session_id), "denied", reason=str(e)[:120])
            return _err(400, "attachment_refused", str(e))
        await record(request, "attachment.upload", customer_ref(session_id), kind=a.kind, size=a.size, sha256=a.sha256[:16])
        return a.meta()

    @app.get("/v1/sessions/{session_id}/attachments")
    async def list_attachments(session_id: str) -> Any:
        return {"attachments": [a.meta() for a in await attachment_repo.for_session(session_id)]}

    @app.get("/v1/attachments/{attachment_id}")
    async def download_attachment(attachment_id: str, request: Request) -> Any:
        """The file itself, for people reviewing a conversation. Served so a browser cannot run or render it."""
        a = await attachment_repo.get(attachment_id)
        if a is None:
            return _err(404, "not_found", "Unknown attachment")
        await record(request, "attachment.download", customer_ref(a.session_id), kind=a.kind)
        return Response(a.data, media_type=a.media_type, headers={
            "Content-Disposition": f'attachment; filename="{a.name}"', "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'", "Cache-Control": "no-store"})

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
            agent = await provider.get(agent_id, "production", body.session_id)
            if agent is not None:
                agent = await runtime.active_agent(agent, body.session_id)
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            return _err(404, "not_found", "Unknown agent")
        queue: asyncio.Queue = asyncio.Queue()
        env_error = await chat_environment(request, body)
        if env_error is not None:
            return env_error
        environment = body.environment or "production"
        if environment != "production":
            try:
                agent = await provider.get(agent_id, environment, body.session_id)
                if agent is not None:
                    agent = await runtime.active_agent(agent, body.session_id, environment)
            except AgentUnavailable as e:
                return _err(503, "agent_unavailable", str(e))
            if agent is None:
                return _err(404, "not_found", "Unknown agent")

        files = await load_attachments(body, agent)
        if isinstance(files, JSONResponse):
            return files

        async def work() -> None:
            try:
                r = await runtime.run(agent, body.session_id, body.message, customer_id, attachments=files or None, progress=lambda e: queue.put_nowait(("progress", e)),
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
        env_error = await chat_environment(request, body)
        if env_error is not None:
            return env_error
        environment = body.environment or "production"
        ikey = request.headers.get("idempotency-key")
        scope = None
        if ikey is not None:
            if not valid_key(ikey):
                return _err(400, "bad_idempotency_key", "Idempotency-Key must be 1-200 visible ASCII characters")
            scope = scope_hash(who.key_id or who.name, agent_id, body.session_id, ikey)
            out = await idem.begin(scope, request_hash([body.message, customer_id, environment, sorted(body.attachments)]), session_id=body.session_id)
            if out.state == "replay":
                return JSONResponse(out.response, headers={"Idempotent-Replay": "true"})
            if out.state == "conflict":
                return _err(422, "idempotency_key_reused", "This Idempotency-Key was used with a different request")
            if out.state == "in_progress":
                return _err(409, "request_in_progress", "A request with this Idempotency-Key is still being processed; retry shortly")
        try:
            agent = await provider.get(agent_id, environment, body.session_id)
            if agent is not None:
                agent = await runtime.active_agent(agent, body.session_id, environment)
        except AgentUnavailable as e:
            if scope:
                await idem.abandon(scope)
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            if scope:
                await idem.abandon(scope)
            return _err(404, "not_found", "Unknown agent")
        try:
            files = await load_attachments(body, agent)
            if isinstance(files, JSONResponse):
                if scope:
                    await idem.abandon(scope)
                return files
            r = await runtime.run(agent, body.session_id, body.message, customer_id, channel=body.channel or ("web" if who.session_id else None), environment=environment,
                                  attachments=files or None)
        except Exception:
            if scope:
                await idem.abandon(scope)
            return _err(500, "internal", "Run failed")
        result = {"reply": r.reply, "status": r.status, "traceId": r.trace_id, "pendingApprovals": r.pending_approvals,
                  "handoffId": r.handoff_id, "agentVersion": agent.version}
        if scope:
            await idem.complete(scope, result)
        return result

    @app.get("/v1/sessions/{session_id}/outbox")
    async def outbox(session_id: str, request: Request, after: int = 0) -> Any:
        who: Identity = request.state.identity
        if who.session_id is not None and session_id != who.session_id:
            await record(request, "auth.denied", f"GET /v1/sessions/{session_id}/outbox", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot read another conversation")
        items = await runtime.outbox.list(session_id, after)
        return {"messages": [{"id": m.id, "kind": m.kind, "createdAt": m.created_at, **m.payload} for m in items]}
