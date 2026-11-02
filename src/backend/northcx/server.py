from __future__ import annotations

from typing import Any

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .approval_flow import ApprovalFlow
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
    model_config = {"populate_by_name": True}


class DecisionBody(BaseModel):
    approved: bool
    by: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=1000)


class ResolveBody(BaseModel):
    by: str = Field(min_length=1)
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
    by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class PublishBody(BaseModel):
    version: int = Field(ge=1)
    by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class RollbackBody(BaseModel):
    to_version: int | None = Field(default=None, alias="toVersion", ge=1)
    by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    model_config = {"populate_by_name": True}


class ExpireBody(BaseModel):
    older_than_seconds: float = Field(alias="olderThanSeconds", ge=0)
    model_config = {"populate_by_name": True}


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(runtime: Runtime, traces: TraceRepo, agents: dict[str, Agent], api_key: str | None = None,
               approval_ttl_seconds: float | None = None, simulations: SimulationService | None = None,
               releases: ReleaseService | None = None) -> FastAPI:
    provider = as_provider(agents)
    agents = provider  # everything below resolves agents through the provider
    flow = ApprovalFlow(runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if approval_ttl_seconds:  # periodically expire stale approvals and hand those conversations to a person
            async def sweep() -> None:
                while True:
                    await asyncio.sleep(max(1.0, min(60.0, approval_ttl_seconds / 2)))
                    try:
                        await flow.expire_stale(agents, approval_ttl_seconds)
                    except Exception:  # keep sweeping; a failed pass is retried on the next tick
                        pass

            task = asyncio.create_task(sweep())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="NorthCX", lifespan=lifespan)

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if api_key and request.url.path.startswith("/v1/") and request.headers.get("authorization") != f"Bearer {api_key}":
            return _err(401, "unauthorized", "Missing or invalid API key")
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return _err(400, "bad_request", str(exc.errors()))

    @app.get("/", response_class=HTMLResponse)
    async def widget() -> str:
        return WIDGET_HTML

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/agents/{agent_id}/chat")
    async def chat(agent_id: str, body: ChatBody) -> Any:
        try:
            agent = await provider.get(agent_id)
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            return _err(404, "not_found", "Unknown agent")
        try:
            r = await runtime.run(agent, body.session_id, body.message, body.customer_id)
        except Exception:
            return _err(500, "internal", "Run failed")
        return {"reply": r.reply, "status": r.status, "traceId": r.trace_id, "pendingApprovals": r.pending_approvals,
                "handoffId": r.handoff_id, "agentVersion": agent.version}

    @app.get("/v1/traces/{trace_id}")
    async def get_trace(trace_id: str) -> Any:
        t = await traces.get(trace_id)
        return t.to_dict() if t else _err(404, "not_found", "Unknown trace")

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
                            "forcedTopics": [t.name for t in a.forced_handoffs]} for a in live]}

    @app.get("/v1/approvals")
    async def list_approvals(state: str | None = None) -> Any:
        return {"approvals": [a.__dict__ for a in await runtime.approvals.list(state)]}

    @app.post("/v1/approvals/{approval_id}/decision")
    async def decide(approval_id: str, body: DecisionBody) -> Any:
        """Record the decision, run the action if approved, and continue the conversation. The customer receives the
        outcome through the outbox (and the webhook, if configured)."""
        try:
            res = await flow.resolve(agents, approval_id, body.approved, body.by, body.note)
        except KeyError:
            return _err(404, "not_found", "Unknown approval")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        out = dict(res.approval.__dict__)
        out["resume"] = ({"reply": res.run.reply, "status": res.run.status, "traceId": res.run.trace_id}
                         if res.run else {"error": res.error})
        if res.run and res.error:
            out["resume"]["error"] = res.error
        return out

    @app.post("/v1/approvals/expire")
    async def expire(body: ExpireBody) -> Any:
        done = await flow.expire_stale(agents, body.older_than_seconds)
        return {"expired": [a.id for a in done]}

    def handoff_json(h: Any, full: bool = False) -> dict[str, Any]:
        out = {"id": h.id, "sessionId": h.session_id, "traceId": h.trace_id, "agentId": h.agent_id, "customerId": h.customer_id,
               "trigger": h.trigger, "reason": h.reason, "topics": h.topics, "state": h.state, "createdAt": h.created_at,
               "resolvedBy": h.resolved_by, "resolvedAt": h.resolved_at, "note": h.note, "summary": h.package.get("summary")}
        if full:
            out["package"] = h.package
        return out

    @app.get("/v1/handoffs")
    async def list_handoffs(state: str | None = None, sessionId: str | None = None, limit: int = 200) -> Any:
        items = await runtime.handoffs.list(state, sessionId, max(1, min(limit, 1000)))
        return {"handoffs": [handoff_json(h) for h in items]}

    @app.get("/v1/handoffs/{handoff_id}")
    async def get_handoff(handoff_id: str) -> Any:
        h = await runtime.handoffs.get(handoff_id)
        return handoff_json(h, full=True) if h else _err(404, "not_found", "Unknown handoff")

    @app.post("/v1/handoffs/{handoff_id}/resolve")
    async def resolve_handoff(handoff_id: str, body: ResolveBody) -> Any:
        try:
            return handoff_json(await runtime.handoffs.resolve(handoff_id, body.by, body.note))
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
    async def sim_run(body: SimRunBody) -> Any:
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
    async def create_version(agent_id: str, body: VersionBody) -> Any:
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
            v = await svc.create_version(agent_id, spec, body.by, body.note)
        except (SpecError, InvalidSpec, Conflict, ValueError) as e:
            return rel_error(e if isinstance(e, (InvalidSpec, Conflict)) else InvalidSpec(str(e)))
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
    async def publish(agent_id: str, body: PublishBody) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            return release_json(await svc.publish(agent_id, body.version, body.by, body.note))
        except (NotFound, Conflict, GateBlocked) as e:
            return rel_error(e)

    @app.post("/v1/agents/{agent_id}/rollback")
    async def rollback(agent_id: str, body: RollbackBody) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            return release_json(await svc.rollback(agent_id, body.by, body.note, body.to_version))
        except (NotFound, Conflict) as e:
            return rel_error(e)

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
    async def outbox(session_id: str, after: int = 0) -> Any:
        items = await runtime.outbox.list(session_id, after)
        return {"messages": [{"id": m.id, "kind": m.kind, "createdAt": m.created_at, **m.payload} for m in items]}

    return app
