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
from northcx.api.models import AnswersBody, NoteBody, PlanBody, TaskBody, WorkspaceChatBody
from northcx.release_requests import principal
from northcx.staff_search import ConversationProvider, HandoffProvider, KnowledgeProvider, SearchService
from northcx.tasks import TaskError, TaskService
from northcx.workspace import WorkspaceService


def register(app: FastAPI, d: AppDeps) -> None:
    access, limits, record, runtime, too_many = d.access, d.limits, d.record, d.runtime, d.too_many
    ws = WorkspaceService(runtime, d.traces, d.kb, d.insight, d.tag_repo, d.audit, d.review_repo, policy=getattr(runtime, "workspace_policy", None))
    app.state.workspace = ws
    tasks = TaskService(getattr(runtime, "task_repo", None), ws)
    search = SearchService(([KnowledgeProvider(d.kb)] if d.kb is not None else []) + [ConversationProvider(d.insight, d.tag_repo), HandoffProvider(runtime.handoffs)])
    app.state.staff_search = search
    app.state.tasks = tasks

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
        use_memory = body.memory and not body.temporary
        r = await runtime.run(agent, session_id, body.message, who_id if use_memory else None, channel="workspace", environment="workspace", actor=who)
        sources = sources_of(r.trace)
        if body.temporary:  # a temporary chat keeps nothing: history, traces and anything attached to them are erased now
            await runtime.privacy.erase_session(session_id)
        await record(request, "workspace.chat", chat_id, style=body.style, status=r.status, temporary=body.temporary, memory=use_memory)
        return {"chatId": chat_id, "reply": r.reply, "status": r.status, "traceId": None if body.temporary else r.trace_id, "sources": sources,
                "tools": [t.name for t in agent.tools], "temporary": body.temporary, "memory": use_memory}

    @app.post("/v1/workspace/chat/stream")
    async def workspace_chat_stream(body: WorkspaceChatBody, request: Request) -> Any:
        prep = await prepare(request, body)
        if isinstance(prep, JSONResponse):
            return prep
        who, who_id, session_id, chat_id, agent = prep
        queue: asyncio.Queue = asyncio.Queue()

        async def work() -> None:
            try:
                r = await runtime.run(agent, session_id, body.message, who_id if (body.memory and not body.temporary) else None, channel="workspace", environment="workspace",
                                      actor=who, progress=lambda e: queue.put_nowait(("progress", e)))
                if body.temporary:
                    await runtime.privacy.erase_session(session_id)
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

    # ---------------- tasks (Research) ----------------
    async def mine(request: Request, task_id: str | None = None) -> tuple[Identity, str, Any] | JSONResponse:
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        who_id, _ = person(who)
        task = None
        if task_id is not None:
            try:
                task = await tasks.settle(await tasks.own(task_id, who_id))
            except TaskError as e:
                return _err(e.status, "not_found", str(e))
        return who, who_id, task

    def failed(e: TaskError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 404: "not_found", 409: "conflict"}.get(e.status, "error"), str(e))

    @app.post("/v1/workspace/tasks", status_code=201)
    async def create_task(body: TaskBody, request: Request) -> Any:
        m = await mine(request)
        if isinstance(m, JSONResponse):
            return m
        who, who_id, _ = m
        if not ws.agent(who, "research").tools:
            return _err(403, "forbidden", "Your role has no tools to give the assistant")
        try:
            t = await tasks.create(who_id, body.prompt, body.style)
        except TaskError as e:
            return failed(e)
        await record(request, "workspace.task.create", t.id, style=t.style, status=t.status)
        return t.to_dict()

    @app.get("/v1/workspace/tasks")
    async def list_tasks(request: Request, limit: int = 50) -> Any:
        m = await mine(request)
        if isinstance(m, JSONResponse):
            return m
        _, who_id, _ = m
        return {"tasks": [(await tasks.settle(t)).to_dict() for t in await tasks.repo.list(who_id, max(1, min(limit, 200)))]}

    @app.get("/v1/workspace/tasks/{task_id}")
    async def get_task(task_id: str, request: Request) -> Any:
        m = await mine(request, task_id)
        return m if isinstance(m, JSONResponse) else m[2].to_dict()

    @app.post("/v1/workspace/tasks/{task_id}/answers")
    async def answer_task(task_id: str, body: AnswersBody, request: Request) -> Any:
        m = await mine(request, task_id)
        if isinstance(m, JSONResponse):
            return m
        try:
            t = await tasks.answer(m[2], body.answers)
        except TaskError as e:
            return failed(e)
        await record(request, "workspace.task.plan", t.id, steps=len(t.plan))
        return t.to_dict()

    @app.put("/v1/workspace/tasks/{task_id}/plan")
    async def edit_plan(task_id: str, body: PlanBody, request: Request) -> Any:
        m = await mine(request, task_id)
        if isinstance(m, JSONResponse):
            return m
        try:
            t = await tasks.edit_plan(m[2], body.steps)
        except TaskError as e:
            return failed(e)
        await record(request, "workspace.task.edit", t.id, steps=len(t.plan))
        return t.to_dict()

    @app.post("/v1/workspace/tasks/{task_id}/approve")
    async def approve_task(task_id: str, request: Request) -> Any:
        m = await mine(request, task_id)
        if isinstance(m, JSONResponse):
            return m
        who, who_id, task = m
        try:
            t = await tasks.approve(task, who, f"{who_id}:task:{task.id}", who_id)
        except TaskError as e:
            return failed(e)
        await record(request, "workspace.task.approve", t.id, steps=len(t.plan))
        return t.to_dict()

    async def control(task_id: str, request: Request, action: str) -> Any:
        m = await mine(request, task_id)
        if isinstance(m, JSONResponse):
            return m
        try:
            t = await tasks.control(m[2], action)
        except TaskError as e:
            return failed(e)
        await record(request, f"workspace.task.{action}", t.id)
        return t.to_dict()

    @app.post("/v1/workspace/tasks/{task_id}/pause")
    async def pause_task(task_id: str, request: Request) -> Any:
        return await control(task_id, request, "pause")

    @app.post("/v1/workspace/tasks/{task_id}/stop")
    async def stop_task(task_id: str, request: Request) -> Any:
        return await control(task_id, request, "stop")

    @app.delete("/v1/workspace/tasks/{task_id}")
    async def delete_task(task_id: str, request: Request) -> Any:
        m = await mine(request, task_id)
        if isinstance(m, JSONResponse):
            return m
        await tasks.delete(m[2])
        await record(request, "workspace.task.delete", task_id)
        return {"deleted": True}

    # ---------------- search ----------------
    @app.get("/v1/workspace/search")
    async def workspace_search(request: Request, q: str = "", limit: int = 20) -> Any:
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        if len(q) > 200:
            return _err(400, "bad_request", "The search can be at most 200 characters")
        out = await search.search(who, q, max(1, min(limit, 50)))
        await record(request, "workspace.search", q[:80], results=len(out["results"]))
        return out

    # ---------------- memory (the person's own working notes) ----------------
    def memory_service() -> Any:
        return runtime.memories

    @app.get("/v1/workspace/memory")
    async def list_memory(request: Request) -> Any:
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        if memory_service() is None:
            return _err(501, "not_configured", "Memory is switched off on this server")
        who_id, _ = person(who)
        return {"notes": [{"id": m.id, "note": m.text, "createdAt": m.created_at, "updatedAt": m.updated_at} for m in await memory_service().list(who_id)]}

    @app.post("/v1/workspace/memory", status_code=201)
    async def add_memory(body: NoteBody, request: Request) -> Any:
        from northcx.memory import MemoryRejected
        from northcx.workspace import screen_staff_note
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        if memory_service() is None:
            return _err(501, "not_configured", "Memory is switched off on this server")
        who_id, _ = person(who)
        try:
            m, new = await memory_service().remember(who_id, screen_staff_note(body.note), None)
        except MemoryRejected as e:
            return _err(400, "bad_request", str(e))
        await record(request, "workspace.memory.add", "own", new=new)
        return {"id": m.id, "note": m.text, "new": new}

    @app.put("/v1/workspace/memory/{note_id}")
    async def edit_memory(note_id: str, body: NoteBody, request: Request) -> Any:
        from northcx.memory import MemoryRejected
        from northcx.workspace import screen_staff_note
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        if memory_service() is None:
            return _err(501, "not_configured", "Memory is switched off on this server")
        who_id, _ = person(who)
        try:
            clean = screen_staff_note(body.note)             # screened first, so a rejected edit leaves the old note alone
        except MemoryRejected as e:
            return _err(400, "bad_request", str(e))
        if not await memory_service().forget(who_id, note_id):
            return _err(404, "not_found", "Unknown note")
        m, _ = await memory_service().remember(who_id, clean, None)
        await record(request, "workspace.memory.edit", "own")
        return {"id": m.id, "note": m.text}

    @app.delete("/v1/workspace/memory/{note_id}")
    async def forget_memory(note_id: str, request: Request) -> Any:
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        if memory_service() is None:
            return _err(501, "not_configured", "Memory is switched off on this server")
        who_id, _ = person(who)
        if not await memory_service().forget(who_id, note_id):
            return _err(404, "not_found", "Unknown note")
        await record(request, "workspace.memory.delete", "own")
        return {"deleted": True}

    @app.delete("/v1/workspace/memory")
    async def erase_memory(request: Request) -> Any:
        who: Identity = request.state.identity
        if (refused := staff_only(who)) is not None:
            return refused
        if memory_service() is None:
            return _err(501, "not_configured", "Memory is switched off on this server")
        who_id, _ = person(who)
        n = await memory_service().forget_all(who_id)
        await record(request, "workspace.memory.erase", "own", removed=n)
        return {"removed": n}
