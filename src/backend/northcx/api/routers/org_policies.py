"""Routes for organization policies: a proven, reviewed, locked rule set that applies to every customer agent (E16)."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import OrgPolicyBody, OrgPolicyDecisionBody, OrgPolicyEditBody, OrgPolicyProveBody
from northcx.org_policies import OrgPolicyError, OrgPolicyService, prove
from northcx.release_requests import principal


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime, actor = d.record, d.runtime, d.actor

    def svc() -> OrgPolicyService | JSONResponse:
        return getattr(runtime, "org_policies", None) or _err(501, "not_configured", "Organization policies are not configured on this server")

    def fail(e: OrgPolicyError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 403: "forbidden", 404: "not_found", 409: "conflict"}.get(e.status, "error"), str(e))

    @app.get("/v1/org-policies")
    async def list_policies() -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        out = []
        for p in await s.repo.list():
            vs = await s.repo.versions(p.id)
            out.append({**p.to_dict(), "versions": [{"version": v.version, "status": v.status, "createdBy": v.created_by, "decidedBy": v.decided_by} for v in vs]})
        return {"policies": out}

    @app.post("/v1/org-policies/prove")
    async def prove_policy(body: OrgPolicyProveBody) -> Any:
        """Run cases against a policy setting without saving anything (for the editor)."""
        try:
            return await prove(body.policy, body.config, body.cases)
        except OrgPolicyError as e:
            return fail(e)

    @app.post("/v1/org-policies", status_code=201)
    async def create_policy(body: OrgPolicyBody, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            p = await s.create(body.name, body.policy, body.config, body.cases, body.applies_to, principal(request.state.identity))
        except OrgPolicyError as e:
            return fail(e)
        await record(request, "org_policy.create", p.name, id=p.id, policy=p.policy, proofPassed=p.proof.get("passed"))
        return p.to_dict()

    @app.put("/v1/org-policies/{policy_id}")
    async def edit_policy(policy_id: str, body: OrgPolicyEditBody, request: Request) -> Any:
        """Edit the draft; if the latest version is in force, this starts a new draft version and the one in force stays in force."""
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            cur = await s.repo.get(policy_id)
            if cur is not None and cur.status in ("active", "rejected", "retired", "superseded"):
                p = await s.revise(policy_id, body.config, body.cases, body.applies_to, principal(request.state.identity))
            else:
                p = await s.edit_draft(policy_id, body.config, body.cases, body.applies_to)
        except OrgPolicyError as e:
            return fail(e)
        await record(request, "org_policy.edit", p.name, id=p.id, version=p.version, proofPassed=p.proof.get("passed"))
        return p.to_dict()

    @app.post("/v1/org-policies/{policy_id}/propose")
    async def propose_policy(policy_id: str, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            p = await s.propose(policy_id, principal(request.state.identity))
        except OrgPolicyError as e:
            return fail(e)
        await record(request, "org_policy.propose", p.name, id=p.id, version=p.version)
        return p.to_dict()

    async def decide(policy_id: str, request: Request, approve: bool, note: str | None) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        who: Identity = request.state.identity
        try:
            p = await s.decide(policy_id, approve, principal(who), note)
        except OrgPolicyError as e:
            await record(request, "org_policy.approve" if approve else "org_policy.reject", policy_id, "denied", reason=str(e))
            return fail(e)
        await record(request, "org_policy.approve" if approve else "org_policy.reject", p.name, id=p.id, version=p.version, proposedBy=p.proposed_by)
        return p.to_dict()

    @app.post("/v1/org-policies/{policy_id}/approve")
    async def approve_policy(policy_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        return await decide(policy_id, request, True, body.note)

    @app.post("/v1/org-policies/{policy_id}/reject")
    async def reject_policy(policy_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        return await decide(policy_id, request, False, body.note)

    @app.post("/v1/org-policies/{policy_id}/retire")
    async def retire_policy(policy_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        """Take a locked policy out of force. Deliberate, and recorded."""
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            p = await s.retire(policy_id, principal(request.state.identity), body.note)
        except OrgPolicyError as e:
            return fail(e)
        await record(request, "org_policy.retire", p.name, id=p.id, version=p.version, note=bool(body.note))
        return p.to_dict()
