"""WhatsApp channel routes: the signed webhook, its one-time verification and approved template messages."""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response

from northcx.access import Identity
from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import TemplateSendBody
from northcx.audit import AuditEntry
from northcx.tenancy import TENANT
from northcx.channels.sms import phone_hash
from northcx.channels.whatsapp import TemplateRefused, parse_webhook

log = logging.getLogger("northcx.server")


def register(app: FastAPI, d: AppDeps) -> None:
    access = d.access
    audit = d.audit
    limits = d.limits
    record = d.record
    too_many = d.too_many
    whatsapp = d.whatsapp

    # ---------------- WhatsApp ----------------
    @app.get("/channels/whatsapp/meta")
    async def whatsapp_verify(request: Request) -> Any:
        """One-time webhook check by Meta: echoes the challenge only when the shared verify token matches."""
        q = request.query_params
        if whatsapp is None:
            return _err(501, "not_configured", "The WhatsApp channel is not configured")
        challenge = q.get("hub.challenge", "")
        if q.get("hub.mode") != "subscribe" or not whatsapp.provider.valid_verify_token(q.get("hub.verify_token", "")) or not re.fullmatch(r"[0-9A-Za-z_.~-]{1,200}", challenge):
            return _err(403, "forbidden", "Verification failed")
        return Response(content=challenge, media_type="text/plain")

    @app.post("/channels/whatsapp/meta")
    async def whatsapp_inbound(request: Request) -> Any:
        """Public webhook for WhatsApp. Authenticated by the body signature, never by an API key."""
        if whatsapp is None:
            return _err(501, "not_configured", "The WhatsApp channel is not configured")
        ip = request.client.host if request.client else "unknown"
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 262144:
                return _err(413, "too_large", "Request is too large")
        if not whatsapp.authentic(raw, request.headers.get("x-hub-signature-256", "")):
            if limits and not (await access.limiter.hit(f"smsfail:{ip}", limits.auth_failures_per_minute))[0]:
                return too_many(60, "unsigned requests")
            if (await access.limiter.hit(f"smslog:{ip}", 6))[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/channels/whatsapp/meta", outcome="denied", detail={"client": ip}))
            return _err(403, "forbidden", "Invalid signature")
        if access.tenants is not None:  # the tenant that owns the WhatsApp number each message was sent to (WP2.6)
            try:
                tenants = {await access.tenants.inbound_tenant("whatsapp", m["to"]) for m in parse_webhook(raw)}
            except ValueError as e:
                return _err(400, "bad_request", str(e))
            if len(tenants) > 1:
                return _err(400, "bad_request", "One webhook body must be for numbers of one tenant")
            if tenants:
                tenant = tenants.pop()
                if tenant is None:
                    return {"status": "ignored"}
                TENANT.set(tenant)
        try:
            await whatsapp.receive_body(raw)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        except Exception:
            log.exception("whatsapp inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return {"status": "ok"}

    # ---------------- Telegram ----------------
    @app.post("/v1/channels/whatsapp/templates/send")
    async def whatsapp_template(body: TemplateSendBody, request: Request) -> Any:
        """Send an approved WhatsApp template (for example to reach someone after the 24-hour window). Only to people who already messaged that number or are on the opt-in list."""
        if whatsapp is None:
            return _err(501, "not_configured", "The WhatsApp channel is not configured")
        who: Identity = request.state.identity
        if not (await access.limiter.hit(f"watemplate:{who.key_id or 'open'}", 60))[0]:
            return too_many(60, "template messages")
        try:
            mid = await whatsapp.send_template(body.phone_id, body.to, body.template, body.params)
        except TemplateRefused as e:
            return _err(403, "not_allowed", str(e))
        except Exception as e:
            from northcx.channels.sms import PermanentSendError
            if isinstance(e, PermanentSendError):
                return _err(422, "refused_by_provider", str(e))
            log.exception("whatsapp template failed")
            return _err(502, "provider_unavailable", "WhatsApp could not be reached; try again")
        await record(request, "whatsapp.template", body.template, to=phone_hash(body.to)[:12])
        return {"sent": True, "messageId": mid}
