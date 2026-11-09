"""Routes for the staff Workspace: the Pilot chat (E5)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import WorkspaceChatBody
from northcx.release_requests import principal
from northcx.workspace import WorkspaceService


def register(app: FastAPI, d: AppDeps) -> None:
    access, limits, record, runtime, too_many = d.access, d.limits, d.record, d.runtime, d.too_many
    ws = WorkspaceService(runtime, d.traces, d.kb, d.insight, d.tag_repo, d.audit, d.review_repo)
    app.state.workspace = ws

    def person(who: Identity) -> tuple[str, str]:
        """(the person's stable id for staff data, short form). A single-sign-on person is one person across sessions."""
        h = hashlib.sha256(principal(who).encode()).hexdigest()[:16]
        return f"staff:{h}", h

    def staff_only(who: Identity) -> JSONResponse | None:
        if who.session_id is not None or who.role in ("channel", "customer_session"):
            return _err(403, "forbidden", "The Workspace is for signed-in staff")
        return None

    async def prepare(request: Request, body: WorkspaceChatBody) -> tuple[Any, ...] | JSONResponse:
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        who_id, h = person(who)
        if limits:
            ok, retry = await access.limiter.hit(f"workspace:{h}", limits.chat_per_session_per_minute)
            if not ok:
                return too_many(retry, "messages")
        chat_id = body.chat_id or uuid.uuid4().hex[:16]
        agent = ws.agent(who, body.style)
        if not agent.tools:
            return _err(403, "forbidden", "Your role has no tools to give the assistant")
        return who, who_id, f"{who_id}:{chat_id}", chat_id, agent

    def sources_of(trace: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for e in trace.events:
            if e.type == "tool_result" and e.data.get("name") == "search_knowledge":
                for r in (e.data.get("output") or {}).get("results", []):
                    out.append({"title": r.get("title"), "url": r.get("url"), "section": r.get("section"), "updated": r.get("updated"), "stale": bool(r.get("stale"))})
        return out

    @app.post("/v1/workspace/chat")
    async def workspace_chat(body: WorkspaceChatBody, request: Request) -> Any:
        prep = await prepare(request, body)
        if isinstance(prep, JSONResponse):
            return prep
        who, who_id, session_id, chat_id, agent = prep
        r = await runtime.run(agent, session_id, body.message, who_id, channel="workspace", environment="workspace", actor=who)
        await record(request, "workspace.chat", chat_id, style=body.style, status=r.status)
        return {"chatId": chat_id, "reply": r.reply, "status": r.status, "traceId": r.trace_id, "sources": sources_of(r.trace),
                "tools": [t.name for t in agent.tools]}

    @app.post("/v1/workspace/chat/stream")
    async def workspace_chat_stream(body: WorkspaceChatBody, request: Request) -> Any:
        prep = await prepare(request, body)
        if isinstance(prep, JSONResponse):
            return prep
        who, who_id, session_id, chat_id, agent = prep
        queue: asyncio.Queue = asyncio.Queue()

        async def work() -> None:
            try:
                r = await runtime.run(agent, session_id, body.message, who_id, channel="workspace", environment="workspace", actor=who, progress=lambda e: queue.put_nowait(("progress", e)))
                queue.put_nowait(("result", r))
            except Exception:
                queue.put_nowait(("error", {"code": "internal", "message": "Run failed"}))

        def sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        async def events() -> Any:
            task = asyncio.create_task(work())
            try:
                yield sse("started", {"chatId": chat_id, "style": body.style})
                while True:
                    kind, payload = await queue.get()
                    if kind == "progress":
                        yield sse("progress", payload)
                    elif kind == "error":
                        yield sse("error", payload)
                        return
                    else:
                        yield sse("done", {"chatId": chat_id, "reply": payload.reply, "status": payload.status, "traceId": payload.trace_id, "sources": sources_of(payload.trace)})
                        await record(request, "workspace.chat", chat_id, style=body.style, status=payload.status)
                        return
            finally:
                if not task.done():
                    await task  # the question is always handled and saved, even if the browser goes away

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
