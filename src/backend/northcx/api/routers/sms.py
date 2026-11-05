"""SMS channel webhook."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.audit import AuditEntry
from northcx.channels.sms import parse_form

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    audit = d.audit
    limits = d.limits
    sms = d.sms
    too_many = d.too_many

    # ---------------- SMS ----------------
    @app.post("/channels/sms/twilio")
    async def sms_inbound(request: Request) -> Any:
        """Public webhook for the SMS provider. It is not behind an API key: every request must carry the provider's signature."""
        if sms is None:
            return _err(501, "not_configured", "The SMS channel is not configured")
        ip = request.client.host if request.client else "unknown"
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 65536:
                return _err(413, "too_large", "Request is too large")
        try:
            params = parse_form(raw)
        except ValueError:
            return _err(400, "bad_request", "Unreadable request")
        if not sms.authentic(params, request.headers.get("x-twilio-signature", "")):
            if limits and not access.limiter.allow(f"smsfail:{ip}", limits.auth_failures_per_minute)[0]:
                return too_many(60, "unsigned requests")  # only failures count, so real traffic is never throttled by this
            if access.limiter.allow(f"smslog:{ip}", 6)[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/channels/sms/twilio", outcome="denied", detail={"client": ip}))
            return _err(403, "forbidden", "Invalid signature")
        try:
            await sms.receive(params)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        except Exception:
            log.exception("sms inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return Response(content="<Response></Response>", media_type="text/xml")  # replies go out through the outbox
