"""Email channel route."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request

from northcx.api.common import _err
from northcx.tenancy import TENANT
from northcx.api.deps import AppDeps
from northcx.channels.email import EmailParseError

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    MAX_EMAIL_BYTES = d.MAX_EMAIL_BYTES
    email = d.email

    @app.post("/v1/channels/email/inbound")
    async def email_inbound(request: Request) -> Any:
        """The company's mail system forwards each raw message here (Content-Type message/rfc822)."""
        if email is None:
            return _err(501, "not_configured", "The email channel is not configured (set NORTHCX_EMAIL_FROM and NORTHCX_SMTP_URL)")
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_EMAIL_BYTES:
            return _err(413, "too_large", "Message is too large")
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_EMAIL_BYTES:
                return _err(413, "too_large", "Message is too large")
        tenants = d.access.tenants
        if tenants is not None:  # the recipient's domain belongs to a tenant; a tenant's own channel key may only deliver to its own domains (WP2.6)
            from email import policy
            from email.parser import BytesParser
            from email.utils import getaddresses
            head = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
            domains = {a.rpartition("@")[2].lower() for _, a in getaddresses([str(head.get("To", "")), str(head.get("Delivered-To", ""))]) if "@" in a}
            owners = {await tenants.inbound_tenant("email_domain", dom, request.state.identity.tenant) for dom in domains} or {request.state.identity.tenant}
            if len(owners) != 1 or None in owners:
                return {"status": "ignored", "reason": "no tenant owns this recipient"}
            TENANT.set(owners.pop())
        try:
            res = await email.receive(raw)
        except EmailParseError as e:
            return _err(400, "bad_message", str(e))
        except Exception:
            log.exception("email inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return {"status": res.status, "sessionId": res.session_id, "reason": res.reason, "traceId": res.trace_id,
                "handoffId": res.handoff_id}
