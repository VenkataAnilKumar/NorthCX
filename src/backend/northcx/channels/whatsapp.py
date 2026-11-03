"""WhatsApp channel (C4), through the Meta Cloud API webhook shape.

It reuses the SMS conversation engine (opt-outs, rate limits, duplicate handling, hand-offs, privacy erasure), so a person
who texts and later messages on WhatsApp is the same customer. Only the provider differs: inbound requests are JSON signed
with the app secret (`X-Hub-Signature-256`), the webhook is verified once with a shared token, and replies go out through
the Graph API. Media is not read; a note tells the agent that an attachment arrived.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

import httpx

from .email import InboundResult
from .sms import PermanentSendError, SmsChannel, SmsConfig, SmsNotifier, SmsSendError, valid_number

_ID = re.compile(r"^[0-9]{5,20}$")
_CHALLENGE = re.compile(r"^[A-Za-z0-9_.~-]{1,200}$")


class WhatsAppProvider:
    def __init__(self, access_token: str, app_secret: str, verify_token: str, client: httpx.AsyncClient | None = None,
                 base_url: str = "https://graph.facebook.com/v21.0"):
        if not access_token or not app_secret or not verify_token:
            raise ValueError("WhatsApp needs NORTHCX_WHATSAPP_TOKEN, NORTHCX_WHATSAPP_APP_SECRET and NORTHCX_WHATSAPP_VERIFY_TOKEN")
        u = httpx.URL(base_url)
        if u.scheme != "https" and not (u.scheme == "http" and u.host in ("localhost", "127.0.0.1")):
            raise ValueError("the WhatsApp API address must be https")
        self.token, self.secret, self.verify_token, self.base = access_token, app_secret.encode(), verify_token, base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=False)

    def valid_body_signature(self, raw: bytes, header: str) -> bool:
        want = "sha256=" + hmac.new(self.secret, raw, hashlib.sha256).hexdigest()
        return bool(header) and hmac.compare_digest(want, header)

    def valid_verify_token(self, token: str) -> bool:
        return bool(token) and hmac.compare_digest(token.encode(), self.verify_token.encode())

    async def send(self, to: str, from_: str, body: str) -> str:
        if not _ID.match(from_):
            raise ValueError("invalid WhatsApp phone number id")
        try:
            r = await self._client.post(f"{self.base}/{from_}/messages", headers={"authorization": f"Bearer {self.token}"},
                                        json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"preview_url": False, "body": body}})
        except httpx.HTTPError as e:
            raise SmsSendError(f"could not send message: {type(e).__name__}") from e
        if 400 <= r.status_code < 500 and r.status_code != 429:  # includes the closed 24-hour reply window and unreachable numbers
            raise PermanentSendError(f"the message was refused by WhatsApp ({r.status_code})")
        if r.status_code >= 300:
            raise SmsSendError(f"could not send message: provider returned {r.status_code}")
        try:
            return str(r.json()["messages"][0]["id"])
        except (ValueError, KeyError, IndexError, TypeError):
            return ""


def parse_webhook(raw: bytes) -> list[dict[str, Any]]:
    """The messages in a webhook call: id, sender number (+digits), our number id, text and attachment count. Delivery receipts are skipped."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError("unreadable request") from None
    if not isinstance(data, dict) or data.get("object") != "whatsapp_business_account":
        raise ValueError("not a WhatsApp webhook")
    out: list[dict[str, Any]] = []
    for entry in data.get("entry") or []:
        for change in (entry.get("changes") or []) if isinstance(entry, dict) else []:
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            to = str((value.get("metadata") or {}).get("phone_number_id", ""))
            for m in value.get("messages") or []:
                if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not _ID.match(str(m.get("from", ""))):
                    continue
                text = ((m.get("text") or {}).get("body") if m.get("type") == "text" else None) or ""
                if m.get("type") == "button":
                    text = (m.get("button") or {}).get("text") or ""
                elif m.get("type") == "interactive":
                    r = (m.get("interactive") or {})
                    text = ((r.get("button_reply") or r.get("list_reply") or {}).get("title")) or ""
                out.append({"id": m["id"][:200], "phone": "+" + m["from"], "to": to, "text": str(text),
                            "media": 0 if m.get("type") in ("text", "button", "interactive", "reaction") else 1})
    return out


class WhatsAppNotifier(SmsNotifier):
    SPLIT = 3500


class WhatsAppChannel(SmsChannel):
    CHANNEL, PREFIX, REPLY_KIND = "whatsapp", "wa-", "whatsapp_reply"

    def __init__(self, runtime: Any, agents: Any, repo: Any, provider: WhatsAppProvider, config: SmsConfig):
        super().__init__(runtime, agents, repo, provider, config)  # config.from_number is the WhatsApp phone number id

    def authentic(self, raw: bytes, signature: str) -> bool:  # type: ignore[override]
        return self.provider.valid_body_signature(raw, signature)

    async def receive_body(self, raw: bytes) -> list[InboundResult]:
        results = []
        for m in parse_webhook(raw):
            if m["to"] != self.config.from_number or not valid_number(m["phone"]):
                continue
            key = "wa:" + m["id"]
            async with self._lock(f"msg:{key}"):
                if await self.repo.has_message(key):
                    results.append(InboundResult("duplicate", reason="already handled"))
                    continue
                res = await self._handle(m["phone"], m["text"].strip(), m["media"])
                outcome = res.status if res.status != "ignored" else f"ignored:{res.reason}"
                from .sms import phone_hash
                await self.repo.record_message(key, res.session_id or "-", "in", outcome[:32], m["phone"] if res.session_id else phone_hash(m["phone"])[:20])
                results.append(res)
        return results
