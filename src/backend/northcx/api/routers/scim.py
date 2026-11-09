"""SCIM 2.0 routes under /scim/v2, authenticated by their own bearer token (NORTHCX_SCIM_TOKEN), not by an API key."""
from __future__ import annotations

import hmac
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.access import hash_secret
from northcx.api.deps import AppDeps
from northcx.audit import AuditEntry
from northcx.scim import GROUP_SCHEMA, LIST_SCHEMA, USER_SCHEMA, ScimError

CT = "application/scim+json"


def register(app: FastAPI, d: AppDeps) -> None:
    access, audit = d.access, d.audit

    def reply(body: Any, status: int = 200) -> JSONResponse:
        return JSONResponse(body, status_code=status, media_type=CT)

    def fail(e: ScimError) -> JSONResponse:
        return reply(e.body(), e.status)

    async def guard(request: Request) -> Any:
        """The service when the bearer token is right, else the error response to send."""
        svc = getattr(access, "scim", None)
        if svc is None:
            return fail(ScimError(404, "SCIM provisioning is not configured"))
        ip = request.client.host if request.client else "unknown"
        h = request.headers.get("authorization", "")
        if not h.startswith("Bearer ") or not hmac.compare_digest(hash_secret(h[7:]), svc.token_hash):
            if d.limits and not (await access.limiter.hit(f"scimfail:{ip}", d.limits.auth_failures_per_minute))[0]:
                return fail(ScimError(429, "Too many failed attempts"))
            if (await access.limiter.hit(f"authlog:{ip}", 6))[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="scim.auth.failed", target=request.url.path, outcome="denied", detail={"client": ip}))
            return fail(ScimError(401, "Missing or invalid provisioning token"))
        if d.limits and not (await access.limiter.hit("scim", 6000))[0]:
            return fail(ScimError(429, "Too many requests"))
        return svc

    async def rec(action: str, target: str, **detail: Any) -> None:
        await audit.append(AuditEntry(actor="scim", role="provisioning", action=action, target=target, outcome="ok", detail=detail))

    async def body_of(request: Request) -> dict[str, Any]:
        try:
            b = await request.json()
        except ValueError as e:
            raise ScimError(400, "The body is not valid JSON", "invalidSyntax") from e
        if not isinstance(b, dict):
            raise ScimError(400, "The body must be a JSON object", "invalidSyntax")
        return b

    @app.get("/scim/v2/ServiceProviderConfig")
    async def spc(request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        return reply({"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"], "patch": {"supported": True}, "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
                      "filter": {"supported": True, "maxResults": 200}, "changePassword": {"supported": False}, "sort": {"supported": False}, "etag": {"supported": False},
                      "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token", "description": "A long random token (NORTHCX_SCIM_TOKEN)", "primary": True}]})

    @app.get("/scim/v2/ResourceTypes")
    async def resource_types(request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        return reply({"schemas": [LIST_SCHEMA], "totalResults": 2, "startIndex": 1, "itemsPerPage": 2, "Resources": [
            {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"], "id": "User", "name": "User", "endpoint": "/Users", "schema": USER_SCHEMA},
            {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"], "id": "Group", "name": "Group", "endpoint": "/Groups", "schema": GROUP_SCHEMA}]})

    @app.get("/scim/v2/Schemas")
    async def schemas(request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        return reply({"schemas": [LIST_SCHEMA], "totalResults": 2, "startIndex": 1, "itemsPerPage": 2, "Resources": [{"id": USER_SCHEMA, "name": "User"}, {"id": GROUP_SCHEMA, "name": "Group"}]})

    @app.post("/scim/v2/Users")
    async def create_user(request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            u = await s.create_user(await body_of(request), "scim")
        except ScimError as e:
            return fail(e)
        await rec("scim.user.create", u.user_name, id=u.id, active=u.active)
        return reply(s.user_json(u, await s.group_refs(u)), 201)

    @app.get("/scim/v2/Users")
    async def list_users(request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        q = request.query_params
        try:
            start, count = max(1, int(q.get("startIndex", 1))), min(200, max(0, int(q.get("count", 100))))
            items, total = await s.list_users(q.get("filter"), start, count)
        except ValueError:
            return fail(ScimError(400, "startIndex and count must be numbers", "invalidValue"))
        except ScimError as e:
            return fail(e)
        return reply({"schemas": [LIST_SCHEMA], "totalResults": total, "startIndex": start, "itemsPerPage": len(items),
                      "Resources": [s.user_json(u, await s.group_refs(u)) for u in items]})

    @app.get("/scim/v2/Users/{user_id}")
    async def get_user(user_id: str, request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        u = await s.users.get(user_id)
        return reply(s.user_json(u, await s.group_refs(u))) if u else fail(ScimError(404, "User not found"))

    async def after_change(s: Any, u: Any, deactivated: bool, action: str) -> None:
        ended = await s.end_access(u) if deactivated else 0
        await rec(action, u.user_name, id=u.id, active=u.active, sessionsRevoked=ended)

    @app.put("/scim/v2/Users/{user_id}")
    async def replace_user(user_id: str, request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            u, deactivated = await s.replace_user(user_id, await body_of(request))
        except ScimError as e:
            return fail(e)
        await after_change(s, u, deactivated, "scim.user.update")
        return reply(s.user_json(u, await s.group_refs(u)))

    @app.patch("/scim/v2/Users/{user_id}")
    async def patch_user(user_id: str, request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            u, deactivated = await s.patch_user(user_id, await body_of(request))
        except ScimError as e:
            return fail(e)
        await after_change(s, u, deactivated, "scim.user.update")
        return reply(s.user_json(u, await s.group_refs(u)))

    @app.delete("/scim/v2/Users/{user_id}")
    async def delete_user(user_id: str, request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            u = await s.delete_user(user_id)
        except ScimError as e:
            return fail(e)
        await after_change(s, u, True, "scim.user.delete")
        return JSONResponse(None, status_code=204)

    @app.post("/scim/v2/Groups")
    async def create_group(request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            g = await s.create_group(await body_of(request), "scim")
        except ScimError as e:
            return fail(e)
        await rec("scim.group.create", g.name, id=g.id)
        return reply(await s.group_json(g), 201)

    @app.get("/scim/v2/Groups")
    async def list_groups(request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        gs = await s.groups.repo.list()
        return reply({"schemas": [LIST_SCHEMA], "totalResults": len(gs), "startIndex": 1, "itemsPerPage": len(gs), "Resources": [await s.group_json(g) for g in gs]})

    @app.get("/scim/v2/Groups/{group_id}")
    async def get_group(group_id: str, request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        g = await s.groups.repo.get(group_id)
        return reply(await s.group_json(g)) if g else fail(ScimError(404, "Group not found"))

    @app.patch("/scim/v2/Groups/{group_id}")
    async def patch_group(group_id: str, request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            g = await s.patch_group(group_id, await body_of(request))
        except ScimError as e:
            return fail(e)
        await rec("scim.group.update", g.name, id=g.id, members=len(g.members))
        return reply(await s.group_json(g))

    @app.delete("/scim/v2/Groups/{group_id}")
    async def delete_group(group_id: str, request: Request) -> Any:
        s = await guard(request)
        if isinstance(s, JSONResponse):
            return s
        g = await s.groups.repo.get(group_id)
        if g is None:
            return fail(ScimError(404, "Group not found"))
        await s.groups.delete(group_id)
        await rec("scim.group.delete", g.name, id=g.id)
        return JSONResponse(None, status_code=204)
