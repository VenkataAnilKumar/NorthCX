"""Routes for scenarios, simulation runs and the release gate."""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import yaml

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import QualifyBody, ScenarioBody, SimRunBody
from northcx.privacy import customer_ref
from northcx.regression import scenario_from_traces
from northcx.simulation import Busy, SimulationService
from northcx.simulation.managed import parse_definition
from northcx.simulation.scenario import ScenarioError
from northcx.spec import AgentSpec


def register(app: FastAPI, d: AppDeps) -> None:
    actor = d.actor
    record = d.record
    releases = d.releases
    simulations = d.simulations
    runtime = d.runtime
    traces = d.traces

    @app.get("/v1/sessions/{session_id}/scenario-draft")
    async def scenario_draft(session_id: str, request: Request) -> Any:
        """A scenario drafted from a real conversation (personal data masked), for a person to review and add to the scenario files."""
        found = [t for t in [await traces.get(s.id) for s in await traces.summaries(session_id, 200)] if t is not None]
        try:
            d = scenario_from_traces(found, session_id)
        except ScenarioError as e:
            return _err(404 if not found else 400, "not_found" if not found else "bad_request", str(e))
        await record(request, "scenario.draft", customer_ref(session_id), turns=len(d.scenario["turns"]))
        return {"yaml": d.yaml, "scenario": d.scenario, "warnings": d.warnings}

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
        files = {s.name for s in sim.scenarios}
        return {"modes": sim.modes, "managedAvailable": sim.managed is not None, "scenarios": [
            {"name": s.name, "agent": s.agent, "required": s.required, "description": s.description, "steps": len(s.turns), "tags": s.tags,
             "judge": s.judge is not None, "digest": s.digest(), "source": "file" if s.name in files else "managed", "editable": s.name not in files and sim.managed is not None}
            for s in await sim.all_scenarios()]}

    def scenario_input(body: ScenarioBody) -> tuple[dict[str, Any], Any] | JSONResponse:
        if (body.yaml is None) == (body.scenario is None):
            return _err(400, "bad_request", "Give exactly one of 'yaml' or 'scenario'")
        try:
            return parse_definition(body.yaml if body.yaml is not None else body.scenario)
        except ScenarioError as e:
            return _err(400, "invalid_scenario", str(e))

    async def need_require(request: Request, what: str) -> JSONResponse | None:
        """Required scenarios decide what may be released, so changing which ones are required needs the release permission."""
        who: Identity = request.state.identity
        if not who.can("scenarios:require"):
            await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", permission="scenarios:require")
            return _err(403, "forbidden", f"The '{who.role}' role cannot {what} a required scenario (needs scenarios:require)")
        return None

    @app.post("/v1/simulations/scenarios/validate")
    async def validate_scenario(body: ScenarioBody) -> Any:
        """Check a scenario without saving it."""
        parsed = scenario_input(body)
        if isinstance(parsed, JSONResponse):
            return {"valid": False, "problems": [json.loads(parsed.body)["error"]["message"]]}
        definition, sc = parsed
        return {"valid": True, "problems": [], "name": sc.name, "agent": sc.agent, "required": sc.required, "digest": sc.digest(), "steps": len(sc.turns)}

    @app.get("/v1/simulations/scenarios/{name}")
    async def get_scenario(name: str) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        sc = next((s for s in await sim.all_scenarios() if s.name == name), None)
        if sc is None:
            return _err(404, "not_found", "Unknown scenario")
        is_file = any(s.name == name for s in sim.scenarios)
        m = None if is_file or sim.managed is None else await sim.managed.get(name)
        definition = m.definition if m else json.loads(sc.model_dump_json(exclude={"source"}, exclude_defaults=True))
        return {"name": name, "source": "file" if is_file else "managed", "editable": m is not None, "required": sc.required, "digest": sc.digest(),
                "definition": definition, "yaml": yaml.safe_dump(definition, sort_keys=False, allow_unicode=True, width=100),
                "revision": m.revision if m else None, "updatedBy": m.updated_by if m else None, "updatedAt": m.updated_at if m else None}

    @app.post("/v1/simulations/scenarios", status_code=201)
    async def create_scenario(body: ScenarioBody, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        if sim.managed is None:
            return _err(501, "not_configured", "Saving scenarios is not configured on this server")
        parsed = scenario_input(body)
        if isinstance(parsed, JSONResponse):
            return parsed
        definition, sc = parsed
        if any(s.name == sc.name for s in await sim.all_scenarios()):
            return _err(409, "conflict", f"A scenario named '{sc.name}' already exists")
        if sc.required and (denied := await need_require(request, "create")) is not None:
            return denied
        m, _ = await sim.managed.put(sc, definition, actor(request, None))
        await record(request, "scenario.create", sc.name, agent=sc.agent, required=sc.required, digest=sc.digest()[:12])
        return JSONResponse({"name": m.name, "revision": m.revision, "digest": sc.digest(), "required": sc.required}, status_code=201)

    @app.put("/v1/simulations/scenarios/{name}")
    async def update_scenario(name: str, body: ScenarioBody, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        if sim.managed is None:
            return _err(501, "not_configured", "Saving scenarios is not configured on this server")
        if any(s.name == name for s in sim.scenarios):
            return _err(409, "conflict", "This scenario comes from a file and is changed there")
        old = await sim.managed.get(name)
        if old is None:
            return _err(404, "not_found", "Unknown scenario")
        parsed = scenario_input(body)
        if isinstance(parsed, JSONResponse):
            return parsed
        definition, sc = parsed
        if sc.name != name:
            return _err(400, "bad_request", "A scenario cannot be renamed; save it under the new name and delete the old one")
        if (old.required or sc.required) and (denied := await need_require(request, "change")) is not None:
            return denied
        m, _ = await sim.managed.put(sc, definition, actor(request, None))
        await record(request, "scenario.update", name, agent=sc.agent, required=sc.required, was_required=old.required, digest=sc.digest()[:12], revision=m.revision)
        return {"name": m.name, "revision": m.revision, "digest": sc.digest(), "required": sc.required}

    @app.delete("/v1/simulations/scenarios/{name}")
    async def delete_scenario(name: str, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        if sim.managed is None:
            return _err(501, "not_configured", "Saving scenarios is not configured on this server")
        if any(s.name == name for s in sim.scenarios):
            return _err(409, "conflict", "This scenario comes from a file and is removed there")
        old = await sim.managed.get(name)
        if old is None:
            return _err(404, "not_found", "Unknown scenario")
        if old.required and (denied := await need_require(request, "delete")) is not None:
            return denied
        await sim.managed.delete(name)
        await record(request, "scenario.delete", name, agent=old.agent, was_required=old.required)
        return {"deleted": True}

    @app.post("/v1/simulations/runs")
    async def sim_run(body: SimRunBody, request: Request) -> Any:
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
        meta: dict[str, Any] | None = {"version": body.version} if body.version else None
        if body.model:
            if spec is None or body.mode != "live":
                return _err(400, "bad_request", "'model' needs 'agent', 'version' and mode 'live': a candidate model is tried against one saved version with a real model")
            providers = getattr(runtime.llm, "inner", None)
            qualify = getattr(providers, "qualify", None)
            try:
                named = qualify(body.model) if qualify else body.model
            except Exception as e:  # noqa: BLE001 - an unknown provider
                return _err(400, "bad_request", str(e))
            meta = {**(meta or {}), "model": named, "agent_digest": spec.digest()}  # the digest of the definition as released, which is what a conversation is served with
            spec = spec.model_copy(update={"model": named})
        try:
            run = await sim.run(body.mode, body.only, body.skip_judge, source="api", meta=meta, spec=spec)
        except Busy as e:
            return _err(409, "busy", str(e))
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "simulation.run", run.id, mode=run.mode, passed=run.passed, counts=run.counts,
                     agent=body.agent, version=body.version)
        return run_json(run)

    @app.get("/v1/agents/{agent_id}/qualifications")
    async def list_qualifications(agent_id: str) -> Any:
        q = getattr(runtime, "qualifications", None)
        if q is None:
            return _err(501, "not_configured", "Model qualification is not configured on this server")
        return {"qualifications": [x.to_dict() for x in await q.list(agent_id)]}

    @app.post("/v1/agents/{agent_id}/qualifications", status_code=201)
    async def qualify_model(agent_id: str, body: QualifyBody, request: Request) -> Any:
        """Judge a finished live run made against a candidate model, and record whether that model may serve this agent."""
        q, sim = getattr(runtime, "qualifications", None), need_sim()
        if q is None:
            return _err(501, "not_configured", "Model qualification is not configured on this server")
        if isinstance(sim, JSONResponse):
            return sim
        run = await sim.runs.get(body.run_id)
        if run is None:
            return _err(404, "not_found", "Unknown run")
        out = await q.record(run, agent_id, body.model)
        await record(request, "model.qualify", f"{agent_id}:{body.model}", "qualified" if out.qualified else "not_qualified", run=run.id, reasons=out.reasons[:5])
        return out.to_dict()

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
