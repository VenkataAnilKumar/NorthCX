"""Telegram channel webhook."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.audit import AuditEntry

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    audit = d.audit
    limits = d.limits
    telegram = d.telegram
    too_many = d.too_many

    @app.post("/channels/telegram/webhook")
    async def telegram_inbound(request: Request) -> Any:
        """Public webhook for the Telegram bot. Authenticated by the secret token registered with setWebhook, never by an API key."""
        if telegram is None:
            return _err(501, "not_configured", "The Telegram channel is not configured")
        ip = request.client.host if request.client else "unknown"
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 262144:
                return _err(413, "too_large", "Request is too large")
        if not telegram.authentic(request.headers.get("x-telegram-bot-api-secret-token", "")):
            if limits and not (await access.limiter.hit(f"smsfail:{ip}", limits.auth_failures_per_minute))[0]:
                return too_many(60, "unsigned requests")
            if (await access.limiter.hit(f"smslog:{ip}", 6))[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/channels/telegram/webhook", outcome="denied", detail={"client": ip}))
            return _err(403, "forbidden", "Invalid secret")
        try:
            await telegram.receive_body(raw)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        except Exception:
            log.exception("telegram inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return {"status": "ok"}
