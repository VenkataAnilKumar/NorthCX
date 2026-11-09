"""Routes for the caller's identity, API keys and the audit log."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx import __version__
from northcx.access import Identity, ROLES, SSO_CREATOR
from northcx.tenancy import DEFAULT_TENANT
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import KeyBody


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    actor = d.actor
    audit = d.audit
    record = d.record

    # ---------------- identity, keys and audit ----------------
    @app.get("/v1/me")
    async def me(request: Request) -> Any:
        who: Identity = request.state.identity
        return {"name": who.name, "role": who.role, "openMode": who.open_mode, "keyId": who.key_id,
                "permissions": sorted(who.permissions), "serverVersion": __version__, "tenant": who.tenant, "roles": [who.role, *who.extra_roles],
                "agents": list(who.scope_agents) if who.scope_agents is not None else None, "environments": list(who.scope_envs) if who.scope_envs is not None else None}

    @app.get("/v1/tenant/limits")
    async def tenant_limits(request: Request) -> Any:
        """The ceilings that apply to this organization and where each comes from. Read-only: the platform operator sets them."""
        tl = getattr(d.runtime, "tenant_limits", None)
        return {"tenant": request.state.identity.tenant, "limits": await tl.effective(request.state.identity.tenant) if tl is not None else {}}

    @app.post("/v1/me/logout")
    async def logout(request: Request) -> Any:
        """End a single-sign-on session now. Other kinds of key are left alone (revoke those on the Access page)."""
        who: Identity = request.state.identity
        key = await access.keys.get(who.key_id) if who.key_id else None
        if key is None or key.created_by != SSO_CREATOR or not key.active():
            return {"revoked": False}
        await access.revoke(key.key_id, who.name)
        await record(request, "sso.logout", who.name)
        return {"revoked": True}

    def key_json(k: Any) -> dict[str, Any]:
        return {"id": k.key_id, "prefix": k.prefix, "name": k.name, "role": k.role, "createdBy": k.created_by,
                "createdAt": k.created_at, "expiresAt": k.expires_at, "revokedAt": k.revoked_at, "revokedBy": k.revoked_by,
                "lastUsedAt": k.last_used_at, "active": k.active(), "agents": k.agents, "environments": k.environments}

    @app.get("/v1/keys")
    async def list_keys(request: Request) -> Any:
        return {"roles": {r: sorted(p) for r, p in ROLES.items()}, "keys": [key_json(k) for k in await access.keys_of(request.state.identity.tenant)]}

    @app.post("/v1/keys", status_code=201)
    async def create_key(body: KeyBody, request: Request) -> Any:
        try:
            key, secret = await access.issue(body.name, body.role, actor(request, None), body.expires_in_days, body.agents, body.environments, request.state.identity.tenant)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "key.create", key.prefix, name=key.name, role=key.role, expires=key.expires_at, agents=key.agents, environments=key.environments)
        return JSONResponse({**key_json(key), "key": secret}, status_code=201)  # the only time the secret is shown

    @app.post("/v1/keys/{key_id}/revoke")
    async def revoke_key(key_id: str, request: Request) -> Any:
        try:
            key = await access.revoke(key_id, actor(request, None), request.state.identity.tenant)
        except KeyError:
            return _err(404, "not_found", "Unknown key")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        await record(request, "key.revoke", key.prefix, name=key.name, role=key.role)
        return key_json(key)

    @app.get("/v1/audit")
    async def audit_log(request: Request, limit: int = 100, before: int | None = None, actor_name: str | None = None, action: str | None = None) -> Any:
        rows = await audit.list(max(1, min(limit, 500)), before, actor_name, action, request.state.identity.tenant)
        return {"entries": [{"id": e.id, "at": e.at, "actor": e.actor, "role": e.role, "keyId": e.key_id, "action": e.action,
                             "target": e.target, "outcome": e.outcome, "detail": e.detail} for e in rows]}

    @app.get("/v1/audit/verify")
    async def audit_verify(request: Request) -> Any:
        v = await audit.verify()
        if request.state.identity.tenant != DEFAULT_TENANT:  # the chain runs through every tenant's entries, so a tenant learns only whether it holds
            return {"ok": v.ok}
        return {"ok": v.ok, "checked": v.checked, "brokenAt": v.broken_at, "reason": v.reason, "head": v.head}
