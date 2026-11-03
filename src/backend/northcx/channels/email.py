"""Email channel.

Inbound: the company's mail system forwards each raw message (RFC 822) to `POST /v1/channels/email/inbound`. NorthCX
groups messages into conversations by the standard threading headers, runs the agent, and sends the reply over SMTP in
the same thread. Safe by default: auto-replies, bounces, mailing lists and our own mail are never answered (no reply
loops), duplicates are ignored, senders are rate limited, and the sender address is never trusted as an identity unless
the deployment says its mail gateway vets it. Once a conversation is handed to a person, further mail from the customer
is kept in the conversation but not answered by the agent.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import re
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.message import EmailMessage, Message
from email.utils import formataddr, getaddresses, parseaddr
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

from ..catalog import AgentUnavailable, as_provider
from ..outbox import OutboxMessage
from ..runtime import Runtime

ADDRESS_RE = re.compile(r"^[A-Za-z0-9._%+'!#$&*/=?^`{|}~-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$")
NO_REPLY_LOCALS = {"mailer-daemon", "postmaster", "noreply", "no-reply", "donotreply", "do-not-reply", "bounce", "bounces"}
QUOTE_STARTS = [
    re.compile(r"^On .{5,200}wrote:\s*$", re.I), re.compile(r"^Le .{5,200}a écrit\s*:\s*$", re.I),
    re.compile(r"^-{2,}\s*(Original Message|Forwarded message)\s*-{2,}\s*$", re.I), re.compile(r"^_{5,}\s*$"),
    re.compile(r"^From:\s.+", re.I),
]


class EmailParseError(ValueError):
    pass


@dataclass
class ParsedEmail:
    message_id: str
    sender: str
    sender_name: str
    subject: str
    text: str
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    ignore_reason: str | None = None  # why the agent must not answer this message
    verified: bool = False  # the receiving gateway vouched for the sender (only if trusted)
    attachments: list[str] = field(default_factory=list)
    truncated: bool = False


# ---------------- parsing ----------------
class _Text(HTMLParser):
    BREAKS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(src: str) -> str:
    p = _Text()
    try:
        p.feed(src)
        p.close()
    except Exception:
        return html.unescape(re.sub(r"<[^>]+>", " ", src))
    return "".join(p.parts)


def strip_quoted_reply(text: str) -> str:
    """The new part of a reply: everything above the quoted history, the signature marker, and `>` quote lines."""
    kept: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.rstrip() == "--" or line == "-- ":
            break
        if any(rx.match(line.strip()) for rx in QUOTE_STARTS) and kept:
            break
        if line.lstrip().startswith(">"):
            continue
        kept.append(line)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return cleaned


def _ids(value: str | None) -> list[str]:
    return re.findall(r"<[^<>\s]{1,900}>", value or "")


def _clean_header(value: Any, limit: int = 300) -> str:
    return re.sub(r"[\r\n\t]+", " ", str(value or "")).strip()[:limit]


def ignore_reason(msg: Message, sender: str) -> str | None:
    """Messages a robot must never answer: answering them makes mail loops and floods."""
    auto = str(msg.get("Auto-Submitted", "no")).strip().lower()
    if auto and auto != "no":
        return "auto-submitted"
    if str(msg.get("Precedence", "")).strip().lower() in ("bulk", "junk", "list", "auto_reply"):
        return "bulk"
    if msg.get("X-Auto-Response-Suppress") or msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return "auto-response"
    if msg.get("List-Id") or msg.get("List-Unsubscribe"):
        return "mailing-list"
    if str(msg.get("Return-Path", "")).strip() == "<>":
        return "bounce"
    if msg.get_content_type() == "multipart/report":
        return "delivery-report"
    if sender.split("@")[0].lower() in NO_REPLY_LOCALS:
        return "no-reply-sender"
    return None


def gateway_vouches(msg: Message) -> bool:
    """True if the receiving mail gateway recorded a passing DMARC check. Only meaningful if that gateway removes any such
    header a sender supplied; the caller decides whether to trust it."""
    for h in msg.get_all("Authentication-Results", []) or []:
        if re.search(r"\bdmarc=pass\b", str(h), re.I):
            return True
    return False


def parse_email(raw: bytes, max_bytes: int = 1_000_000, max_chars: int = 6000, trust_gateway: bool = False) -> ParsedEmail:
    if not raw or not raw.strip():
        raise EmailParseError("empty message")
    if len(raw) > max_bytes:
        raise EmailParseError(f"message is larger than {max_bytes} bytes")
    try:
        msg = message_from_bytes(raw, policy=policy.default)
    except Exception as e:
        raise EmailParseError(f"not a readable email: {e}") from e
    name, addr = parseaddr(str(msg.get("From", "")))
    addr = addr.strip().lower()
    if not ADDRESS_RE.fullmatch(addr):
        raise EmailParseError("no valid sender address")
    ids = _ids(str(msg.get("Message-ID", "")))
    message_id = ids[0] if ids else f"<{hashlib.sha256(raw).hexdigest()[:40]}@parsed.northcx>"
    subject = _clean_header(msg.get("Subject", ""), 500)
    body_part = msg.get_body(preferencelist=("plain", "html"))
    text, attachments = "", []
    try:
        if body_part is not None:
            content = body_part.get_content()
            text = html_to_text(content) if body_part.get_content_type() == "text/html" else content
        for part in msg.iter_attachments():
            attachments.append(_clean_header(part.get_filename() or part.get_content_type(), 120))
    except Exception:
        text = ""  # an undecodable body is treated as empty rather than guessed at
    cleaned = strip_quoted_reply(text) or text.strip()
    truncated = len(cleaned) > max_chars
    return ParsedEmail(
        message_id=message_id, sender=addr, sender_name=_clean_header(name, 120), subject=subject,
        text=cleaned[:max_chars], in_reply_to=(_ids(str(msg.get("In-Reply-To", ""))) or [None])[0],
        references=_ids(str(msg.get("References", ""))), ignore_reason=ignore_reason(msg, addr),
        verified=trust_gateway and gateway_vouches(msg), attachments=attachments, truncated=truncated)


# ---------------- storage ----------------
@dataclass
class EmailSession:
    session_id: str
    sender: str
    subject: str
    last_message_id: str
    customer_id: str | None = None
    verified: bool = False
    references: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class EmailRepo(Protocol):
    async def get_session(self, session_id: str) -> EmailSession | None: ...
    async def find_session(self, message_ids: list[str]) -> EmailSession | None: ...
    async def save_session(self, session: EmailSession) -> None: ...
    async def has_message(self, message_id: str) -> bool: ...
    async def record_message(self, message_id: str, session_id: str, direction: str, outcome: str, peer: str) -> bool: ...
    async def recent_count(self, peer: str, direction: str, since: float) -> int: ...


class InMemoryEmailRepo:
    def __init__(self) -> None:
        self.sessions: dict[str, EmailSession] = {}
        self.messages: dict[str, dict[str, Any]] = {}

    async def get_session(self, session_id: str) -> EmailSession | None:
        return self.sessions.get(session_id)

    async def find_session(self, message_ids: list[str]) -> EmailSession | None:
        for mid in message_ids:  # nearest first
            m = self.messages.get(mid)
            if m and m["session_id"] in self.sessions:
                return self.sessions[m["session_id"]]
        return None

    async def save_session(self, session: EmailSession) -> None:
        self.sessions[session.session_id] = session

    async def has_message(self, message_id: str) -> bool:
        return message_id in self.messages

    async def record_message(self, message_id: str, session_id: str, direction: str, outcome: str, peer: str) -> bool:
        if message_id in self.messages:
            return False
        self.messages[message_id] = dict(session_id=session_id, direction=direction, outcome=outcome, peer=peer, at=time.time())
        return True

    async def recent_count(self, peer: str, direction: str, since: float) -> int:
        return sum(1 for m in self.messages.values() if m["peer"] == peer and m["direction"] == direction and m["at"] >= since)


# ---------------- sending ----------------
class SmtpError(RuntimeError):
    pass


def parse_smtp_url(url: str) -> dict[str, Any]:
    """smtp://host:25 (plain), smtp+starttls://host:587, smtps://host:465; user and password may be in the URL."""
    u = urlparse(url)
    if u.scheme not in ("smtp", "smtp+starttls", "smtps") or not u.hostname:
        raise ValueError("NORTHCX_SMTP_URL must look like smtp+starttls://user:password@host:587 (or smtp://, smtps://)")
    default = {"smtp": 25, "smtp+starttls": 587, "smtps": 465}[u.scheme]
    return {"scheme": u.scheme, "host": u.hostname, "port": u.port or default,
            "user": unquote(u.username) if u.username else None, "password": unquote(u.password) if u.password else None}


class SmtpSender:
    def __init__(self, url: str, timeout: float = 15.0):
        self.cfg, self.timeout = parse_smtp_url(url), timeout

    def _send_blocking(self, msg: EmailMessage) -> None:
        c = self.cfg
        try:
            if c["scheme"] == "smtps":
                smtp: smtplib.SMTP = smtplib.SMTP_SSL(c["host"], c["port"], timeout=self.timeout, context=ssl.create_default_context())
            else:
                smtp = smtplib.SMTP(c["host"], c["port"], timeout=self.timeout)
            with smtp:
                if c["scheme"] == "smtp+starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if c["user"]:
                    smtp.login(c["user"], c["password"] or "")
                refused = smtp.send_message(msg)
                if refused:
                    raise SmtpError(f"recipient refused: {list(refused)}")
        except (smtplib.SMTPException, OSError) as e:
            raise SmtpError(f"could not send email: {e.__class__.__name__}: {e}") from e

    async def send(self, msg: EmailMessage) -> None:
        await asyncio.to_thread(self._send_blocking, msg)


class Sender(Protocol):
    async def send(self, msg: EmailMessage) -> None: ...


@dataclass
class EmailConfig:
    from_address: str
    agent_id: str = "support"
    trust_gateway: bool = False  # believe an Authentication-Results header (only if the gateway strips forged ones)
    max_replies_per_sender_per_hour: int = 6
    max_chars: int = 6000
    from_name: str = ""

    @property
    def domain(self) -> str:
        return self.from_address.rsplit("@", 1)[-1]


def message_id_for(config: EmailConfig, key: str) -> str:
    return f"<northcx-{hashlib.sha256(key.encode()).hexdigest()[:24]}@{config.domain}>"


def build_reply(config: EmailConfig, session: EmailSession, body: str, message_id: str, in_reply_to: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((config.from_name, config.from_address)) if config.from_name else config.from_address
    msg["To"] = session.sender
    subject = session.subject or "Your message"
    msg["Subject"] = subject if re.match(r"^(re|aw|sv)\s*:", subject, re.I) else f"Re: {subject}"
    msg["Message-ID"] = message_id
    msg["In-Reply-To"] = in_reply_to
    msg["References"] = " ".join((session.references + [in_reply_to])[-20:])
    msg["Auto-Submitted"] = "auto-replied"  # so other robots do not answer us
    msg["X-Auto-Response-Suppress"] = "All"
    msg["Precedence"] = "bulk"
    msg.set_content(body)
    return msg


# ---------------- outbound: the outbox delivers replies by email ----------------
class EmailNotifier:
    """Delivers outbox messages that belong to email conversations as replies in the same thread; ignores the rest."""

    def __init__(self, repo: EmailRepo, sender: Sender, config: EmailConfig):
        self.repo, self.sender, self.config = repo, sender, config

    async def deliver(self, message: OutboxMessage) -> None:
        session = await self.repo.get_session(message.session_id)
        body = message.payload.get("reply")
        if session is None or not body:
            return  # not an email conversation (or nothing to say)
        mid = message_id_for(self.config, f"outbox:{message.id}:{message.session_id}")
        if await self.repo.has_message(mid):
            return  # already sent on an earlier attempt
        reply_to = message.payload.get("inReplyTo") or session.last_message_id
        msg = build_reply(self.config, session, body, mid, reply_to)
        await self.sender.send(msg)  # raises on failure, so the outbox retries later
        await self.repo.record_message(mid, session.session_id, "out", "sent", session.sender)
        session.last_message_id = mid
        session.references = (session.references + [reply_to])[-20:]
        await self.repo.save_session(session)


# ---------------- inbound ----------------
@dataclass
class InboundResult:
    status: str  # replied | escalated | needs_approval | held_for_person | ignored | duplicate | rate_limited
    session_id: str | None = None
    reason: str | None = None
    trace_id: str | None = None
    handoff_id: str | None = None


class EmailChannel:
    def __init__(self, runtime: Runtime, agents: Any, repo: EmailRepo, config: EmailConfig):
        self.rt, self.agents, self.repo, self.config = runtime, as_provider(agents), repo, config
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if len(self._locks) > 5000:
            self._locks = {k: v for k, v in self._locks.items() if v.locked()}
        return self._locks.setdefault(key, asyncio.Lock())

    async def receive(self, raw: bytes) -> InboundResult:
        cfg = self.config
        mail = parse_email(raw, max_chars=cfg.max_chars, trust_gateway=cfg.trust_gateway)  # EmailParseError for the caller
        async with self._lock(f"msg:{mail.message_id}"):
            if await self.repo.has_message(mail.message_id):
                return InboundResult("duplicate", reason="this message was already handled")
            result = await self._handle(mail)
            outcome = result.status if result.status != "ignored" else f"ignored:{result.reason}"
            await self.repo.record_message(mail.message_id, result.session_id or "-", "in", outcome[:32],
                                           mail.sender if result.session_id else "h:" + hashlib.sha256(mail.sender.encode()).hexdigest()[:24])
            return result

    async def _handle(self, mail: ParsedEmail) -> InboundResult:
        cfg = self.config
        if mail.sender == cfg.from_address.lower():
            return InboundResult("ignored", reason="our own address")
        if mail.ignore_reason:
            return InboundResult("ignored", reason=mail.ignore_reason)
        if not mail.text:
            return InboundResult("ignored", reason="no text")
        found = await self.repo.find_session(([mail.in_reply_to] if mail.in_reply_to else []) + list(reversed(mail.references)))
        session = found if found and found.sender == mail.sender else None  # a different sender never joins someone's thread
        new = session is None
        if new:
            session = EmailSession(f"email-{uuid.uuid4().hex}", mail.sender, mail.subject, mail.message_id,
                                   f"email:{mail.sender}" if mail.verified else None, mail.verified)
        recent = await self.repo.recent_count(mail.sender, "out", time.time() - 3600)
        if recent >= cfg.max_replies_per_sender_per_hour:
            return InboundResult("rate_limited", session.session_id, "too many replies to this sender in the last hour")
        async with self._lock(f"session:{session.session_id}"):
            session.references = (session.references + [session.last_message_id])[-20:] if not new else []
            session.last_message_id = mail.message_id
            await self.repo.save_session(session)
            if not new and await self.rt.handoffs.list("open", session.session_id, 1):
                # A person owns this conversation: keep what the customer wrote, but the agent stays quiet.
                msgs = await self.rt.store.load_messages(session.session_id)
                msgs.append({"role": "user", "content": mail.text})
                await self.rt.store.save_messages(session.session_id, msgs)
                return InboundResult("held_for_person", session.session_id, "a person is handling this conversation")
            try:
                agent = await self.agents.get(cfg.agent_id)
            except AgentUnavailable as e:
                raise RuntimeError(str(e)) from e
            if agent is None:
                raise RuntimeError(f"email agent '{cfg.agent_id}' does not exist")
            text = f"Subject: {mail.subject}\n\n{mail.text}" if new else mail.text
            if mail.attachments:
                text += f"\n\n[The email had {len(mail.attachments)} attachment(s) that were not read.]"
            run = await self.rt.run(agent, session.session_id, text, session.customer_id, channel="email")
            await self.rt.outbox.publish(session.session_id, "email_reply", {
                "reply": run.reply, "status": run.status, "traceId": run.trace_id, "handoffId": run.handoff_id,
                "inReplyTo": mail.message_id})
            status = {"completed": "replied"}.get(run.status, run.status)
            return InboundResult(status, session.session_id, trace_id=run.trace_id, handoff_id=run.handoff_id)
