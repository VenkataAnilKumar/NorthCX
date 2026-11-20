"""Routes for shadow mode: the drafts waiting for a person, the decision, and how often people changed the agent's words."""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import ShadowDecisionBody
from northcx.shadow import STATES, ShadowError, ShadowFlow, draft_json


def register(app: FastAPI, d: AppDeps) -> None:
    runtime, record, agents, actor = d.runtime, d.record, d.agents, d.actor
    flow = ShadowFlow(runtime)

    @app.get("/v1/shadow/drafts")
    async def list_drafts(state: str | None = None, session: str | None = None, limit: int = 100) -> Any:
        """Replies waiting for a person, oldest first. `state` is pending, sent, edited, rejected or expired."""
        if state is not None and state not in STATES:
            return _err(400, "bad_request", f"state must be one of: {', '.join(STATES)}")
        return {"drafts": [draft_json(x) for x in await runtime.shadow.list(state, session_id=session, limit=max(1, min(limit, 500)))]}

    @app.post("/v1/shadow/drafts/{draft_id}/decision")
    async def decide(draft_id: str, body: ShadowDecisionBody, request: Request) -> Any:
        """Send the draft as written, send the person's own text, or send nothing. A send reaches the customer once, through the outbox."""
        try:
            done = await flow.decide(agents, draft_id, body.action, actor(request, body.by), body.text, body.reasons, body.note)
        except ShadowError as e:
            return _err(e.status, "conflict" if e.status == 409 else "bad_request" if e.status == 400 else "not_found", e.message)
        await record(request, f"shadow.{body.action}", draft_id, state=done.state, reasons=",".join(done.reasons), note=bool(done.note), length=len(done.final_text or ""))
        return draft_json(done)

    @app.get("/v1/shadow/summary")
    async def summary(days: float = 30, agent: str | None = None) -> Any:
        """Counts of sent, edited, rejected and expired drafts over the last `days` days, with the agreement ratio and its denominator."""
        return {"days": days, **await flow.summary(time.time() - max(0.04, min(days, 365)) * 86400, agent)}
