"""SMS channel (C4). The phone number is the conversation and, because the carrier network vouches for it, the customer.

Providers sit behind a small interface (`valid_signature`, `send`); a Twilio-compatible one is included. Inbound texts
arrive at a public webhook that is authenticated by the provider's signature, not by an API key.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import parse_qsl

import httpx

from ..choices import WHATSAPP_BODY, numbered
from ..outbox import OutboxMessage
from ..runtime import Runtime
from ..catalog import AgentUnavailable, as_provider
from .email import InboundResult

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
START_WORDS = {"start", "unstop"}
HELP_WORDS = {"help", "info"}
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def valid_number(n: str) -> bool:
    return bool(_E164.match(n or ""))


def phone_hash(n: str) -> str:
    return hashlib.sha256(("sms:" + n).encode()).hexdigest()


def parse_form(body: bytes, limit: int = 65536) -> dict[str, str]:
    if len(body) > limit:
        raise ValueError("request too large")
    return {k: v for k, v in parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True)}


def split_sms(text: str, limit: int = 1500, max_parts: int = 3) -> list[str]:
    """Split a reply into messages of at most `limit` characters at sentence or word ends; the rest is cut with an ellipsis."""
    text = text.strip()
    parts: list[str] = []
    while text and len(parts) < max_parts:
        if len(text) <= limit:
            parts.append(text)
            text = ""
            break
        cut = max(text.rfind(". ", 0, limit), text.rfind("\n", 0, limit))
        cut = cut + 1 if cut > limit // 2 else text.rfind(" ", 0, limit)
        cut = cut if cut > limit // 4 else limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts[-1] = parts[-1][: limit - 1].rstrip() + "…"
    return parts


class SmsProvider(Protocol):
    def valid_signature(self, url: str, params: dict[str, str], signature: str) -> bool: ...
    async def send(self, to: str, from_: str, body: str) -> str: ...


class SmsSendError(RuntimeError):
    pass


class PermanentSendError(SmsSendError):
    """The provider refused this message for good (for example a closed reply window); retrying would never succeed."""


class TwilioProvider:
    """Twilio-compatible: webhook signature is HMAC-SHA1 of the URL plus the sorted form fields; sending uses the Messages API."""

    def __init__(self, account_sid: str, auth_token: str, client: httpx.AsyncClient | None = None, base_url: str = "https://api.twilio.com"):
        if not account_sid or not auth_token:
            raise ValueError("SMS needs NORTHCX_SMS_ACCOUNT_SID and NORTHCX_SMS_AUTH_TOKEN")
        self.sid, self.token, self.base = account_sid, auth_token, base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=False)

    def expected_signature(self, url: str, params: dict[str, str]) -> str:
        data = url + "".join(k + params[k] for k in sorted(params))
        return base64.b64encode(hmac.new(self.token.encode(), data.encode(), hashlib.sha1).digest()).decode()

    def valid_signature(self, url: str, params: dict[str, str], signature: str) -> bool:
        return bool(signature) and hmac.compare_digest(self.expected_signature(url, params), signature)

    async def send(self, to: str, from_: str, body: str) -> str:
        try:
            r = await self._client.post(f"{self.base}/2010-04-01/Accounts/{self.sid}/Messages.json", auth=(self.sid, self.token),
                                        data={"To": to, "From": from_, "Body": body})
        except httpx.HTTPError as e:
            raise SmsSendError(f"could not send text: {type(e).__name__}") from e
        if r.status_code >= 300:
            raise SmsSendError(f"could not send text: provider returned {r.status_code}")
        try:
            return str(r.json().get("sid", ""))
        except ValueError:
            return ""


@dataclass
class SmsConfig:
    from_number: str
    agent_id: str = "support"
    session_idle_hours: float = 24.0
    max_replies_per_number_per_hour: int = 20
    help_text: str = "Reply with your question and our assistant will help. Reply STOP to unsubscribe."
    webhook_url: str = ""  # the exact public URL configured with the provider; it is part of the signed data
    max_chars: int = 1000  # longest inbound text passed to the agent


@dataclass
class SmsSession:
    session_id: str
    phone: str
    our_number: str
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    @property
    def customer_id(self) -> str:
        return f"phone:{self.phone}" if self.phone.startswith("+") else self.phone  # other messaging apps use their own prefix, such as tg:123


class SmsRepo(Protocol):
    async def latest_session(self, phone: str, our_number: str) -> SmsSession | None: ...
    async def get_session(self, session_id: str) -> SmsSession | None: ...
    async def save_session(self, session: SmsSession) -> None: ...
    async def has_message(self, message_id: str) -> bool: ...
    async def record_message(self, message_id: str, session_id: str, direction: str, outcome: str, peer: str) -> bool: ...
    async def recent_count(self, peer: str, direction: str, since: float) -> int: ...
    async def set_opt_out(self, phone: str, opted_out: bool) -> None: ...
    async def is_opted_out(self, phone: str) -> bool: ...


class InMemorySmsRepo:
    def __init__(self) -> None:
        self.sessions: dict[str, SmsSession] = {}
        self.messages: dict[str, dict[str, Any]] = {}
        self.opt_outs: set[str] = set()

    async def latest_session(self, phone, our_number) -> SmsSession | None:
        c = [s for s in self.sessions.values() if s.phone == phone and s.our_number == our_number]
        return max(c, key=lambda s: s.last_seen) if c else None

    async def get_session(self, session_id) -> SmsSession | None:
        return self.sessions.get(session_id)

    async def save_session(self, session) -> None:
        self.sessions[session.session_id] = session

    async def has_message(self, message_id) -> bool:
        return message_id in self.messages

    async def record_message(self, message_id, session_id, direction, outcome, peer) -> bool:
        if message_id in self.messages:
            return False
        self.messages[message_id] = {"session_id": session_id, "direction": direction, "outcome": outcome, "peer": peer, "at": time.time()}
        return True

    async def recent_count(self, peer, direction, since) -> int:
        return sum(1 for m in self.messages.values() if m["peer"] == peer and m["direction"] == direction and m["at"] >= since)

    async def set_opt_out(self, phone, opted_out) -> None:
        (self.opt_outs.add if opted_out else self.opt_outs.discard)(phone_hash(phone))

    async def is_opted_out(self, phone) -> bool:
        return phone_hash(phone) in self.opt_outs


class SmsNotifier:
    SPLIT = 1500
    """Delivers outbox messages that belong to SMS conversations (replies, approval results, hand-off notices) as texts."""

    def __init__(self, repo: SmsRepo, provider: SmsProvider, config: SmsConfig):
        self.repo, self.provider, self.config = repo, provider, config

    async def deliver(self, message: OutboxMessage) -> None:
        session = await self.repo.get_session(message.session_id)
        body = message.payload.get("reply")
        choices = message.payload.get("choices") or []
        if session is None or not body or session.our_number != self.config.from_number:  # another channel's conversation
            return
        key = f"outbox:{message.id}:{message.session_id}"
        if await self.repo.has_message(key):
            return
        if await self.repo.is_opted_out(session.phone):
            await self.repo.record_message(key, session.session_id, "out", "opted_out", session.phone)
            return
        try:
            if choices and hasattr(self.provider, "send_choices"):  # a channel with buttons (WhatsApp, Telegram)
                await self._send_buttons(session.phone, body, choices)
            else:
                for part in split_sms(numbered(body, choices), self.SPLIT):
                    await self.provider.send(session.phone, self.config.from_number, part)  # raises on failure, so the outbox retries
        except PermanentSendError:
            await self.repo.record_message(key, session.session_id, "out", "undeliverable", session.phone)  # retrying cannot help
            return
        await self.repo.record_message(key, session.session_id, "out", "sent", session.phone)


    async def _send_buttons(self, to: str, body: str, choices: list[str]) -> None:
        """The reply with its options as buttons. A reply too long for a button message goes first as text, then the buttons follow."""
        if len(body) <= WHATSAPP_BODY:
            await self.provider.send_choices(to, self.config.from_number, body, choices)
            return
        for part in split_sms(body, self.SPLIT):
            await self.provider.send(to, self.config.from_number, part)
        await self.provider.send_choices(to, self.config.from_number, "Choose one:", choices)


class SmsChannel:
    CHANNEL, PREFIX, REPLY_KIND = "sms", "sms-", "sms_reply"

    def __init__(self, runtime: Runtime, agents: Any, repo: SmsRepo, provider: SmsProvider, config: SmsConfig):
        self.rt, self.agents, self.repo, self.provider, self.config = runtime, as_provider(agents), repo, provider, config
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if len(self._locks) > 5000:
            self._locks = {k: v for k, v in self._locks.items() if v.locked()}
        return self._locks.setdefault(key, asyncio.Lock())

    def authentic(self, params: dict[str, str], signature: str) -> bool:
        return self.provider.valid_signature(self.config.webhook_url, params, signature)

    async def receive(self, params: dict[str, str]) -> InboundResult:
        sid, phone, to = params.get("MessageSid", ""), params.get("From", ""), params.get("To", "")
        body = (params.get("Body") or "").strip()
        if not sid or not valid_number(phone) or not valid_number(to):
            raise ValueError("missing or invalid MessageSid, From or To")
        if to != self.config.from_number:
            return InboundResult("ignored", reason="sent to a different number")
        async with self._lock(f"msg:{sid}"):
            if await self.repo.has_message(sid):
                return InboundResult("duplicate", reason="this text was already handled")
            result = await self._handle(phone, body, int(params.get("NumMedia", "0") or 0))
            outcome = result.status if result.status != "ignored" else f"ignored:{result.reason}"
            # Texts that belong to no conversation are recorded under a one-way reference, so erasing a customer leaves no number behind.
            await self.repo.record_message(sid, result.session_id or "-", "in", outcome[:32], phone if result.session_id else phone_hash(phone)[:20])
            return result

    async def _attachments(self, session_id: str, agent: Any, items: list[Any]) -> tuple[list[Any], str | None]:
        """Files that came with a message, for channels that can carry them. The text channels here read none."""
        return [], None

    async def _handle(self, phone: str, body: str, media: int, cfg: "SmsConfig | None" = None, media_items: list[Any] | None = None) -> InboundResult:
        cfg = cfg or self.config
        word = re.sub(r"@\w+$", "", body.lower().strip()).strip(" ./!")
        if word in STOP_WORDS:
            await self.repo.set_opt_out(phone, True)
            return InboundResult("opted_out")
        if word in START_WORDS:
            await self.repo.set_opt_out(phone, False)
            return InboundResult("opted_in")
        if await self.repo.is_opted_out(phone):
            return InboundResult("ignored", reason="this number has opted out")
        if word in HELP_WORDS:
            await self.provider.send(phone, cfg.from_number, cfg.help_text)
            return InboundResult("help")
        if not body and not media:
            return InboundResult("ignored", reason="no text")
        now = time.time()
        if await self.repo.recent_count(phone, "out", now - 3600) >= cfg.max_replies_per_number_per_hour:
            return InboundResult("rate_limited", reason="too many replies to this number in the last hour")
        async with self._lock(f"phone:{phone}"):
            session = await self.repo.latest_session(phone, cfg.from_number)
            if session is None or now - session.last_seen > cfg.session_idle_hours * 3600:
                session = SmsSession(f"{self.PREFIX}{uuid.uuid4().hex}", phone, cfg.from_number)
            session.last_seen = now
            await self.repo.save_session(session)
            text = body[: cfg.max_chars]
            if await self.rt.handoffs.list("open", session.session_id, 1):
                msgs = await self.rt.store.load_messages(session.session_id)
                msgs.append({"role": "user", "content": text})
                await self.rt.store.save_messages(session.session_id, msgs)
                return InboundResult("held_for_person", session.session_id, "a person is handling this conversation")
            try:
                agent = await self.agents.get(cfg.agent_id, "production", session.session_id)
            except AgentUnavailable as e:
                raise RuntimeError(str(e)) from e
            if agent is None:
                raise RuntimeError(f"{self.CHANNEL} agent '{cfg.agent_id}' does not exist")
            agent = await self.rt.active_agent(agent, session.session_id)
            files, note = await self._attachments(session.session_id, agent, media_items or []) if media_items else ([], None)
            unread = media - len(files)
            if unread > 0:
                text += f"\n\n[The message included {unread} attachment(s) that were not read.]"
            if note:
                text += f"\n\n[{note}]"
            run = await self.rt.run(agent, session.session_id, text, session.customer_id, channel=self.CHANNEL, attachments=files or None)
            await self.rt.outbox.publish(session.session_id, self.REPLY_KIND, {
                "reply": run.reply, "status": run.status, "traceId": run.trace_id, "handoffId": run.handoff_id, "choices": run.choices})
            return InboundResult({"completed": "replied"}.get(run.status, run.status), session.session_id, trace_id=run.trace_id, handoff_id=run.handoff_id)
