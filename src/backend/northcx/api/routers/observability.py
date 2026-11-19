"""Routes for alerts, monitoring, regression status, trace export, traces, status events and the residency report."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import EventTestBody
from northcx.api.responses import EventFeed, EventTestResult, EventTypes, Trace, TraceExports, TraceList
from northcx.events import EVENTS


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    alerts = d.alerts
    events = d.events
    record = d.record
    regression = d.regression
    residency = d.residency
    runtime = d.runtime
    too_many = d.too_many
    traces = d.traces

    @app.get("/v1/alerts")
    async def alert_status() -> Any:
        """The alert rules, which are firing now, and recent alert events."""
        if alerts is not None:
            await alerts.refresh()
        return alerts.status() if alerts is not None else {"enabled": False}

    @app.get("/v1/regression")
    async def regression_status() -> Any:
        """Whether simulations re-run when the knowledge changes, and how the last re-run went."""
        return regression.status() if regression is not None else {"enabled": False}

    @app.get("/v1/events/types", responses={200: {"model": EventTypes}})
    async def event_types() -> Any:
        return {"enabled": events is not None, "types": [{"type": k, "description": v, "subscribed": events is not None and k in events.types} for k, v in EVENTS.items()]}

    @app.post("/v1/events/test", responses={200: {"model": EventTestResult}})
    async def event_test(body: EventTestBody, request: Request) -> Any:
        """Sends one signed sample event of the given type to the configured events webhook and reports whether the receiver accepted it.
        Nothing is stored or retried, and the sample is marked `test`."""
        webhook = getattr(events, "webhook", None) if events is not None else None
        if webhook is None:
            return _err(501, "not_configured", "Status events are not configured: set NORTHCX_EVENTS_WEBHOOK_URL (and NORTHCX_EVENTS_WEBHOOK_SECRET)")
        if body.type not in EVENTS:
            return _err(400, "bad_request", "Unknown event type; see GET /v1/events/types")
        who = request.state.identity
        if not (await access.limiter.hit(f"events-test:{who.key_id or 'open'}", 6))[0]:
            return too_many(60, "event tests")
        result = await webhook.send_test(body.type)
        await record(request, "events.test", body.type, outcome="success" if result["status"] == "sent" else "failure", delivery=result["status"])
        return {"type": body.type, **result}

    @app.get("/v1/events", responses={200: {"model": EventFeed}})
    async def event_feed(after: int = 0, limit: int = 100) -> Any:
        """The same events the webhook sends, for receivers that would rather poll. `after` is the id of the last event already seen."""
        if events is None:
            return _err(501, "not_configured", "Status events are not configured: set NORTHCX_EVENTS_WEBHOOK_URL (and NORTHCX_EVENTS_WEBHOOK_SECRET)")
        return {"events": await events.listing(max(0, after), limit)}

    @app.get("/v1/residency")
    async def residency_report() -> Any:
        """Where this deployment keeps data and where it sends it, checked against the residency file (evidence for a data-processing agreement)."""
        return residency or {"configured": False, "flows": [], "compliant": False, "problems": [], "note": "Residency is not reported by this server."}

    @app.get("/v1/trace-export")
    async def trace_export_status() -> Any:
        """Whether export is on, where traces go, what content is sent, and how deliveries are doing."""
        x = runtime.exports
        if x is None:
            return {"configured": False}
        return {"configured": True, "exporters": sorted(x.exporters), "content": x.redactor.mode, "sample": x.sample, "environment": x.environment,
                **await x.repo.counts()}

    @app.get("/v1/traces/{trace_id}/exports", responses={200: {"model": TraceExports}})
    async def trace_exports(trace_id: str) -> Any:
        if await traces.get(trace_id) is None:
            return _err(404, "not_found", "Unknown trace")
        jobs = await runtime.exports.repo.for_trace(trace_id) if runtime.exports is not None else []
        return {"configured": runtime.exports is not None, "deliveries": [j.to_dict() for j in jobs]}

    @app.get("/v1/traces/{trace_id}", responses={200: {"model": Trace}})
    async def get_trace(trace_id: str) -> Any:
        t = await traces.get(trace_id)
        return t.to_dict() if t else _err(404, "not_found", "Unknown trace")

    @app.post("/v1/alerts/test")
    async def alert_test(request: Request) -> Any:
        """Sends a test alert through the real delivery path and reports whether the receiver accepted it."""
        if alerts is None:
            return _err(501, "not_configured", "Alerts are not configured on this server")
        e = await alerts.send_test()
        await record(request, "alert.test", "alerts", delivery=e["delivery"]["status"])
        return e

    @app.get("/v1/monitor/findings")
    async def monitor_findings(rule: str | None = None, severity: str | None = None, agentId: str | None = None,
                               sessionId: str | None = None, since: float | None = None, limit: int = 100) -> Any:
        items = await runtime.monitor.repo.list(rule=rule, severity=severity, agent_id=agentId, session_id=sessionId,
                                                since=since, limit=max(1, min(limit, 500)))
        return {"findings": [f.to_dict() for f in items]}

    @app.get("/v1/monitor/summary")
    async def monitor_summary(since: float | None = None) -> Any:
        counts = await runtime.monitor.repo.counts(since)
        return {"rules": sorted(runtime.monitor.rules), "counts": counts,
                "total": sum(n for by in counts.values() for n in by.values())}

    @app.get("/v1/traces", responses={200: {"model": TraceList}})
    async def list_traces(sessionId: str | None = None, limit: int = 200) -> Any:
        items = await traces.summaries(sessionId, max(1, min(limit, 1000)))
        return {"traces": [{"id": t.id, "agentId": t.agent_id, "sessionId": t.session_id, "events": t.events,
                            "status": t.status, "startedAt": t.started_at, "tools": t.tools,
                            "agentVersion": t.agent_version, "environment": t.environment} for t in items]}
