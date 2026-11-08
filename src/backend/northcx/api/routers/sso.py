"""Single sign-on routes (outside /v1: the identity provider, not a key, authenticates them)."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.audit import AuditEntry
from northcx.sso import SsoError


def register(app: FastAPI, d: AppDeps) -> None:
    SSO_COOKIE = d.SSO_COOKIE
    access = d.access
    audit = d.audit
    secure_cookie = d.secure_cookie
    sso = d.sso
    too_many = d.too_many

    @app.get("/auth/sso/config")
    async def sso_config() -> Any:
        return {"enabled": sso is not None, "loginUrl": "/auth/sso/login" if sso else None}

    async def sso_failed(request: Request, e: SsoError) -> RedirectResponse:
        ip = request.client.host if request.client else "unknown"
        await audit.append(AuditEntry(actor="unknown", role="none", action="sso.denied", target="login", outcome="denied", detail={"client": ip, "reason": e.detail[:200]}))
        resp = RedirectResponse(f"{sso.cfg.landing}?{urlencode({'error': str(e)})}", status_code=303)
        resp.delete_cookie(SSO_COOKIE, path="/")
        return resp

    @app.get("/auth/sso/login")
    async def sso_login(request: Request) -> Any:
        if sso is None:
            return _err(404, "not_found", "Single sign-on is not configured")
        ip = request.client.host if request.client else "unknown"
        if not (await access.limiter.hit(f"sso:{ip}", 20))[0]:
            return too_many(60, "sign-in attempts")
        try:
            url, cookie = await sso.begin()
        except SsoError as e:
            return await sso_failed(request, e)
        resp = RedirectResponse(url, status_code=303)
        resp.set_cookie(SSO_COOKIE, cookie, max_age=600, httponly=True, samesite="lax", secure=secure_cookie, path="/")
        return resp

    @app.get("/auth/sso/callback")
    async def sso_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> Any:
        if sso is None:
            return _err(404, "not_found", "Single sign-on is not configured")
        ip = request.client.host if request.client else "unknown"
        if not (await access.limiter.hit(f"sso:{ip}", 20))[0]:
            return too_many(60, "sign-in attempts")
        if error:
            return await sso_failed(request, SsoError("The identity provider did not complete the sign-in", f"provider error: {error[:60]}"))
        try:
            login = await sso.finish(code, state, request.cookies.get(SSO_COOKIE))
            key, token = await access.issue_session(login.email, login.role, sso.cfg.session_hours)
        except SsoError as e:
            return await sso_failed(request, e)
        await audit.append(AuditEntry(actor=login.email, role=login.role, action="sso.login", target=f"ncx_{key.key_id}", outcome="ok",
                                      detail={"subject": login.subject, "client": ip, "expiresAt": key.expires_at}))
        resp = RedirectResponse(f"{sso.cfg.landing}#token={token}", status_code=303)  # in the fragment, so it is never sent to a server or logged
        resp.delete_cookie(SSO_COOKIE, path="/")
        resp.headers["cache-control"] = "no-store"
        return resp
