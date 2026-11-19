"""Routes for held actions: list, decide and expire approvals."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.decision_teams import note_team
from northcx.api.models import DecisionBody, ExpireBody
from northcx.api.responses import ApprovalDecision, ApprovalExpiry, ApprovalList


def register(app: FastAPI, d: AppDeps) -> None:
    actor = d.actor
    agents = d.agents
    flow = d.flow
    record = d.record
    runtime = d.runtime

    @app.get("/v1/approvals", responses={200: {"model": ApprovalList}})
    async def list_approvals(state: str | None = None) -> Any:
        return {"approvals": [a.__dict__ for a in await runtime.approvals.list(state)]}

    @app.post("/v1/approvals/{approval_id}/decision", responses={200: {"model": ApprovalDecision}})
    async def decide(approval_id: str, body: DecisionBody, request: Request) -> Any:
        """Record the decision, run the action if approved, and continue the conversation. The customer receives the
        outcome through the outbox (and the webhook, if configured)."""
        try:
            res = await flow.resolve(agents, approval_id, body.approved, actor(request, body.by), body.note)
        except KeyError:
            return _err(404, "not_found", "Unknown approval")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        await note_team(runtime, request, "approval", approval_id)
        await record(request, "approval.decide", approval_id, tool=res.approval.tool, approved=body.approved,
                     state=res.approval.state, note=bool(body.note), follow_up=res.run.status if res.run else "none")
        out = dict(res.approval.__dict__)
        out["resume"] = ({"reply": res.run.reply, "status": res.run.status, "traceId": res.run.trace_id}
                         if res.run else {"error": res.error})
        if res.run and res.error:
            out["resume"]["error"] = res.error
        return out

    @app.post("/v1/approvals/expire", responses={200: {"model": ApprovalExpiry}})
    async def expire(body: ExpireBody, request: Request) -> Any:
        done = await flow.expire_stale(agents, body.older_than_seconds)
        await record(request, "approval.expire", "", older_than_seconds=body.older_than_seconds, approvals=[a.id for a in done])
        return {"expired": [a.id for a in done]}
