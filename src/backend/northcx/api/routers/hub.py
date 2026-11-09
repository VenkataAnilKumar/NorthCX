"""Routes for the Agent Hub: requirements, install, installed list and updates (E22)."""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import HubBody
from northcx.api.template_lookup import lookup, tampered
from northcx.hub import CHANNEL_NAMES, InMemoryInstalls, Install, check_requirements, scenario_diff
from northcx.simulation.managed import parse_definition
from northcx.templates import TemplateError, _fill, render
from northcx.versions import Conflict, InvalidSpec, diff_specs


def register(app: FastAPI, d: AppDeps) -> None:
    actor, need_rel, record, rel_error, releases, simulations, templates, runtime = d.actor, d.need_rel, d.record, d.rel_error, d.releases, d.simulations, d.templates, d.runtime
    installs = getattr(runtime, "install_repo", None) or InMemoryInstalls()
    app.state.installs = installs

    async def find(template_id: str) -> Any:
        return await lookup(d, template_id) or _err(404, "not_found", "Unknown template")

    async def deployment() -> tuple[set[str], dict[str, bool], int]:
        tools = set(releases.registry.tool_names()) if releases else set()
        channels = {"web": True, "email": d.email is not None, "sms": d.sms is not None, "whatsapp": d.whatsapp is not None, "telegram": d.telegram is not None, "voice": d.voice is not None}
        sources = len(await d.kb.list_sources()) if d.kb is not None else 0
        return tools, {c: channels.get(c, False) for c in CHANNEL_NAMES}, sources

    async def rendered(t: Any, body: HubBody) -> Any:
        try:
            return render(t, body.agent_id, body.params, releases.registry if releases else None)
        except TemplateError as e:
            return _err(400, "bad_request", str(e))

    async def requirements_of(t: Any, r: Any, body: HubBody) -> dict[str, Any]:
        tools, channels, sources = await deployment()
        values = {**{p.name: str(body.params.get(p.name, p.default or "")) for p in t.params}, "agent_id": body.agent_id}
        sel = getattr(runtime.llm, "selector", None)
        return check_requirements(t, r, tools, channels, sources, bool(sel and getattr(sel, "qualification_required", False)), _fill(t.requires_tools, values))

    @app.post("/v1/templates/{template_id}/requirements")
    async def requirements(template_id: str, body: HubBody) -> Any:
        """Check a template against this deployment: tools, knowledge, channels, tests, model rules. Saves nothing."""
        t = await find(template_id)
        if isinstance(t, JSONResponse):
            return t
        r = await rendered(t, body)
        return r if isinstance(r, JSONResponse) else await requirements_of(t, r, body)

    @app.post("/v1/templates/{template_id}/install", status_code=201)
    async def install(template_id: str, body: HubBody, request: Request) -> Any:
        """Create a draft from a template, save its scenarios and run them, and record where the agent came from. The agent is not live."""
        t = await find(template_id)
        if isinstance(t, JSONResponse):
            return t
        if (why := tampered(t)):
            return _err(400, "template_not_trusted", why)
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        r = await rendered(t, body)
        if isinstance(r, JSONResponse):
            return r
        req = await requirements_of(t, r, body)
        if not req["ok"]:
            return JSONResponse({"error": {"code": "requirements_not_met", "message": "This deployment does not meet the template's requirements", "reasons": [f"{c['label']}: {c['detail']}" for c in req["checks"] if c["blocking"] and not c["ok"]]},
                                 "requirements": req}, status_code=400)
        who = actor(request, body.by)
        try:
            v = await svc.create_version(body.agent_id, r.spec, who, body.note or f"from template {t.id} v{t.version}")
        except (InvalidSpec, Conflict) as e:
            return rel_error(e)
        saved: list[str] = []
        if simulations is not None and simulations.managed is not None:
            may_require = request.state.identity.can("scenarios:require")
            existing = {s.name for s in await simulations.all_scenarios()}
            for sc in r.scenarios:
                if sc["name"] in existing:
                    continue
                definition = {**sc, "required": bool(sc.get("required", True)) and may_require, "tags": sorted({*sc.get("tags", []), "template"})}
                await simulations.managed.put(parse_definition(definition)[1], definition, who)
                saved.append(sc["name"])
        tests: dict[str, Any] = {"ran": False}
        if simulations is not None and r.scenarios:
            try:
                run = await simulations.run("scripted", skip_judge=True, source="hub", meta={"template": t.id, "version": v.number}, spec=r.spec)
                tests = {"ran": True, "runId": run.id, "passed": run.passed, "counts": run.counts}
            except Exception as e:  # noqa: BLE001 - a busy or unconfigured simulator is reported, not fatal: the draft exists
                tests = {"ran": False, "reason": str(e)[:200]}
        inst = Install(body.agent_id, t.id, t.version, {k: str(v_) for k, v_ in body.params.items()}, v.number, who, r.spec.model_dump(mode="json"), [s["name"] for s in r.scenarios], tests)
        await installs.save(inst)
        await record(request, "hub.install", f"{body.agent_id}@{v.number}", template=t.id, templateVersion=t.version, tests=tests.get("passed"))
        return JSONResponse({"agent": body.agent_id, "version": v.number, "live": False, "requirements": req, "scenariosSaved": saved, "tests": tests, "install": inst.to_dict()}, status_code=201)

    @app.get("/v1/hub/installs")
    async def list_installs() -> Any:
        out = []
        for i in await installs.list():
            t = await lookup(d, i.template_id)
            out.append({**i.to_dict(), "title": t.title if t else i.template_id, "currentTemplateVersion": t.version if t else None, "updateAvailable": bool(t and t.version != i.template_version),
                        "templateAvailable": t is not None})
        return {"installs": out}

    async def update_plan(template_id: str, agent_id: str) -> Any:
        t = await find(template_id)
        if isinstance(t, JSONResponse):
            return t
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        inst = await installs.get(agent_id)
        if inst is None or inst.template_id != template_id:
            return _err(404, "not_found", "That agent was not installed from this template")
        try:
            r = render(t, agent_id, inst.params, svc.registry)
        except TemplateError as e:
            return _err(400, "bad_request", str(e))
        latest = (await svc.versions.list(agent_id))[:1]
        current = latest[0].spec if latest else inst.spec_snapshot
        new_spec = r.spec.model_dump(mode="json")
        return t, svc, inst, r, current, {
            "from": inst.template_version, "to": t.version, "installedVersion": inst.version_number, "currentVersion": latest[0].number if latest else None,
            "templateChanges": diff_specs(inst.spec_snapshot, new_spec),                       # what the template itself changed
            "localChanges": diff_specs(inst.spec_snapshot, current),                           # what people changed on this agent since the install
            "scenarios": scenario_diff(inst.scenario_names, r.scenarios)}

    @app.post("/v1/templates/{template_id}/update-preview")
    async def update_preview(template_id: str, body: HubBody) -> Any:
        plan = await update_plan(template_id, body.agent_id)
        return plan if isinstance(plan, JSONResponse) else plan[5]

    @app.post("/v1/templates/{template_id}/update", status_code=201)
    async def update(template_id: str, body: HubBody, request: Request) -> Any:
        """Create a new draft version from the template's newer version, using the settings from the install. Local changes are shown, never silently merged: the new draft is the template's text, and the person decides what to carry over."""
        plan = await update_plan(template_id, body.agent_id)
        if isinstance(plan, JSONResponse):
            return plan
        t, svc, inst, r, current, summary = plan
        who = actor(request, body.by)
        try:
            v = await svc.create_version(body.agent_id, r.spec, who, body.note or f"update to template {t.id} v{t.version}")
        except (InvalidSpec, Conflict) as e:
            return rel_error(e)
        saved: list[str] = []
        if simulations is not None and simulations.managed is not None:
            existing = {s.name for s in await simulations.all_scenarios()}
            may_require = request.state.identity.can("scenarios:require")
            for sc in r.scenarios:
                if sc["name"] not in existing:
                    definition = {**sc, "required": bool(sc.get("required", True)) and may_require, "tags": sorted({*sc.get("tags", []), "template"})}
                    await simulations.managed.put(parse_definition(definition)[1], definition, who)
                    saved.append(sc["name"])
        inst.template_version, inst.version_number, inst.spec_snapshot, inst.scenario_names = t.version, v.number, r.spec.model_dump(mode="json"), [s["name"] for s in r.scenarios]
        inst.updated_at = time.time()
        await installs.save(inst)
        await record(request, "hub.update", f"{body.agent_id}@{v.number}", template=t.id, to=t.version)
        return JSONResponse({**summary, "version": v.number, "live": False, "scenariosSaved": saved}, status_code=201)
