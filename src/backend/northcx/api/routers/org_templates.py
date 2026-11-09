"""Routes for the organization's own Hub templates: write, check, propose, approve by a second person, withdraw (WP22.5)."""
from __future__ import annotations

from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import OrgPolicyDecisionBody, OrgTemplateBody
from northcx.org_templates import OrgTemplateError, OrgTemplateService, check_template
from northcx.release_requests import principal


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime = d.record, d.runtime

    def svc() -> OrgTemplateService | JSONResponse:
        return getattr(runtime, "org_templates", None) or _err(501, "not_configured", "Organization templates are not configured on this server")

    def fail(e: OrgTemplateError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 403: "forbidden", 404: "not_found", 409: "conflict"}.get(e.status, "error"), str(e))

    def document(body: OrgTemplateBody) -> dict[str, Any]:
        if body.template is not None:
            return body.template
        try:
            doc = yaml.safe_load(body.yaml or "")
        except yaml.YAMLError as e:
            raise OrgTemplateError(400, f"Not valid YAML: {e}") from e
        if not isinstance(doc, dict):
            raise OrgTemplateError(400, "Give the template as YAML or as a JSON object")
        return doc

    @app.get("/v1/org-templates")
    async def list_org_templates() -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        out = []
        for o in await s.repo.list():
            out.append({**o.to_dict(), "versions": [{"version": v.version, "status": v.status, "createdBy": v.created_by, "decidedBy": v.decided_by} for v in await s.repo.versions(o.id)]})
        return {"templates": out}

    @app.get("/v1/org-templates/{template_id}")
    async def get_org_template(template_id: str) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        o = await s.repo.get(template_id)
        return o.to_dict(full=True) if o else _err(404, "not_found", "Unknown template")

    @app.post("/v1/org-templates/check")
    async def check(body: OrgTemplateBody) -> Any:
        """Parse and render a template with example values. Saves nothing."""
        try:
            t, c = check_template(document(body), set(d.templates or {}))
        except OrgTemplateError as e:
            return fail(e)
        return {**c, "id": t.id, "title": t.title}

    @app.post("/v1/org-templates", status_code=201)
    async def create(body: OrgTemplateBody, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            o = await s.create(document(body), principal(request.state.identity))
        except OrgTemplateError as e:
            return fail(e)
        await record(request, "org_template.create", o.id, version=o.version, ok=o.check.get("ok"))
        return o.to_dict()

    @app.put("/v1/org-templates/{template_id}")
    async def revise(template_id: str, body: OrgTemplateBody, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            o = await s.revise(template_id, document(body), principal(request.state.identity))
        except OrgTemplateError as e:
            return fail(e)
        await record(request, "org_template.edit", o.id, version=o.version, ok=o.check.get("ok"))
        return o.to_dict()

    @app.post("/v1/org-templates/{template_id}/propose")
    async def propose(template_id: str, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            o = await s.propose(template_id, principal(request.state.identity))
        except OrgTemplateError as e:
            return fail(e)
        await record(request, "org_template.propose", o.id, version=o.version)
        return o.to_dict()

    async def decide(template_id: str, request: Request, approve: bool, note: str | None) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        action = "org_template.approve" if approve else "org_template.reject"
        try:
            o = await s.decide(template_id, approve, principal(request.state.identity), note)
        except OrgTemplateError as e:
            await record(request, action, template_id, "denied", reason=str(e))
            return fail(e)
        await record(request, action, o.id, version=o.version, proposedBy=o.proposed_by)
        return o.to_dict()

    @app.post("/v1/org-templates/{template_id}/approve")
    async def approve(template_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        return await decide(template_id, request, True, body.note)

    @app.post("/v1/org-templates/{template_id}/reject")
    async def reject(template_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        return await decide(template_id, request, False, body.note)

    @app.post("/v1/org-templates/{template_id}/withdraw")
    async def withdraw(template_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            o = await s.withdraw(template_id, principal(request.state.identity), body.note)
        except OrgTemplateError as e:
            return fail(e)
        await record(request, "org_template.withdraw", o.id, version=o.version)
        return o.to_dict()
