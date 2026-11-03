"""One-time-code identity checks (C9).

The company's server already says who a customer is when it mints the chat token. This adds a second step for sensitive actions:
the customer proves they control the email address or phone number the company has on file. The address comes only from the
facts the company's own systems reported for this customer (`email`, `phone`), never from the conversation, so a code cannot be
sent to an address a customer or the model made up. A correct code makes the conversation "verified" for a while; that shows up as
the fact `identity_verified: yes`, which tool scopes can require (`tool_scopes: {issue_refund: {facts: {identity_verified: [yes]}}}`).

Codes are six digits from the system random source, stored only as a keyed hash, single use, expire in ten minutes, allow five
tries, and sending is limited per conversation. The code that is sent is never written to a trace, log or audit entry, and the code the customer
types is kept out of the trace of the tool call; the customer's own message that contains it is part of the conversation like any other, which is why
the code is single use and short lived.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets as _secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, Field

from .agent import Tool, ToolContext

FACT = "identity_verified"
Sender = Callable[[str, str], Awaitable[None]]  # (destination, message) -> None; raises on failure


class VerifyRefused(Exception):
    """Safe to show to the customer."""


@dataclass
class VerifyConfig:
    code_ttl: float = 600.0
    verified_for: float = 1800.0
    max_attempts: int = 5
    resend_after: float = 60.0
    max_sends_per_hour: int = 3


@dataclass
class VerifyRecord:
    session_id: str
    customer_id: str
    channel: str = ""
    dest_hash: str = ""
    code_hash: str | None = None
    expires_at: float = 0.0
    attempts: int = 0
    sends: list[float] = field(default_factory=list)
    verified_until: float | None = None


class VerifyRepo(Protocol):
    async def get(self, session_id: str) -> VerifyRecord | None: ...
    async def save(self, r: VerifyRecord) -> None: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryVerify:
    def __init__(self) -> None:
        self.items: dict[str, VerifyRecord] = {}

    async def get(self, session_id: str) -> VerifyRecord | None:
        r = self.items.get(session_id)
        return VerifyRecord(**r.__dict__) if r else None

    async def save(self, r: VerifyRecord) -> None:
        self.items[r.session_id] = VerifyRecord(**r.__dict__)

    async def erase_session(self, session_id: str) -> int:
        return 1 if self.items.pop(session_id, None) else 0


def mask_destination(channel: str, dest: str) -> str:
    if channel == "email" and "@" in dest:
        local, _, domain = dest.partition("@")
        return local[:1] + "***@" + domain
    return "*" * max(0, len(dest) - 3) + dest[-3:]


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_PHONE = re.compile(r"^\+[1-9]\d{6,14}$")


class OtpService:
    def __init__(self, repo: VerifyRepo, senders: dict[str, Sender], secret: bytes, config: VerifyConfig | None = None, clock: Callable[[], float] = time.time):
        self.repo, self.senders, self.secret, self.cfg, self.clock = repo, senders, secret, config or VerifyConfig(), clock

    def channels(self) -> list[str]:
        return sorted(self.senders)

    def _hash(self, session_id: str, customer_id: str, what: str) -> str:
        return hmac.new(self.secret, f"{session_id}\0{customer_id}\0{what}".encode(), hashlib.sha256).hexdigest()

    async def start(self, session_id: str, customer_id: str | None, channel: str, facts: dict[str, str]) -> dict[str, Any]:
        if not customer_id:
            raise VerifyRefused("This conversation is not tied to a known customer, so a code cannot be sent")
        if channel not in self.senders:
            raise VerifyRefused(f"Codes cannot be sent by {channel} here (available: {', '.join(self.channels()) or 'none'})")
        dest = str(facts.get("email" if channel == "email" else "phone", "")).strip()
        if not (_EMAIL.match(dest) if channel == "email" else _PHONE.match(dest)):
            raise VerifyRefused(f"There is no {channel} address on file for this customer, so a code cannot be sent. Offer a hand-off to a person instead")
        now = self.clock()
        rec = await self.repo.get(session_id) or VerifyRecord(session_id, customer_id)
        if rec.customer_id != customer_id:
            raise VerifyRefused("This conversation belongs to a different customer")
        rec.sends = [t for t in rec.sends if now - t < 3600]
        if rec.sends and now - rec.sends[-1] < self.cfg.resend_after:
            raise VerifyRefused(f"A code was just sent; wait {int(self.cfg.resend_after - (now - rec.sends[-1])) + 1} seconds before asking for another")
        if len(rec.sends) >= self.cfg.max_sends_per_hour:
            raise VerifyRefused("Too many codes have been sent for this conversation; offer a hand-off to a person")
        code = f"{_secrets.randbelow(10 ** 6):06d}"
        rec.channel, rec.dest_hash, rec.code_hash = channel, self._hash(session_id, customer_id, dest), self._hash(session_id, customer_id, code)
        rec.expires_at, rec.attempts = now + self.cfg.code_ttl, 0
        rec.sends.append(now)
        await self.repo.save(rec)  # saved before sending, so a slow sender cannot be used to ask for unlimited codes
        try:
            await self.senders[channel](dest, f"Your verification code is {code}. It expires in {int(self.cfg.code_ttl // 60)} minutes. If you did not ask for it, ignore this message.")
        except Exception:
            rec.code_hash = None
            await self.repo.save(rec)
            raise VerifyRefused("The code could not be sent right now; offer a hand-off to a person") from None
        return {"sent": True, "to": mask_destination(channel, dest), "channel": channel, "expiresInSeconds": int(self.cfg.code_ttl)}

    async def check(self, session_id: str, customer_id: str | None, code: str) -> dict[str, Any]:
        now = self.clock()
        rec = await self.repo.get(session_id)
        code = re.sub(r"\s+", "", code or "")
        if rec is None or not customer_id or rec.customer_id != customer_id or rec.code_hash is None or now > rec.expires_at:
            raise VerifyRefused("There is no active code for this conversation; ask for a new one")
        if not re.fullmatch(r"\d{6}", code):
            return {"verified": False, "attemptsLeft": max(0, self.cfg.max_attempts - rec.attempts), "reason": "The code is six digits"}
        rec.attempts += 1
        ok = hmac.compare_digest(rec.code_hash, self._hash(session_id, customer_id, code))
        if ok:
            rec.code_hash, rec.verified_until = None, now + self.cfg.verified_for
            await self.repo.save(rec)
            return {"verified": True, "validForMinutes": int(self.cfg.verified_for // 60)}
        if rec.attempts >= self.cfg.max_attempts:
            rec.code_hash = None
        await self.repo.save(rec)
        left = max(0, self.cfg.max_attempts - rec.attempts)
        return {"verified": False, "attemptsLeft": left, "reason": "That code is not right" + ("" if left else "; it has been cancelled, so ask for a new one")}

    async def is_verified(self, session_id: str, customer_id: str | None) -> bool:
        rec = await self.repo.get(session_id)
        return bool(rec and customer_id and rec.customer_id == customer_id and rec.verified_until and self.clock() < rec.verified_until)


class _Send(BaseModel):
    channel: Literal["email", "sms"] = Field(description="Where to send the code: the email address or the phone number on file")


class _Check(BaseModel):
    code: str = Field(min_length=4, max_length=12, description="The six-digit code the customer received")


def verification_tools(svc: OtpService) -> list[Tool]:
    async def send(data: _Send, ctx: ToolContext) -> dict[str, Any]:
        try:
            return await svc.start(ctx.session_id, ctx.customer_id, data.channel, ctx.facts)
        except VerifyRefused as e:
            return {"sent": False, "reason": str(e)}

    async def check(data: _Check, ctx: ToolContext) -> dict[str, Any]:
        try:
            return await svc.check(ctx.session_id, ctx.customer_id, data.code)
        except VerifyRefused as e:
            return {"verified": False, "reason": str(e)}
    return [
        Tool("send_verification_code", f"Send a one-time code to the email address or phone number the company has on file for this customer ({', '.join(svc.channels())}). "
             "Use it before a sensitive action. The destination cannot be chosen.", _Send, send, effect="write",
             dry_run_result=lambda d, c: {"sent": True, "to": "(simulated)", "channel": d.channel}),
        Tool("check_verification_code", "Check the six-digit code the customer typed. If it is right the customer is verified for a while.", _Check, check, effect="write",
             dry_run_result=lambda d, c: {"verified": False, "reason": "simulated"}),
    ]
