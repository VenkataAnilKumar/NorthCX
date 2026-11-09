"""The platform API (WP2.8): how the operator of a NorthCX service manages tenants. It is a separate application on its own listener, with its own key,
so a tenant's key can never reach it, and it works on metadata only: tenants, their status, plan, limits and channel addresses. It has no route that reads or
changes a tenant's conversations, people or documents. Every change it makes is also written to the affected tenant's own audit log, under the actor `platform`.
"""
from __future__ import annotations

import hmac
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .audit import AuditEntry
from .secrets import ConfigError
from .tenancy import DEFAULT_TENANT, TENANT, TenantError
from .tenant_limits import LimitError

MIN_KEY = 32
PLAN_RE = re.compile(r"^[a-z0-9][a-z0-9 _.-]{0,39}$")


class TenantBody(BaseModel):
    id: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    plan: str | None = Field(default=None, max_length=40)


class PlanBody(BaseModel):
    plan: str = Field(min_length=1, max_length=40)


class BindingBody(BaseModel):
    kind: str = Field(max_length=20)
    address: str = Field(min_length=1, max_length=200)


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_platform_app(key: str, tenants: Any, limits: Any, settings_repo: Any, audit: Any, access: Any = None) -> FastAPI:
    if not key or len(key) < MIN_KEY:
        raise ConfigError(f"NORTHCX_PLATFORM_KEY must be at least {MIN_KEY} characters")
    app = FastAPI(title="NorthCX platform", docs_url=None, redoc_url=None, openapi_url=None)
    failures: dict[str, list[float]] = {}

    @app.exception_handler(RequestValidationError)
    async def bad(request: Request, exc: RequestValidationError):
        return err(400, "bad_request", "The request is not valid")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path == "/platform/health":
            return await call_next(request)
        if not request.url.path.startswith("/platform/v1/"):
            return err(404, "not_found", "No such endpoint")
        import time
        ip = request.client.host if request.client else "unknown"
        recent = [t for t in failures.get(ip, []) if time.time() - t < 60]
        if len(recent) >= 20:
            return err(429, "too_many", "Too many failed attempts")
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or not hmac.compare_digest(header[7:].encode(), key.encode()):
            failures[ip] = recent + [time.time()]
            return err(401, "unauthorized", "Missing or invalid platform key")
        return await call_next(request)

    async def note(tenant_id: str, action: str, **detail: Any) -> None:
        token = TENANT.set(tenant_id)                        # the entry lands in the affected tenant's own log
        try:
            await audit.append(AuditEntry(actor="platform", role="platform", key_id=None, action=action, target=tenant_id, outcome="success", detail=detail))
        finally:
            TENANT.reset(token)

    async def view(t: Any) -> dict[str, Any]:
        token = TENANT.set(t.id)
        try:
            plan = (await settings_repo.get("plan")) or {}
            keys = len([k for k in await access.keys_of(t.id) if k.active()]) if access is not None else None
        finally:
            TENANT.reset(token)
        return {**t.to_dict(), "plan": plan.get("name"), "limits": await limits.effective(t.id), "activeKeys": keys, "bindings": [{"kind": b.kind, "address": b.address} for b in await tenants.repo.bindings(t.id)]}

    @app.get("/platform/health")
    async def health() -> Any:
        return {"ok": True}

    @app.get("/platform/v1/tenants")
    async def list_tenants() -> Any:
        return {"tenants": [await view(t) for t in await tenants.repo.list()]}

    @app.post("/platform/v1/tenants", status_code=201)
    async def create(body: TenantBody) -> Any:
        try:
            t = await tenants.create(body.id, body.name)
            if body.plan:
                await set_plan(t.id, body.plan)
        except TenantError as e:
            return err(409 if "already" in str(e) else 400, "bad_request", str(e))
        await note(t.id, "platform.tenant_created", name=t.name, plan=body.plan)
        return await view(t)

    @app.get("/platform/v1/tenants/{tenant_id}")
    async def get(tenant_id: str) -> Any:
        t = await tenants.repo.get(tenant_id)
        return await view(t) if t else err(404, "not_found", "Unknown tenant")

    async def set_status(tenant_id: str, status: str) -> Any:
        try:
            t = await tenants.set_status(tenant_id, status)
        except KeyError:
            return err(404, "not_found", "Unknown tenant")
        except TenantError as e:
            return err(400, "bad_request", str(e))
        await note(t.id, "platform.tenant_" + ("suspended" if status == "suspended" else "resumed"))
        return await view(t)

    @app.post("/platform/v1/tenants/{tenant_id}/suspend")
    async def suspend(tenant_id: str) -> Any:
        return await set_status(tenant_id, "suspended")

    @app.post("/platform/v1/tenants/{tenant_id}/resume")
    async def resume(tenant_id: str) -> Any:
        return await set_status(tenant_id, "active")

    async def set_plan(tenant_id: str, plan: str) -> None:
        if not PLAN_RE.fullmatch(plan.strip().lower()):
            raise TenantError("A plan name is up to 40 lower-case letters, digits, spaces, - _ or .")
        token = TENANT.set(tenant_id)
        try:
            await settings_repo.put("plan", {"name": plan.strip().lower()}, "platform")
        finally:
            TENANT.reset(token)

    @app.put("/platform/v1/tenants/{tenant_id}/plan")
    async def plan(tenant_id: str, body: PlanBody) -> Any:
        t = await tenants.repo.get(tenant_id)
        if t is None:
            return err(404, "not_found", "Unknown tenant")
        try:
            await set_plan(tenant_id, body.plan)
        except TenantError as e:
            return err(400, "bad_request", str(e))
        await note(tenant_id, "platform.plan_changed", plan=body.plan.strip().lower())
        return await view(t)

    @app.put("/platform/v1/tenants/{tenant_id}/limits")
    async def put_limits(tenant_id: str, request: Request) -> Any:
        t = await tenants.repo.get(tenant_id)
        if t is None:
            return err(404, "not_found", "Unknown tenant")
        try:
            body = await request.json()
            await limits.put(tenant_id, body, "platform")
        except LimitError as e:
            return err(400, "bad_request", str(e))
        except ValueError:
            return err(400, "bad_request", "The body must be JSON")
        await note(tenant_id, "platform.limits_changed", limits=sorted(body))
        return await view(t)

    @app.delete("/platform/v1/tenants/{tenant_id}/limits")
    async def clear_limits(tenant_id: str) -> Any:
        t = await tenants.repo.get(tenant_id)
        if t is None:
            return err(404, "not_found", "Unknown tenant")
        await limits.clear(tenant_id)
        await note(tenant_id, "platform.limits_cleared")
        return await view(t)

    @app.post("/platform/v1/tenants/{tenant_id}/bindings", status_code=201)
    async def bind(tenant_id: str, body: BindingBody) -> Any:
        try:
            b = await tenants.bind(tenant_id, body.kind, body.address)
        except KeyError:
            return err(404, "not_found", "Unknown tenant")
        except TenantError as e:
            return err(409 if "already" in str(e) else 400, "bad_request", str(e))
        await note(tenant_id, "platform.binding_added", kind=b.kind)
        return {"kind": b.kind, "address": b.address, "tenant": b.tenant_id}

    @app.delete("/platform/v1/tenants/{tenant_id}/bindings/{kind}/{address:path}")
    async def unbind(tenant_id: str, kind: str, address: str) -> Any:
        owner = await tenants.resolve(kind, address.strip().lower())
        if owner != tenant_id:
            return err(404, "not_found", "That tenant has no such binding")
        await tenants.repo.unbind(kind, address.strip().lower())
        await note(tenant_id, "platform.binding_removed", kind=kind)
        return {"removed": True}

    return app
