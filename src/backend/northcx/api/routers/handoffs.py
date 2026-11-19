"""Routes for hand-offs to people: queue, detail, suggestions, replies, resolution and routing."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import ReplyBody, ResolveBody
from northcx.api.responses import Handoff, HandoffDetail, HandoffInbox, HandoffList, HandoffReply
from northcx.assist import AssistError
from northcx.decision_teams import note_team
from northcx.handoffs import PERSON_PREFIX, return_note

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    actor = d.actor
    record = d.record
    runtime = d.runtime
    too_many = d.too_many

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

    @app.get("/v1/handoffs", responses={200: {"model": HandoffList}})
    async def list_handoffs(state: str | None = None, sessionId: str | None = None, limit: int = 200, queue: str | None = None) -> Any:
        items = await runtime.handoffs.list(state, sessionId, max(1, min(limit, 1000)), queue)
        return {"handoffs": [handoff_json(h) for h in items]}

    @app.get("/v1/handoffs/{handoff_id}/inbox", responses={200: {"model": HandoffInbox}})
    async def handoff_inbox(handoff_id: str) -> Any:
        """Where this hand-off has been sent (helpdesk reference, attempts, last error)."""
        if await runtime.handoffs.get(handoff_id) is None:
            return _err(404, "not_found", "Unknown handoff")
        events = await runtime.inbox.repo.for_handoff(handoff_id) if runtime.inbox is not None else []
        return {"configured": runtime.inbox is not None, "deliveries": [e.to_dict() for e in events]}

    @app.get("/v1/handoffs/{handoff_id}", responses={200: {"model": HandoffDetail}})
    async def get_handoff(handoff_id: str) -> Any:
        h = await runtime.handoffs.get(handoff_id)
        return handoff_json(h, full=True) if h else _err(404, "not_found", "Unknown handoff")

    @app.post("/v1/handoffs/{handoff_id}/resolve", responses={200: {"model": Handoff}})
    async def resolve_handoff(handoff_id: str, body: ResolveBody, request: Request) -> Any:
        try:
            who = actor(request, body.by)
            done = await runtime.handoffs.resolve(handoff_id, who, body.note)
            if body.returnToAgent:  # the agent is told what happened, so it can carry on from where the person left off
                msgs = await runtime.store.load_messages(done.session_id)
                msgs.append({"role": "user", "content": return_note(who, runtime.secrets.redact_text(body.note or ""))})
                await runtime.store.save_messages(done.session_id, msgs)
            if runtime.inbox is not None:
                try:
                    await runtime.inbox.enqueue(done, "resolved")
                except Exception:
                    log.exception("could not queue the resolution for the inbox")
            await note_team(runtime, request, "handoff", handoff_id)
            await record(request, "handoff.resolve", handoff_id, trigger=done.trigger, note=bool(body.note), returned=body.returnToAgent)
            return handoff_json(done)
        except KeyError:
            return _err(404, "not_found", "Unknown handoff")
        except ValueError as e:
            return _err(409, "conflict", str(e))

    @app.post("/v1/handoffs/{handoff_id}/reply", responses={200: {"model": HandoffReply}})
    async def handoff_reply(handoff_id: str, body: ReplyBody, request: Request) -> Any:
        """A person's message to the customer. It joins the conversation and reaches the customer through the outbox (web chat and apps poll or are
        pushed it); conversations on email and text are answered from the helpdesk instead."""
        h = await runtime.handoffs.get(handoff_id)
        if h is None:
            return _err(404, "not_found", "Unknown handoff")
        if h.state != "open":
            return _err(409, "conflict", "This hand-off is already resolved")
        who = actor(request, body.by)
        text = runtime.secrets.redact_text(body.text.strip())
        msgs = await runtime.store.load_messages(h.session_id)
        msgs.append({"role": "assistant", "content": f"{PERSON_PREFIX} {text}"})
        await runtime.store.save_messages(h.session_id, msgs)
        m = await runtime.outbox.publish(h.session_id, "person_reply", {"reply": text, "by": who, "handoffId": h.id})
        await record(request, "handoff.reply", handoff_id, length=len(text))
        return {"sent": True, "messageId": m.id}

    @app.post("/v1/handoffs/{handoff_id}/assist")
    async def handoff_assist(handoff_id: str, request: Request) -> Any:
        """Draft suggestions (reply, next steps, key facts, cautions) for the person handling this hand-off. Suggestions only: nothing is sent."""
        if runtime.assist is None:
            return _err(501, "not_configured", "Agent assist is switched off on this server")
        h = await runtime.handoffs.get(handoff_id)
        if h is None:
            return _err(404, "not_found", "Unknown handoff")
        who: Identity = request.state.identity
        if not (await access.limiter.hit(f"assist:{who.key_id or 'open'}", 20))[0]:
            return too_many(60, "assist requests")
        try:
            out = runtime.secrets.redact(await runtime.assist.suggest(runtime.secrets.redact(h.package)))
        except AssistError as e:
            return _err(422, "unusable_suggestions", str(e))
        except Exception:
            log.exception("assist failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await runtime.handoffs.set_package_field(h.id, "assist", out)
        await record(request, "handoff.assist", handoff_id)
        return {"assist": out}
