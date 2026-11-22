"""Routes for automations: write a routine, have a second person approve it, run it, pause it, stop everything."""
from __future__ import annotations

from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import AutomationBody, AutomationDecisionBody, AutomationDraftBody, AutomationRunBody, AutomationSettingsBody, OrgPolicyDecisionBody
from northcx.automations import AutomationError, AutomationService, Hooks, InMemoryAutomations, TRIGGER_TYPES, validate_definition
from northcx.release_requests import principal


def _destinations() -> dict[str, tuple[str, str]]:
    """Where a routine may send a result: names the administrator set up as NORTHCX_AUTOMATION_DESTINATIONS="name=https://..." with one shared signing secret."""
    import os
    secret = os.environ.get("NORTHCX_AUTOMATION_DESTINATIONS_SECRET", "").strip()
    out: dict[str, tuple[str, str]] = {}
    for part in filter(None, (p.strip() for p in os.environ.get("NORTHCX_AUTOMATION_DESTINATIONS", "").split(","))):
        name, _, url = part.partition("=")
        if name and url.startswith(("https://", "http://")) and len(secret) >= 16:
            out[name.strip()] = (url.strip(), secret)
        elif name and url.startswith("mailto:") and "@" in url and not any(c in url for c in "\r\n<>\" "):
            out[name.strip()] = (url.strip(), "")                            # an address the administrator chose; sent through the server's own mail settings
    return out


def register(app: FastAPI, d: AppDeps) -> None:
    record, runtime = d.record, d.runtime
    svc: AutomationService = getattr(runtime, "automations", None) or AutomationService(InMemoryAutomations())
    runtime.automations = svc
    signer = getattr(d.access, "signer", None)
    svc.derive = signer.derive if signer is not None else None
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
    async def save_output(title: str, body: str, automation_id: str) -> str:
        content = getattr(runtime, "content", None)
        if content is None:
            raise AutomationError(501, "Outputs are not configured on this server")
        o = await content.create_output(f"automation:{automation_id}", title, body, "digest", "shared", None, f"automation:{automation_id}", 90, False)
        return o.id

    async def feed(after: int, limit: int) -> list[dict[str, Any]]:
        return await d.events.listing(after, limit) if d.events is not None else []

    async def tag_session(session_id: str, tag: str, automation_id: str) -> bool:
        if not await d.traces.summaries(session_id, 1):
            return False
        try:
            await d.tag_repo.add(session_id, "auto-" + tag, f"automation:{automation_id}")
        except ValueError:
            return False
        return True

    destinations = _destinations()

    async def notify(name: str, payload: dict[str, Any]) -> None:
        import json as _json
        import time as _time

        import httpx

        from northcx.notify import sign
        url, secret = destinations[name]
        if url.startswith("mailto:"):
            await send_mail(url[7:], payload)
            return
        body = _json.dumps({"type": "automation.result", **payload}, sort_keys=True).encode()
        ts = str(int(_time.time()))
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            r = await client.post(url, content=body, headers={"content-type": "application/json", "x-northcx-timestamp": ts, "x-northcx-signature": sign(secret, ts, body)})
        if r.status_code >= 300:
            raise AutomationError(502, f"The destination answered {r.status_code}")

    async def send_mail(to: str, payload: dict[str, Any]) -> None:
        import os
        from email.message import EmailMessage

        from northcx.channels.email import SmtpError, SmtpSender
        from northcx.secrets import env_or_file
        smtp_url, sender = env_or_file("NORTHCX_SMTP_URL"), os.environ.get("NORTHCX_EMAIL_FROM", "").strip()
        if not smtp_url or not sender:
            raise AutomationError(501, "Email is not set up on this server (NORTHCX_SMTP_URL and NORTHCX_EMAIL_FROM)")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = sender, to, f"NorthCX routine {payload.get('automation', '')}"[:120]
        msg.set_content(f"{payload.get('text', '')}\n\n-- Sent by the routine '{payload.get('automation')}' after a person approved it (run {payload.get('run')}).")
        try:
            await SmtpSender(smtp_url).send(msg)
        except SmtpError as e:
            raise AutomationError(502, str(e)[:200]) from e

    from northcx.events import EVENTS
    from northcx.safety.pii import PIIDetection
    svc.hooks = Hooks(run_assistant, exists, reports, over_budget, save_output, feed if d.events is not None else None, frozenset(EVENTS) if d.events is not None else frozenset(),
                      tag_session, notify, frozenset(destinations), mask=lambda t: PIIDetection().mask(t)[0])
    service_identity = Identity("automation", "viewer", "automation")

    def registry() -> Any:
        return d.releases.registry if d.releases is not None else None

    def callable_tools() -> dict[str, dict[str, Any]]:
        """What a tool step may name: staff tools the routine's service identity is allowed to use, and customer-side tools that only read or change things behind a person's approval."""
        reg = registry()
        if reg is None:
            return {}
        out: dict[str, dict[str, Any]] = {}
        for name in reg.tool_names():
            t = reg.get(name)
            allowed = t.audience != "staff" or service_identity.can(t.permission)
            out[name] = {"effect": t.effect, "allowed": allowed, "why": f"it needs the {t.permission} permission, which routines do not have", "model": t.input_model}
        return out

    def tool_approval(name: str, args: dict[str, Any]) -> str | None:
        t = registry().get(name)
        return t.requires_approval(t.input_model.model_validate(args)) if t.requires_approval is not None else None

    async def call_tool(name: str, args: dict[str, Any], key: str) -> Any:
        from northcx.agent import ToolContext
        t = registry().get(name)
        try:
            data = t.input_model.model_validate(args)
        except Exception as e:  # noqa: BLE001 - arguments filled in from an earlier result may not fit the tool
            raise AutomationError(400, f"The arguments for '{name}' are not valid: {str(e).splitlines()[0][:150]}") from e
        ctx = ToolContext(key, None, runtime.store, idempotency_key=key, secrets=runtime.secrets, actor=service_identity)
        try:
            result, _ = await runtime.execute_tool(t, data, ctx)
        except PermissionError as e:
            raise AutomationError(403, str(e)) from e
        except Exception as e:  # noqa: BLE001 - the tool's own failure message, shortened
            raise AutomationError(502, f"'{name}' failed: {str(e)[:150]}") from e
        return result

    svc.hooks.tools, svc.hooks.tool_approval, svc.hooks.call_tool = callable_tools, tool_approval, call_tool

    def fail(e: AutomationError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 402: "budget", 403: "forbidden", 404: "not_found", 409: "conflict", 413: "too_large", 429: "rate_limited", 501: "not_configured"}.get(e.status, "error"), str(e))

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
        return {**a.to_dict(full=True), **({"webhookSecret": svc.webhook_secret(a)} if a.nonce else {})}      # the secret is shown now and can be replaced, not read again

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
        nonce = _s.token_hex(8)
        for v in vs:
            v.nonce = nonce
            await svc.repo.save(v)
        new = svc.webhook_secret(vs[0])
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

    @app.get("/v1/automations-catalog")
    async def catalog() -> Any:
        """What a routine may name: the choices the editor offers."""
        h = svc.hooks
        return {"reports": sorted(h.reports) if h else [], "events": sorted(h.event_types) if h else [], "destinations": sorted(h.destinations) if h else [],
                "assistants": sorted(a.id for a in await live_assistants()), "kinds": ["report", "assistant", "tool", "branch", "foreach", "person", "tag", "notify", "output"], "tools": [{"name": k, "effect": v["effect"]} for k, v in sorted(callable_tools().items()) if v["allowed"]], "triggers": list(TRIGGER_TYPES),
                "triggerInfo": [{"type": k, "label": label, "description": text, **({"events": sorted(h.event_types) if h else []} if k == "event" else {})} for k, (label, text) in TRIGGER_TYPES.items()]}

    @app.post("/v1/automations/convert")
    async def convert(body: AutomationBody) -> Any:
        """Between YAML and JSON for the editor, with every problem the checks find. Saves nothing."""
        try:
            raw = definition(body)
        except AutomationError as e:
            return fail(e)
        problems: list[str] = []
        try:
            clean = validate_definition(raw, svc._reports(), svc._events(), svc._destinations(), svc._tools())
            if svc.hooks is not None:
                for s in clean["steps"]:
                    if s["kind"] == "assistant" and not await exists(s["assistant"]):
                        problems.append(f"Step '{s['id']}': '{s['assistant']}' is not a live staff assistant")
        except AutomationError as e:
            problems.append(str(e))
        return {"definition": raw, "yaml": yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=100), "valid": not problems, "problems": problems}

    @app.post("/v1/automations/draft")
    async def draft_routine(body: AutomationDraftBody, request: Request) -> Any:
        """Describe a routine in words and get a checked draft with a dry run. Nothing is saved. Costs a model call, so it respects the daily budget."""
        from northcx.automation_builder import draft
        if await over_budget():
            return _err(402, "budget", "The daily budget is used up")
        try:
            out = await draft(svc, runtime.llm, body.description)
        except AutomationError as e:
            return fail(e)
        except Exception:
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        if out["definition"] is not None:
            out["yaml"] = yaml.safe_dump(out["definition"], sort_keys=False, allow_unicode=True, width=100)
        await record(request, "automation.draft", "builder", chars=len(body.description), valid=out["definition"] is not None)
        return out

    @app.get("/v1/automation-runs")
    async def list_runs(status: str | None = None, limit: int = 50) -> Any:
        """Recent runs of every routine; `status=waiting` is what is waiting for a person."""
        rows = await svc.repo.runs(None, 200)
        return {"runs": [r.to_dict() for r in rows if status is None or r.status == status][: max(1, min(limit, 100))]}

    @app.post("/v1/automation-runs/{run_id}/decision")
    async def decide_run(run_id: str, body: AutomationDecisionBody, request: Request) -> Any:
        """Answer a routine that is waiting for a person. Needs the permission to decide approvals; not the person who started the run."""
        who = request.state.identity
        pending = await svc.repo.get_run(run_id)
        want = (pending.waiting or {}).get("approver") if pending is not None else None
        if want:                                                      # the routine named who may answer
            ok = (want.get("role") in (who.role, *who.extra_roles)) if "role" in want else (want.get("group") in who.groups)
            if not ok:
                await record(request, "automation.decide", run_id, "denied", reason="not the person asked")
                return _err(403, "forbidden", f"This is for {'someone with the ' + want['role'] + ' role' if 'role' in want else 'someone in the ' + want['group'] + ' team'}")
        try:
            run = await svc.decide_run(run_id, body.approve, request.state.identity.name, body.note)
        except AutomationError as e:
            await record(request, "automation.decide", run_id, "denied", reason=str(e))
            return fail(e)
        await record(request, "automation.decide", run_id, approved=body.approve, automation=run.automation_id)
        return run.to_dict()

    @app.get("/v1/automations/{automation_id}/runs")
    async def runs(automation_id: str, limit: int = 30) -> Any:
        return {"runs": [r.to_dict() for r in await svc.repo.runs(automation_id, max(1, min(limit, 100)))]}

    @app.get("/v1/automation-runs/{run_id}")
    async def get_run(run_id: str) -> Any:
        r = await svc.repo.get_run(run_id)
        return r.to_dict() if r else _err(404, "not_found", "Unknown run")
