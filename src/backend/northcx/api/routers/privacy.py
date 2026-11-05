"""Routes for privacy: export, erasure and retention."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.deps import AppDeps
from northcx.api.models import RetentionBody
from northcx.privacy import customer_ref


def register(app: FastAPI, d: AppDeps) -> None:
    privacy = d.privacy
    record = d.record
    runtime = d.runtime

    # ---- privacy: export, erasure, retention ----
    @app.get("/v1/privacy/customers/{customer_id:path}/export")
    async def privacy_export(customer_id: str, request: Request) -> Any:
        data = await privacy.export_customer(customer_id)
        await record(request, "privacy.export", customer_ref(customer_id), sessions=len(data["sessions"]))
        return JSONResponse(data, headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="customer-export.json"'})

    @app.delete("/v1/privacy/customers/{customer_id:path}")
    async def privacy_erase_customer(customer_id: str, request: Request) -> Any:
        r = await privacy.erase_customer(customer_id)
        if runtime.context is not None:
            runtime.context.forget(customer_id)  # do not keep serving the cached copy
        await record(request, "privacy.erase.customer", customer_ref(customer_id), **r)
        return r

    @app.delete("/v1/privacy/sessions/{session_id:path}")
    async def privacy_erase_session(session_id: str, request: Request) -> Any:
        r = await privacy.erase_session(session_id)
        await record(request, "privacy.erase.session", customer_ref(session_id), removed=r)
        return {"removed": r}

    @app.post("/v1/privacy/retention/run")
    async def privacy_retention(body: RetentionBody, request: Request) -> Any:
        r = await privacy.purge_idle(body.older_than_days)
        await record(request, "privacy.retention", f"older than {body.older_than_days:g} days", **r)
        return r
