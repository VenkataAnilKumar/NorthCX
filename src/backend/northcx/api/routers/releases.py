"""Routes for agents, versions, the publish checklist, releases, promotion, rollback and environments."""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import PromoteBody, PublishBody, RequestDecisionBody, RollbackBody, VersionBody
from northcx.api.responses import AgentList, Checklist, Environments, LiveAgent, Release, ReleaseList, VersionDetail, VersionDiff, VersionList, VersionPreview
from northcx.mcp_connections import visible_catalog
from northcx.release_requests import ApprovalError, principal
from northcx.catalog import AgentUnavailable
from northcx.spec import AgentSpec, parse_spec, SpecError
from northcx.versions import check_environment, Conflict, diff_specs, GateBlocked, InvalidSpec, NotFound, spec_yaml


def register(app: FastAPI, d: AppDeps) -> None:
    actor = d.actor
    alerts = d.alerts
    need_env = d.need_env
    need_rel = d.need_rel
    provider = d.provider
    record = d.record
    rel_error = d.rel_error
    version_json = d.version_json

    @app.get("/v1/agents", responses={200: {"model": AgentList}})
    async def list_agents(request: Request) -> Any:
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
                            "forcedTopics": [t.name for t in a.forced_handoffs]} for a in live if request.state.identity.allows_agent(a.id)]}

    def release_json(r: Any) -> dict[str, Any]:
        return {"id": r.id, "agentId": r.agent_id, "environment": r.environment, "action": r.action, "version": r.number,
                "versionId": r.version_id, "previousVersion": r.previous_number, "by": r.by, "note": r.note, "gate": r.gate,
                "createdAt": r.created_at, "toBaseline": r.version_id is None}

    @app.post("/v1/agents/{agent_id}/versions", status_code=201, responses={201: {"model": VersionDetail}})
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

    @app.get("/v1/catalog")
    async def catalog() -> Any:
        """The building blocks an editor can offer: tools, guardrails, policies, skills."""
        svc = need_rel()
        return svc if isinstance(svc, JSONResponse) else visible_catalog(svc.registry.describe())

    @app.post("/v1/agents/{agent_id}/versions/preview", responses={200: {"model": VersionPreview}})
    async def preview_version(agent_id: str, body: VersionBody) -> Any:
        """Check a spec without saving it (for editors): problems, digest, and what changed compared with production."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if body.spec is None:
            return _err(400, "bad_request", "Give the spec as 'spec'")
        return await svc.preview(agent_id, body.spec)

    @app.get("/v1/agents/{agent_id}/versions", responses={200: {"model": VersionList}})
    async def list_versions(agent_id: str) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        live_v, _ = await svc.live(agent_id)
        history = await svc.releases.list(agent_id)
        released = {r.number for r in history if r.number is not None}
        return {"versions": [version_json(v, live_v.number if live_v else None, released) for v in await svc.versions.list(agent_id)]}

    @app.get("/v1/agents/{agent_id}/versions/{number}", responses={200: {"model": VersionDetail}})
    async def get_version(agent_id: str, number: int) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        v = await svc.versions.get_number(agent_id, number)
        if v is None:
            return _err(404, "not_found", f"Agent '{agent_id}' has no version {number}")
        live_v, _ = await svc.live(agent_id)
        return version_json(v, live_v.number if live_v else None, {r.number for r in await svc.releases.list(agent_id) if r.number}, True)

    @app.get("/v1/agents/{agent_id}/versions/{number}/checklist", responses={200: {"model": Checklist}})
    async def version_checklist(agent_id: str, number: int, request: Request, environment: str = "production") -> Any:
        """The publish checklist: required checks and notes for releasing this version to an environment."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        if alerts is not None:
            await alerts.refresh()
        firing = [f"{a['rule']} ({a['severity']})" for a in (alerts.status()["active"] if alerts is not None else [])]
        try:
            return await svc.checklist(agent_id, number, environment, environment != "production" or who.can("releases:publish"), firing)
        except (NotFound, ValueError) as e:
            return rel_error(e) if isinstance(e, (NotFound, Conflict)) else _err(400, "bad_request", str(e))

    @app.get("/v1/agents/{agent_id}/versions/{a}/diff/{b}", responses={200: {"model": VersionDiff}})
    async def version_diff(agent_id: str, a: int, b: int) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        va, vb = await svc.versions.get_number(agent_id, a), await svc.versions.get_number(agent_id, b)
        if va is None or vb is None:
            return _err(404, "not_found", f"Agent '{agent_id}' needs both versions {a} and {b}")
        return {"from": a, "to": b, **diff_specs(va.spec, vb.spec)}

    async def hold_for_second_person(svc: Any, request: Request, kind: str, agent_id: str, environment: str, version: int | None, note: str | None, target: str) -> Any:
        """In an environment that needs a second person, a publish or promote becomes a request (202) instead of a release."""
        appr = getattr(svc, "approvals", None)
        if appr is None or not appr.needs_approval(environment):
            return None
        who: Identity = request.state.identity
        if kind == "publish" and await svc.versions.get_number(agent_id, version) is None:
            return _err(404, "not_found", f"Agent '{agent_id}' has no version {version}")  # a request for nothing is refused now, not at approval
        try:
            r = await appr.request(agent_id, kind, environment, version, principal(who), note)
        except ApprovalError as e:
            return _err(e.status, "conflict", str(e))
        await record(request, "release.request", target, environment=environment, requestId=r.id, kind=kind)
        return JSONResponse({**r.to_dict(), "message": f"{environment} needs a second person: ask someone else with the release permission to approve request {r.id}"}, status_code=202)

    @app.get("/v1/release-requests")
    async def list_release_requests(status: str | None = None, agent: str | None = None, limit: int = 100) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        appr = getattr(svc, "approvals", None)
        return {"required": sorted(appr.required) if appr else [], "requests": [r.to_dict() for r in await appr.repo.list(status, agent, max(1, min(limit, 500)))] if appr else []}

    async def decide_request(request_id: str, request: Request, approve: bool, note: str | None) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        appr = getattr(svc, "approvals", None)
        if appr is None:
            return _err(501, "not_configured", "The two-person release rule is not configured (NORTHCX_RELEASE_APPROVALS)")
        who: Identity = request.state.identity
        try:
            r = await appr.claim(request_id, principal(who), approve, note)
        except ApprovalError as e:
            await record(request, "release.approve" if approve else "release.reject", request_id, "denied", reason=str(e))
            return _err(e.status, "conflict" if e.status == 409 else "forbidden" if e.status == 403 else "not_found", str(e))
        if not approve:
            await record(request, "release.reject", f"{r.agent_id} ({r.environment})", requestId=r.id, requestedBy=r.requested_by)
            return r.to_dict()
        by = actor(request, None)
        try:
            if r.kind == "publish":
                rel = await svc.publish(r.agent_id, r.version, by, f"requested by {r.requested_by}" + (f": {r.note}" if r.note else ""), r.environment)
            else:
                rel = await svc.promote(r.agent_id, r.environment, by, f"requested by {r.requested_by}" + (f": {r.note}" if r.note else ""))
        except GateBlocked as e:
            await appr.fail(r.id, "; ".join(e.reasons[:5]))
            await record(request, "release.approve", f"{r.agent_id} ({r.environment})", "blocked", requestId=r.id, reasons=e.reasons[:10])
            return rel_error(e)
        except (NotFound, Conflict) as e:
            await appr.fail(r.id, str(e))
            return rel_error(e)
        await record(request, "release.approve", f"{r.agent_id}@{rel.number} ({r.environment})", requestId=r.id, requestedBy=r.requested_by, gate=rel.gate)
        return {**r.to_dict(), "release": release_json(rel)}

    @app.post("/v1/release-requests/{request_id}/approve")
    async def approve_request(request_id: str, body: RequestDecisionBody, request: Request) -> Any:
        return await decide_request(request_id, request, True, body.note)

    @app.post("/v1/release-requests/{request_id}/reject")
    async def reject_request(request_id: str, body: RequestDecisionBody, request: Request) -> Any:
        return await decide_request(request_id, request, False, body.note)

    @app.post("/v1/release-requests/{request_id}/cancel")
    async def cancel_request(request_id: str, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        appr = getattr(svc, "approvals", None)
        if appr is None:
            return _err(501, "not_configured", "The two-person release rule is not configured (NORTHCX_RELEASE_APPROVALS)")
        try:
            r = await appr.cancel(request_id, principal(request.state.identity))
        except ApprovalError as e:
            return _err(e.status, "conflict" if e.status == 409 else "forbidden" if e.status == 403 else "not_found", str(e))
        await record(request, "release.cancel", f"{r.agent_id} ({r.environment})", requestId=r.id)
        return r.to_dict()

    @app.post("/v1/agents/{agent_id}/releases", responses={200: {"model": Release}})
    async def publish(agent_id: str, body: PublishBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.environment, "releases:publish")) is not None:
            return denied
        target = f"{agent_id}@{body.version}" + ("" if body.environment == "production" else f" ({body.environment})")
        held = await hold_for_second_person(svc, request, "publish", agent_id, body.environment, body.version, body.note, target)
        if held is not None:
            return held
        try:
            rel = await svc.publish(agent_id, body.version, actor(request, body.by), body.note, body.environment)
        except GateBlocked as e:  # an attempt to release something unproven is itself worth recording
            await record(request, "release.publish", target, "blocked", reasons=e.reasons[:10], environment=body.environment)
            return rel_error(e)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.publish", target, previous=rel.previous_number, gate=rel.gate, note=bool(body.note), environment=body.environment)
        return release_json(rel)

    @app.post("/v1/agents/{agent_id}/promote", responses={200: {"model": Release}})
    async def promote(agent_id: str, body: PromoteBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.to, "releases:publish")) is not None:
            return denied
        held = await hold_for_second_person(svc, request, "promote", agent_id, body.to, None, body.note, f"{agent_id} -> {body.to}")
        if held is not None:
            return held
        try:
            rel = await svc.promote(agent_id, body.to, actor(request, body.by), body.note)
        except GateBlocked as e:
            await record(request, "release.promote", f"{agent_id} -> {body.to}", "blocked", reasons=e.reasons[:10], environment=body.to)
            return rel_error(e)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.promote", f"{agent_id}@{rel.number} -> {body.to}", previous=rel.previous_number, gate=rel.gate, environment=body.to)
        return release_json(rel)

    @app.post("/v1/agents/{agent_id}/rollback", responses={200: {"model": Release}})
    async def rollback(agent_id: str, body: RollbackBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.environment, "releases:rollback")) is not None:
            return denied
        try:
            rel = await svc.rollback(agent_id, actor(request, body.by), body.note, body.to_version, body.environment)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.rollback", f"{agent_id}@{rel.number if rel.number else 'spec-file'}",
                     previous=rel.previous_number, note=bool(body.note), environment=body.environment)
        return release_json(rel)

    @app.get("/v1/agents/{agent_id}/releases", responses={200: {"model": ReleaseList}})
    async def release_history(agent_id: str, environment: str = "production") -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            check_environment(environment)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        return {"releases": [release_json(r) for r in await svc.releases.list(agent_id, environment)]}

    @app.get("/v1/agents/{agent_id}/environments", responses={200: {"model": Environments}})
    async def agent_environments(agent_id: str) -> Any:
        """What is live in dev, staging and production, and what each actually serves."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if svc.baseline(agent_id) is None and not await svc.versions.list(agent_id):
            return _err(404, "not_found", f"Unknown agent '{agent_id}'")
        out = {}
        for env, info in (await svc.environments(agent_id)).items():
            v, rel, served = await svc.resolve(agent_id, env)
            out[env] = {"version": info["version"], "release": release_json(info["release"]) if info["release"] else None,
                        "servedFrom": served, "servedVersion": v.number if v else None}
        return {"agentId": agent_id, "strictPromotion": svc.strict_promotion, "environments": out}

    @app.get("/v1/agents/{agent_id}/live", responses={200: {"model": LiveAgent}})
    async def live(agent_id: str, environment: str = "production") -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            v, rel, served = await svc.resolve(agent_id, environment)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        base = svc.baseline(agent_id)
        if v is None and base is None:
            return _err(404, "not_found", f"Unknown agent '{agent_id}'")
        spec = v.spec if v else json.loads(base.canonical())
        return {"agentId": agent_id, "environment": environment, "servedFrom": served, "source": "release" if v else "baseline", "version": v.number if v else None,
                "digest": v.digest if v else base.digest(), "release": release_json(rel) if rel else None,
                "spec": spec, "specYaml": spec_yaml(spec)}
