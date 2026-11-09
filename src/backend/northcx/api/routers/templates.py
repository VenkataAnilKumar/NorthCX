"""Routes for agent templates and the skill catalog."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import TemplateBody
from northcx.api.template_lookup import all_templates, lookup, tampered
from northcx.simulation.managed import parse_definition
from northcx.templates import render, Template, TemplateError
from northcx.versions import Conflict, InvalidSpec


def register(app: FastAPI, d: AppDeps) -> None:
    actor = d.actor
    need_rel = d.need_rel
    record = d.record
    rel_error = d.rel_error
    releases = d.releases
    simulations = d.simulations
    skills = d.skills
    templates = d.templates
    version_json = d.version_json

    # ---- templates ----
    async def find_template(template_id: str) -> Template | JSONResponse:
        return await lookup(d, template_id) or _err(404, "not_found", "Unknown template")

    def rendered_json(r: Any) -> dict[str, Any]:
        return {"specYaml": r.spec_yaml, "scenariosYaml": r.scenarios_yaml, "scenarios": len(r.scenarios), "missingTools": r.missing_tools, "warnings": r.warnings}

    @app.get("/v1/templates")
    async def list_templates() -> Any:
        return {"templates": [t.info() for t in (await all_templates(d)).values()]}

    @app.get("/v1/templates/{template_id}")
    async def get_template(template_id: str) -> Any:
        t = await find_template(template_id)
        return t if isinstance(t, JSONResponse) else t.info()

    @app.post("/v1/templates/{template_id}/render")
    async def render_template(template_id: str, body: TemplateBody) -> Any:
        """Fill in a template without saving anything: the agent spec, its scenarios, and what this deployment is missing."""
        t = await find_template(template_id)
        if isinstance(t, JSONResponse):
            return t
        try:
            return rendered_json(render(t, body.agent_id, body.params, releases.registry if releases else None))
        except TemplateError as e:
            return _err(400, "bad_request", str(e))

    @app.post("/v1/templates/{template_id}/create-version", status_code=201)
    async def template_version(template_id: str, body: TemplateBody, request: Request) -> Any:
        """Save the rendered agent as a version (it still needs its scenarios and the release gate before it can go live)."""
        t = await find_template(template_id)
        if isinstance(t, JSONResponse):
            return t
        if (why := tampered(t)):
            return _err(400, "template_not_trusted", why)
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            r = render(t, body.agent_id, body.params, svc.registry)
        except TemplateError as e:
            return _err(400, "bad_request", str(e))
        if r.missing_tools:
            return _err(400, "missing_tools", r.warnings[-1] if r.warnings else "This deployment lacks tools the template needs")
        try:
            v = await svc.create_version(body.agent_id, r.spec, actor(request, body.by), body.note or f"from template {t.id}")
        except (InvalidSpec, Conflict) as e:
            return rel_error(e)
        await record(request, "template.create_version", f"{body.agent_id}@{v.number}", template=t.id)
        saved, skipped = [], []
        if body.save_scenarios and simulations is not None and simulations.managed is not None:
            # The template's tests are saved too. They gate releases only if the person saving them may decide that.
            may_require = request.state.identity.can("scenarios:require")
            existing = {s.name for s in await simulations.all_scenarios()}
            for sc in r.scenarios:
                if sc["name"] in existing:
                    skipped.append(sc["name"])
                    continue
                definition = {**sc, "required": bool(sc.get("required", True)) and may_require, "tags": sorted({*sc.get("tags", []), "template"})}
                parsed_sc = parse_definition(definition)[1]
                await simulations.managed.put(parsed_sc, definition, actor(request, body.by))
                saved.append(sc["name"])
            await record(request, "scenario.create", f"{body.agent_id}: {len(saved)} from template {t.id}", required=may_require)
        return JSONResponse({**version_json(v, full=True), **rendered_json(r), "scenariosSaved": saved, "scenariosSkipped": skipped,
                             "scenariosRequired": may_require if saved else None}, status_code=201)

    @app.get("/v1/skills")
    async def list_skills() -> Any:
        """The skills agents can use, with their steps."""
        return {"skills": [{"name": s.name, "description": s.description, "instructions": s.instructions, "tools": s.tool_names(),
                            "steps": [{"purpose": x.purpose, "tool": x.tool, "required": x.required} for x in s.steps]} for s in (skills or [])],
                "flexibility": ["strict", "guided", "free"]}
