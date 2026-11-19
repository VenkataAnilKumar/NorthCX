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
from northcx.api import agui
from northcx.api.models import AguiRunBody, ChatBody
from northcx.api.responses import Attachment, Attachments, ChatResponse, Outbox
from northcx.attachments import accept as accept_attachment, AttachmentError, check_accepted, MAX_BYTES
from northcx.catalog import AgentUnavailable
from northcx.decision_teams import note_team
from northcx.idempotency import request_hash, scope_hash, valid_key
from northcx.privacy import customer_ref


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    actor, agents, flow = d.actor, d.agents, d.flow
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
        who0: Identity = request.state.identity
        if not who0.allows_env(body.environment or "production"):
            await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", environment=body.environment or "production")
            return _err(403, "forbidden", f"This key is limited to the {', '.join(who0.scope_envs or ())} environment(s)")
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

    @app.put("/v1/sessions/{session_id}/attachments", status_code=201, responses={201: {"model": Attachment}})
    async def upload_attachment(session_id: str, request: Request, filename: str | None = None) -> Any:
        """Upload one file (the request body is the file itself). It is identified by its content, size-limited, optionally scanned, and kept with the conversation."""
        who: Identity = request.state.identity
        if who.session_id is not None and who.session_id != session_id:
            await record(request, "auth.denied", f"PUT /v1/sessions/{session_id}/attachments", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot be used for that conversation")
        if not (await access.limiter.hit(f"upload:{session_id}", 20))[0]:
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

    @app.get("/v1/sessions/{session_id}/attachments", responses={200: {"model": Attachments}})
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

    async def open_run(agent_id: str, body: ChatBody, request: Request, path: str) -> JSONResponse | tuple[Any, Any]:
        """The checks every streamed run starts with, then the run itself: returns an error answer, or the agent and an async
        iterator of ("progress", event), ("result", RunResult) or ("error", payload). The customer's message is always handled
        and saved, even if the client disconnects."""
        who: Identity = request.state.identity
        customer_id = body.customer_id
        if request.headers.get("idempotency-key"):
            return _err(400, "unsupported", "Idempotency-Key is not supported on the streaming endpoints; use /chat")
        if who.session_id is not None:
            if body.session_id != who.session_id or (who.agent and agent_id != who.agent):
                await record(request, "auth.denied", f"POST {path}", "denied", reason="outside the token's scope")
                return _err(403, "forbidden", "This chat token cannot be used for that conversation or agent")
            customer_id = who.customer_id
        if limits:
            ok, retry = await access.limiter.hit(f"session:{body.session_id}", limits.chat_per_session_per_minute)
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

        async def items() -> Any:
            task = asyncio.create_task(work())
            try:
                while True:
                    kind, payload = await queue.get()
                    yield kind, payload
                    if kind != "progress":
                        return
            finally:
                if not task.done():
                    await task

        return agent, items()

    @app.post("/v1/agents/{agent_id}/chat/stream")
    async def chat_stream(agent_id: str, body: ChatBody, request: Request) -> Any:
        """Server-sent events: `progress` while tools run, then the reply in `delta` pieces, then `done`.

        The reply is released only after every supervisor has approved it, so the customer never sees text that a
        check could still reject; `delta` pieces are the approved reply, delivered progressively.
        """
        opened = await open_run(agent_id, body, request, f"/v1/agents/{agent_id}/chat/stream")
        if isinstance(opened, JSONResponse):
            return opened
        agent, items = opened

        def sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        async def events() -> Any:
            yield sse("started", {"agent": agent_id})
            async for kind, payload in items:
                if kind == "progress":
                    yield sse("progress", payload)
                elif kind == "error":
                    yield sse("error", payload)
                else:
                    for piece in _pieces(payload.reply):
                        yield sse("delta", {"text": piece})
                    yield sse("done", {"reply": payload.reply, "status": payload.status, "traceId": payload.trace_id,
                                       "pendingApprovals": payload.pending_approvals, "handoffId": payload.handoff_id,
                                       "agentVersion": agent.version})

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/v1/agents/{agent_id}/agui")
    async def agui_run(agent_id: str, body: AguiRunBody, request: Request) -> Any:
        """AG-UI events for one run: the same run as `chat/stream`. A held action ends the run with an `interrupt` outcome;
        staff answer it by sending the next run with `resume`, which makes the same decision as `POST /v1/approvals/{id}/decision`."""
        who: Identity = request.state.identity
        headers = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        if body.resume:
            return await agui_resume(agent_id, body, request, who, headers)
        said = next((m.content for m in reversed(body.messages) if m.role == "user" and isinstance(m.content, str) and m.content.strip()), None)
        if said is None:
            return _err(400, "bad_request", "Send a user message (messages with a user entry that has text) or a resume answer")
        if len(said) > 8000:
            return _err(400, "bad_request", "The message is longer than 8000 characters")
        opened = await open_run(agent_id, ChatBody(sessionId=body.thread_id, message=said), request, f"/v1/agents/{agent_id}/agui")
        if isinstance(opened, JSONResponse):
            return opened
        agent, items = opened

        async def events() -> Any:
            yield agui.sse(agui.started(body.thread_id, body.run_id))
            async for kind, payload in items:
                if kind == "progress":
                    if payload.get("type") == "tool":
                        for e in agui.tool_call(payload["name"]):
                            yield agui.sse(e)
                elif kind == "error":
                    yield agui.sse(agui.error(payload["message"], payload["code"]))
                else:
                    for e in agui.message(payload.reply):
                        yield agui.sse(e)
                    yield agui.sse(agui.finished(body.thread_id, body.run_id, payload.pending_approvals,
                                                 {"status": payload.status, "traceId": payload.trace_id, "handoffId": payload.handoff_id, "agentVersion": agent.version}))

        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    async def agui_resume(agent_id: str, body: AguiRunBody, request: Request, who: Identity, headers: dict[str, str]) -> Any:
        if body.messages and any(m.role == "user" for m in body.messages):
            return _err(400, "bad_request", "A run is either a message or an answer to what is waiting; send one of them")
        if who.session_id is not None or not who.can("approvals:decide"):
            await record(request, "auth.denied", f"POST /v1/agents/{agent_id}/agui", "denied", permission="approvals:decide")
            return _err(403, "forbidden", "Only a person who may decide approvals can answer what is waiting (needs approvals:decide)")
        if request.headers.get("idempotency-key"):
            return _err(400, "unsupported", "Idempotency-Key is not supported on the streaming endpoints; a decision can be made once")
        open_ = [a for a in await runtime.approvals.list("pending") if a.session_id == body.thread_id and a.agent_id == agent_id]
        if not open_:
            return _err(409, "conflict", "Nothing is waiting for an answer in this conversation")
        answers = [a.interrupt_id for a in body.resume]
        wanted = {a.id for a in open_}
        unknown = sorted(set(answers) - wanted)
        if unknown:
            return _err(400, "bad_request", f"Not waiting for an answer: {', '.join(unknown)}")
        if len(set(answers)) != len(answers):
            return _err(400, "bad_request", "Each waiting action is answered once")
        missing = sorted(wanted - set(answers))
        if missing:
            return _err(400, "bad_request", f"Answer every waiting action in one run; still waiting: {', '.join(missing)}")

        async def events() -> Any:
            yield agui.sse(agui.started(body.thread_id, body.run_id))
            last = None
            for ans in body.resume:
                try:
                    res = await flow.resolve(agents, ans.interrupt_id, ans.approved, actor(request, None), ans.note)
                except (KeyError, ValueError) as e:
                    yield agui.sse(agui.error(str(e.args[0]) if e.args else "That action was already decided", "conflict"))
                    return
                await note_team(runtime, request, "approval", ans.interrupt_id)
                await record(request, "approval.decide", ans.interrupt_id, tool=res.approval.tool, approved=ans.approved, state=res.approval.state, note=bool(ans.note),
                             follow_up=res.run.status if res.run else "none")
                if res.run is not None:
                    for e in agui.message(res.run.reply):
                        yield agui.sse(e)
                    last = res.run
                elif res.error:
                    yield agui.sse(agui.error(res.error, "follow_up_failed"))
                    return
            result = {"status": last.status, "traceId": last.trace_id, "handoffId": last.handoff_id} if last else {"status": "decided"}
            yield agui.sse(agui.finished(body.thread_id, body.run_id, last.pending_approvals if last else [], result))

        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    @app.post("/v1/agents/{agent_id}/chat", responses={200: {"model": ChatResponse}})
    async def chat(agent_id: str, body: ChatBody, request: Request) -> Any:
        who: Identity = request.state.identity
        customer_id = body.customer_id
        if who.session_id is not None:  # a chat token: one conversation, one customer, one agent
            if body.session_id != who.session_id or (who.agent and agent_id != who.agent):
                await record(request, "auth.denied", f"POST /v1/agents/{agent_id}/chat", "denied", reason="outside the token's scope")
                return _err(403, "forbidden", "This chat token cannot be used for that conversation or agent")
            customer_id = who.customer_id  # set by the company's server; the customer cannot choose it
        if limits:
            ok, retry = await access.limiter.hit(f"session:{body.session_id}", limits.chat_per_session_per_minute)
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

    @app.get("/v1/sessions/{session_id}/outbox", responses={200: {"model": Outbox}})
    async def outbox(session_id: str, request: Request, after: int = 0) -> Any:
        who: Identity = request.state.identity
        if who.session_id is not None and session_id != who.session_id:
            await record(request, "auth.denied", f"GET /v1/sessions/{session_id}/outbox", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot read another conversation")
        items = await runtime.outbox.list(session_id, after)
        return {"messages": [{"id": m.id, "kind": m.kind, "createdAt": m.created_at, **m.payload} for m in items]}
