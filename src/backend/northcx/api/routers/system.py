"""The operator's health page: what works, what does not, and what to do. Nothing here calls a model or sends a message."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from northcx.api.deps import AppDeps

log = logging.getLogger("northcx.system")
OK, FAILING, NOT_SET_UP = "ok", "failing", "not_set_up"


def check(name: str, status: str, detail: str, action: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "action": action}


def register(app: FastAPI, d: AppDeps) -> None:
    runtime = d.runtime

    async def database() -> dict[str, str]:
        try:
            await runtime.store.load_messages("__health_probe__")
            await runtime.traces.summaries(limit=1)
        except Exception:
            log.exception("health check: database")
            return check("Database", FAILING, "The database did not answer.", "Check that Postgres is running and that NORTHCX_DATABASE_URL is right; the server log has the error.")
        kind = "Postgres" if hasattr(runtime.store, "schema_revision") else "memory"
        if kind == "memory":
            return check("Database", NOT_SET_UP, "No database is set: conversations are kept in memory and are lost when the server stops.", "Set NORTHCX_DATABASE_URL for anything beyond a trial.")
        return check("Database", OK, "Postgres answers.")

    async def migrations() -> dict[str, str]:
        from northcx.ops.backup import newest_revision
        if not hasattr(runtime.store, "schema_revision"):
            return check("Database schema", NOT_SET_UP, "No database, so no schema.")
        try:
            have = await runtime.store.schema_revision()
        except Exception:
            log.exception("health check: schema revision")
            return check("Database schema", FAILING, "The schema revision could not be read.", "See the server log; the database may not have been migrated.")
        want = newest_revision()
        if have == want:
            return check("Database schema", OK, f"At revision {have}, the one this version expects.")
        return check("Database schema", FAILING, f"At revision {have}; this version expects {want}.", "Restart the server so the migrations run, or restore a backup made by this version.")

    def providers() -> dict[str, str]:
        registry = getattr(runtime.llm, "inner", None)
        names = list(getattr(registry, "names", []) or [])
        if not names:
            return check("Models", NOT_SET_UP, "No model providers are set up (the offline demo model is in use, or none).", "Set ANTHROPIC_API_KEY or a providers file (NORTHCX_PROVIDERS_FILE); see the local models guide.")
        return check("Models", OK, f"{len(names)} provider(s) set up: {', '.join(names)}. Reachability is not tested here, because that would cost a model call; the Models page and the traces show real calls.")

    def channels() -> list[dict[str, str]]:
        out = []
        for label, obj in (("Email", d.email), ("SMS", d.sms), ("WhatsApp", d.whatsapp), ("Telegram", d.telegram), ("Voice", d.voice)):
            out.append(check(f"Channel: {label}", OK if obj is not None else NOT_SET_UP, "Set up." if obj is not None else "Not set up.",
                             "" if obj is not None else f"Optional. See the channel's setting in .env.example if you want {label}."))
        return out

    def alert_delivery() -> dict[str, str]:
        mgr = d.alerts
        if mgr is None:
            return check("Alert delivery", NOT_SET_UP, "Alerts are off.", "Set NORTHCX_ALERTS to turn them on.")
        st = mgr.status()
        if not st["webhook"]:
            return check("Alert delivery", NOT_SET_UP, "Alerts are on but no alert webhook is set, so nobody is told outside the console.", "Set NORTHCX_ALERT_WEBHOOK_URL and NORTHCX_ALERT_WEBHOOK_SECRET.")
        if st["undelivered"]:
            return check("Alert delivery", FAILING, f"{st['undelivered']} recent alert(s) could not be delivered.", "Check the webhook address and secret; POST /v1/alerts/test sends a test alert.")
        return check("Alert delivery", OK, "No recent alert failed to reach the webhook.")

    @app.get("/v1/system/health")
    async def system_health() -> Any:
        """Each part of the system as ok, failing or not set up, with what to do. Needs the permission to manage keys (an operator)."""
        checks = [await database(), await migrations(), providers(), *channels(), alert_delivery()]
        return {"status": FAILING if any(c["status"] == FAILING for c in checks) else OK, "checks": checks}
