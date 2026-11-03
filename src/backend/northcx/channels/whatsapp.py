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
from ..attachments import AttachmentError, accept as accept_attachment, check_accepted
from .sms import PermanentSendError, SmsChannel, SmsConfig, SmsNotifier, SmsSendError, phone_hash, valid_number

_ID = re.compile(r"^[0-9]{5,20}$")
MEDIA_HOSTS = (".fbsbx.com", ".facebook.com", ".fbcdn.net", ".whatsapp.net", ".whatsapp.com")
MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_MEDIA_PER_MESSAGE = 3
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

    async def send_template(self, to: str, from_: str, name: str, language: str, params: list[str]) -> str:
        if not _ID.match(from_):
            raise ValueError("invalid WhatsApp phone number id")
        components = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}] if params else []
        try:
            r = await self._client.post(f"{self.base}/{from_}/messages", headers={"authorization": f"Bearer {self.token}"},
                                        json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template", "template": {"name": name, "language": {"code": language}, "components": components}})
        except httpx.HTTPError as e:
            raise SmsSendError(f"could not send message: {type(e).__name__}") from None
        if 400 <= r.status_code < 500 and r.status_code != 429:
            raise PermanentSendError(f"the template message was refused by WhatsApp ({r.status_code})")
        if r.status_code >= 300:
            raise SmsSendError(f"could not send message: provider returned {r.status_code}")
        try:
            return str(r.json()["messages"][0]["id"])
        except (ValueError, KeyError, IndexError, TypeError):
            return ""

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


def _media_ok(url: str) -> bool:
    u = httpx.URL(url)
    return u.scheme == "https" and bool(u.host) and not u.userinfo and any(u.host == h[1:] or u.host.endswith(h) for h in MEDIA_HOSTS)


async def _download(self: "WhatsAppProvider", media_id: str) -> tuple[bytes, str]:
    """A customer's file: look the address up with the Graph API, then fetch it from a Meta host. Never from any other host."""
    if not _ID.match(media_id):
        raise SmsSendError("invalid media id")
    headers = {"authorization": f"Bearer {self.token}"}
    try:
        r = await self._client.get(f"{self.base}/{media_id}", headers=headers)
        if r.status_code != 200:
            raise SmsSendError(f"media lookup returned {r.status_code}")
        info = r.json()
        url = str(info.get("url", ""))
        if not _media_ok(url):
            raise SmsSendError("the media address is not a WhatsApp address")
        data = b""
        async with self._client.stream("GET", url, headers=headers) as resp:
            if resp.status_code != 200:
                raise SmsSendError(f"media download returned {resp.status_code}")
            async for chunk in resp.aiter_bytes():
                data += chunk
                if len(data) > MAX_MEDIA_BYTES:
                    raise SmsSendError("the file is too large")
    except httpx.HTTPError as e:
        raise SmsSendError(f"could not fetch the file: {type(e).__name__}") from None
    except ValueError:
        raise SmsSendError("unreadable media reply") from None
    return data, str(info.get("mime_type", ""))[:100]


WhatsAppProvider.download = _download  # type: ignore[attr-defined]


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
                kind = m.get("type")
                item = m.get(kind) if kind in ("image", "document") and isinstance(m.get(kind), dict) else None
                if item is not None:
                    text = text or str(item.get("caption") or "")
                out.append({"id": m["id"][:200], "phone": "+" + m["from"], "to": to, "text": str(text),
                            "media": 0 if kind in ("text", "button", "interactive", "reaction") else 1,
                            "items": [{"id": str(item.get("id", "")), "filename": str(item.get("filename") or "")[:100]}] if item is not None and _ID.match(str(item.get("id", ""))) else []})
    return out


class _OneNumber(SmsNotifier):
    SPLIT = 3500


class WhatsAppNotifier:
    """Delivers replies for every configured number: each conversation goes out from the number it came in on."""

    def __init__(self, repo: Any, provider: Any, configs: "SmsConfig | dict[str, SmsConfig]"):
        cfgs = {configs.from_number: configs} if isinstance(configs, SmsConfig) else dict(configs)
        self.repo = repo
        self._by_number = {n: _OneNumber(repo, provider, c) for n, c in cfgs.items()}

    async def deliver(self, message: Any) -> None:
        session = await self.repo.get_session(message.session_id)
        one = self._by_number.get(session.our_number) if session is not None else None
        if one is not None:
            await one.deliver(message)


class TemplateRefused(ValueError):
    """A template message that must not be sent. The message is safe to show."""


class WhatsAppChannel(SmsChannel):
    CHANNEL, PREFIX, REPLY_KIND = "whatsapp", "wa-", "whatsapp_reply"

    def __init__(self, runtime: Any, agents: Any, repo: Any, provider: WhatsAppProvider, config: "SmsConfig | dict[str, SmsConfig]",
                 attachments: Any = None, scanner: Any = None, templates: dict[str, str] | None = None, optin: set[str] | None = None):
        self.configs = {config.from_number: config} if isinstance(config, SmsConfig) else dict(config)
        super().__init__(runtime, agents, repo, provider, next(iter(self.configs.values())))  # each config's from_number is a WhatsApp phone number id
        self.attachment_repo, self.scanner = attachments, scanner
        self.templates, self.optin = dict(templates or {}), set(optin or ())

    def authentic(self, raw: bytes, signature: str) -> bool:  # type: ignore[override]
        return self.provider.valid_body_signature(raw, signature)

    async def _attachments(self, session_id: str, agent: Any, items: list[Any]) -> tuple[list[Any], str | None]:
        if not items:
            return [], None
        if self.attachment_repo is None or not getattr(agent, "attachments", None):
            return [], "The customer sent a file, but this assistant does not read attachments"
        found, notes = [], []
        for item in items[:MAX_MEDIA_PER_MESSAGE]:
            try:
                data, _mime = await self.provider.download(item["id"])
                a = await accept_attachment(self.attachment_repo, session_id, item.get("filename") or None, data, "whatsapp", self.scanner)
                check_accepted([a], agent.attachments)
                found.append(a)
            except AttachmentError as e:
                notes.append(str(e))
            except SmsSendError:
                notes.append("a file could not be fetched")
        return found, ("; ".join(dict.fromkeys(notes)) + " (the file was not used)") if notes else None

    async def receive_body(self, raw: bytes) -> list[InboundResult]:
        results = []
        for m in parse_webhook(raw):
            cfg = self.configs.get(m["to"])
            if cfg is None or not valid_number(m["phone"]):
                continue
            key = "wa:" + m["id"]
            async with self._lock(f"msg:{key}"):
                if await self.repo.has_message(key):
                    results.append(InboundResult("duplicate", reason="already handled"))
                    continue
                res = await self._handle(m["phone"], m["text"].strip(), m["media"], cfg, m.get("items"))
                outcome = res.status if res.status != "ignored" else f"ignored:{res.reason}"
                await self.repo.record_message(key, res.session_id or "-", "in", outcome[:32], m["phone"] if res.session_id else phone_hash(m["phone"])[:20])
                results.append(res)
        return results

    async def send_template(self, phone_id: str | None, to: str, template: str, params: list[str]) -> str:
        """Start or resume a conversation with an approved template. Only to someone who has already messaged this number or is on the opt-in list,
        never to someone who opted out, and within the hourly reply limit."""
        cfg = self.configs.get(phone_id) if phone_id else self.config
        if cfg is None:
            raise TemplateRefused("Unknown WhatsApp number")
        language = self.templates.get(template)
        if language is None:
            raise TemplateRefused("That template is not on the list of approved templates")
        if not valid_number(to):
            raise TemplateRefused("The recipient must be a phone number in international format")
        if len(params) > 10 or any(len(p) > 200 for p in params):
            raise TemplateRefused("Too many or too long template parameters")
        if await self.repo.is_opted_out(to):
            raise TemplateRefused("This person has opted out")
        known = await self.repo.latest_session(to, cfg.from_number) is not None
        if not known and to not in self.optin:
            raise TemplateRefused("This person has not messaged this number and is not on the opt-in list")
        import time as _t
        if await self.repo.recent_count(to, "out", _t.time() - 3600) >= cfg.max_replies_per_number_per_hour:
            raise TemplateRefused("Too many messages to this person in the last hour")
        mid = await self.provider.send_template(to, cfg.from_number, template, language, params)
        import uuid as _u
        await self.repo.record_message(f"tpl:{_u.uuid4().hex}", "-", "out", "template", to)
        return mid
