"""Routes for automations: write a routine, have a second person approve it, run it, pause it, stop everything."""
from __future__ import annotations

from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import AutomationBody, AutomationRunBody, AutomationSettingsBody, OrgPolicyDecisionBody
from northcx.automations import AutomationError, AutomationService, Hooks, InMemoryAutomations
from northcx.release_requests import principal


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime = d.record, d.runtime
    svc: AutomationService = getattr(runtime, "automations", None) or AutomationService(InMemoryAutomations())
    runtime.automations = svc
    app.state.automations = svc

    async def live_assistants() -> list[Any]:
        return [a for a in await d.provider.all() if a.audience == "staff" and a.id != "pilot"]

    async def run_assistant(agent_id: str, prompt: str, session_id: str) -> tuple[str, str, str | None]:
        found = next((a for a in await live_assistants() if a.id == agent_id), None)
        if found is None:
            raise AutomationError(409, f"'{agent_id}' is not a live staff assistant")
        who = Identity("automation", "viewer", "automation")          # a read-only service identity: it can read what a viewer can read and change nothing
        agent = app.state.workspace.scoped(found, who)
        r = await runtime.run(agent, session_id, prompt, None, channel="workspace", environment="workspace", actor=who)
        return r.reply, r.status, r.trace_id

    async def exists(agent_id: str) -> bool:
        return any(a.id == agent_id for a in await live_assistants())

    async def over_budget() -> bool:
        led = getattr(runtime, "ledger", None)
        return bool(led is not None and await led.over_budget())

    reports = {name: getattr(app.state, f"report_{name}") for name in ("performance", "quality") if hasattr(app.state, f"report_{name}")}
    svc.hooks = Hooks(run_assistant, exists, reports, over_budget)

    def fail(e: AutomationError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 402: "budget", 403: "forbidden", 404: "not_found", 409: "conflict", 429: "rate_limited", 501: "not_configured"}.get(e.status, "error"), str(e))

    def definition(body: AutomationBody) -> dict[str, Any]:
        if body.definition is not None:
            return body.definition
        try:
            doc = yaml.safe_load(body.yaml or "")
        except yaml.YAMLError as e:
            raise AutomationError(400, f"Not valid YAML: {e}") from e
        if not isinstance(doc, dict):
            raise AutomationError(400, "Give the routine as YAML or as a JSON object")
        return doc

    async def summary(a: Any) -> dict[str, Any]:
        st = await svc.repo.state(a.id)
        last = (await svc.repo.runs(a.id, 1))[:1]
        return {**a.to_dict(), "paused": st["paused"], "nextRun": st["nextRun"], "lastRun": last[0].to_dict() if last else None}

    @app.get("/v1/automation-settings")
    async def get_settings() -> Any:
        return {"enabled": await svc.enabled()}

    @app.put("/v1/automation-settings")
    async def put_settings(body: AutomationSettingsBody, request: Request) -> Any:
        """The switch for every routine in the organization. Off: nothing starts and running ones stop at their next step."""
        await svc.set_enabled(body.enabled, request.state.identity.name)
        if not body.enabled:
            await svc.stop_all_runs()
        await record(request, "automations.all_enabled" if body.enabled else "automations.all_stopped", "organization")
        return {"enabled": body.enabled}

    @app.get("/v1/automations")
    async def list_automations() -> Any:
        return {"enabled": await svc.enabled(), "automations": [await summary(a) for a in await svc.repo.list()]}

    @app.get("/v1/automations/{automation_id}")
    async def get_automation(automation_id: str) -> Any:
        vs = await svc.repo.versions(automation_id)
        if not vs:
            return _err(404, "not_found", "Unknown routine")
        return {**await summary(vs[0]), "definition": vs[0].data, "yaml": yaml.safe_dump(vs[0].data, sort_keys=False, allow_unicode=True, width=100),
                "versions": [{"version": v.version, "status": v.status, "createdBy": v.created_by, "decidedBy": v.decided_by} for v in vs]}

    @app.post("/v1/automations", status_code=201)
    async def create(body: AutomationBody, request: Request) -> Any:
        try:
            a = await svc.create(definition(body), principal(request.state.identity))
        except AutomationError as e:
            return fail(e)
        await record(request, "automation.create", a.id, version=a.version)
        return {**a.to_dict(full=True), **({"webhookSecret": a.secret} if a.secret else {})}      # the secret is shown now and can be replaced, not read again

    @app.put("/v1/automations/{automation_id}")
    async def revise(automation_id: str, body: AutomationBody, request: Request) -> Any:
        try:
            a = await svc.revise(automation_id, definition(body), principal(request.state.identity))
        except AutomationError as e:
            return fail(e)
        await record(request, "automation.edit", a.id, version=a.version)
        return a.to_dict(full=True)

    @app.post("/v1/automations/{automation_id}/propose")
    async def propose(automation_id: str, request: Request) -> Any:
        try:
            a = await svc.propose(automation_id, principal(request.state.identity))
        except AutomationError as e:
            return fail(e)
        await record(request, "automation.propose", a.id, version=a.version)
        return a.to_dict()

    async def decide(automation_id: str, request: Request, approve: bool, note: str | None) -> Any:
        action = "automation.approve" if approve else "automation.reject"
        try:
            a = await svc.decide(automation_id, approve, principal(request.state.identity), note)
        except AutomationError as e:
            await record(request, action, automation_id, "denied", reason=str(e))
            return fail(e)
        await record(request, action, a.id, version=a.version, proposedBy=a.proposed_by)
        return a.to_dict()

    @app.post("/v1/automations/{automation_id}/approve")
    async def approve(automation_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        return await decide(automation_id, request, True, body.note)

    @app.post("/v1/automations/{automation_id}/reject")
    async def reject(automation_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        return await decide(automation_id, request, False, body.note)

    @app.post("/v1/automations/{automation_id}/retire")
    async def retire(automation_id: str, body: OrgPolicyDecisionBody, request: Request) -> Any:
        try:
            a = await svc.retire(automation_id, principal(request.state.identity), body.note)
        except AutomationError as e:
            return fail(e)
        await record(request, "automation.retire", a.id, version=a.version)
        return a.to_dict()

    async def pause(automation_id: str, request: Request, paused: bool) -> Any:
        try:
            st = await svc.pause(automation_id, paused)
        except AutomationError as e:
            return fail(e)
        await record(request, "automation.pause" if paused else "automation.resume", automation_id)
        return {"id": automation_id, "paused": st["paused"]}

    @app.post("/v1/automations/{automation_id}/pause")
    async def pause_one(automation_id: str, request: Request) -> Any:
        return await pause(automation_id, request, True)

    @app.post("/v1/automations/{automation_id}/resume")
    async def resume_one(automation_id: str, request: Request) -> Any:
        return await pause(automation_id, request, False)

    @app.post("/v1/automations/{automation_id}/secret")
    async def rotate_secret(automation_id: str, request: Request) -> Any:
        """Make a new webhook secret. The old one stops working at once; the new one is shown only here."""
        import secrets as _s
        vs = await svc.repo.versions(automation_id)
        if not vs or vs[0].data["trigger"]["type"] != "webhook":
            return _err(404, "not_found", "No webhook routine with that id")
        new = _s.token_urlsafe(24)
        for v in vs:
            v.secret = new
            await svc.repo.save(v)
        await record(request, "automation.secret_rotated", automation_id)
        return JSONResponse({"webhookSecret": new}, headers={"Cache-Control": "no-store"})

    async def start(automation_id: str, request: Request, trigger: str, text: str) -> Any:
        try:
            run = await svc.run(automation_id, trigger, request.state.identity.name, text, wait=False)
        except AutomationError as e:
            await record(request, f"automation.{trigger}", automation_id, "denied", reason=str(e))
            return fail(e)
        await record(request, f"automation.{trigger}", automation_id, run=run.id)
        return JSONResponse(run.to_dict(), status_code=202)

    @app.post("/v1/automations/{automation_id}/run")
    async def run_now(automation_id: str, body: AutomationRunBody, request: Request) -> Any:
        return await start(automation_id, request, "manual", body.input)

    @app.post("/v1/automations/{automation_id}/hook")
    async def hook(automation_id: str, request: Request) -> Any:
        """A webhook trigger: needs a key that may run routines and a valid signature, `X-Northcx-Signature: sha256=<hmac of the body with the routine's secret>`."""
        raw = await request.body()
        if len(raw) > 20000:
            return _err(413, "too_large", "The body is too large")
        a = next((v for v in await svc.repo.versions(automation_id) if v.status == "published"), None)
        if a is None or a.data["trigger"]["type"] != "webhook":
            return _err(404, "not_found", "No published webhook routine with that id")
        if not svc.verify_signature(a, raw, request.headers.get("x-northcx-signature")):
            await record(request, "automation.hook", automation_id, "denied", reason="bad signature")
            return _err(401, "bad_signature", "The signature does not match")
        return await start(automation_id, request, "webhook", raw.decode("utf-8", "replace"))

    @app.get("/v1/automations/{automation_id}/runs")
    async def runs(automation_id: str, limit: int = 30) -> Any:
        return {"runs": [r.to_dict() for r in await svc.repo.runs(automation_id, max(1, min(limit, 100)))]}

    @app.get("/v1/automation-runs/{run_id}")
    async def get_run(run_id: str) -> Any:
        r = await svc.repo.get_run(run_id)
        return r.to_dict() if r else _err(404, "not_found", "Unknown run")
