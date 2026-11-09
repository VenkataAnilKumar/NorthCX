"""Helpers every router uses: rate-limit responses, who is acting, audit recording, release guards."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from northcx.access import OPEN_IDENTITY, Identity
from northcx.api.common import _err
from northcx.audit import AuditEntry, AuditRepo
from northcx.versions import Conflict, GateBlocked, NotFound, ReleaseService, check_environment, spec_yaml

log = logging.getLogger("northcx.server")  # the same logger the audit-failure message has always used


def too_many(retry: float, what: str) -> JSONResponse:
    r = _err(429, "rate_limited", f"Too many {what}; retry in {max(1, round(retry))} s")
    r.headers["Retry-After"] = str(max(1, round(retry)))
    return r


def actor(request: Request, claimed: str | None) -> str:
    """Who is acting. With authentication it is the key's name; a name in the body is only trusted without it."""
    who: Identity = request.state.identity
    return (claimed.strip() if claimed and claimed.strip() else "anonymous") if who.open_mode else who.name


def version_json(v: Any, live_number: int | None = None, released: set[int] | None = None, full: bool = False) -> dict[str, Any]:
    out = {"id": v.id, "agentId": v.agent_id, "number": v.number, "digest": v.digest, "author": v.author, "note": v.note,
           "createdAt": v.created_at, "live": live_number == v.number, "everReleased": v.number in (released or set())}
    if full:
        out["spec"] = v.spec
        out["specYaml"] = spec_yaml(v.spec)
    return out


def rel_error(e: Exception) -> JSONResponse:
    if isinstance(e, NotFound):
        return _err(404, "not_found", str(e))
    if isinstance(e, GateBlocked):
        resp = _err(409, "gate_not_satisfied", str(e))
        resp.body = json.dumps({"error": {"code": "gate_not_satisfied", "message": str(e), "reasons": e.reasons}}).encode()
        resp.headers["content-length"] = str(len(resp.body))
        return resp
    if isinstance(e, Conflict):
        return _err(409, "conflict", str(e))
    return _err(400, "bad_request", str(e))


def make_guards(audit: AuditRepo, releases: ReleaseService | None):
    """The three helpers that need the audit log or the release service. Returns (record, need_rel, need_env)."""

    async def record(request: Request | None, action: str, target: str = "", outcome: str = "success", **detail: Any) -> None:
        """Write an audit entry for the caller. A failure to record is raised: a privileged action must not go unrecorded."""
        who: Identity = getattr(request.state, "identity", OPEN_IDENTITY) if request is not None else OPEN_IDENTITY
        try:
            await audit.append(AuditEntry(actor=who.name, role=who.role, key_id=who.key_id, action=action, target=target,
                                          outcome=outcome, detail=detail))
        except Exception:
            log.exception("AUDIT FAILURE: could not record %s on %s", action, target)
            raise

    def need_rel() -> ReleaseService | JSONResponse:
        return releases or _err(501, "not_configured", "Versions and releases are not configured on this server")

    async def need_env(request: Request, environment: str, perm: str) -> JSONResponse | None:
        """Dev and staging are for developers; production needs the release permission."""
        try:
            check_environment(environment)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        who: Identity = request.state.identity
        if not who.allows_env(environment):
            await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", environment=environment)
            return _err(403, "forbidden", f"This key is limited to the {', '.join(who.scope_envs or ())} environment(s)")
        if environment == "production" and not who.can(perm):
            await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", permission=perm)
            return _err(403, "forbidden", f"The '{who.role}' role cannot do this (needs {perm})")
        return None

    return record, need_rel, need_env
