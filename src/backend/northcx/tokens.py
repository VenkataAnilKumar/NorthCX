"""Short-lived chat tokens for customers' browsers and apps.

A company's server holds a channel key and asks NorthCX for a token for one conversation; the customer's browser then
uses that token and nothing else. The token is signed (HMAC-SHA256), names the one conversation it may use, the customer
it speaks for, and the agent it may talk to, and expires within hours. It cannot read anything, cannot start other
conversations, and stops working at once if the key that minted it is revoked."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets as pysecrets
import time
from dataclasses import dataclass
from typing import Callable

PREFIX = "ncxc_"
DEFAULT_TTL, MIN_TTL, MAX_TTL = 3600, 60, 86400
MAX_LENGTH = 2048


class TokenError(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind  # malformed | unsupported | bad_signature | expired


@dataclass(frozen=True)
class Claims:
    sid: str  # the one conversation this token may use
    cid: str | None  # the customer it speaks for (set by the company's server, not by the customer)
    agent: str | None  # the one agent it may talk to; None means any
    kid: str  # the key that minted it; revoking that key revokes the token
    jti: str
    iat: float
    exp: float


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def derive_secret(explicit: str | None, bootstrap_key: str | None) -> bytes | None:
    """The signing secret: `NORTHCX_TOKEN_SECRET` if given, else derived from the bootstrap key (stable across restarts and
    server processes that share it, and different from the key itself), else None."""
    if explicit:
        return hashlib.sha256(b"northcx-token-secret-v1:" + explicit.encode()).digest()
    if bootstrap_key:
        return hmac.new(bootstrap_key.encode(), b"northcx-chat-token-v1", hashlib.sha256).digest()
    return None


class TokenSigner:
    def __init__(self, secret: bytes, clock: Callable[[], float] = time.time):
        if len(secret) < 16:
            raise ValueError("token secret is too short")
        self._secret, self._clock = secret, clock

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._secret, payload.encode(), hashlib.sha256).digest())

    def mint(self, *, sid: str, kid: str, cid: str | None = None, agent: str | None = None, ttl: float = DEFAULT_TTL) -> tuple[str, Claims]:
        if not MIN_TTL <= ttl <= MAX_TTL:
            raise ValueError(f"ttlSeconds must be between {MIN_TTL} and {MAX_TTL}")
        now = self._clock()
        claims = Claims(sid, cid, agent, kid, pysecrets.token_hex(8), now, now + ttl)
        body = {"v": 1, "sid": sid, "cid": cid, "ag": agent, "kid": kid, "jti": claims.jti, "iat": int(now), "exp": int(now + ttl)}
        payload = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
        return f"{PREFIX}{payload}.{self._sign(payload)}", claims

    def verify(self, token: str) -> Claims:
        if not token.startswith(PREFIX) or len(token) > MAX_LENGTH or token.count(".") != 1:
            raise TokenError("malformed")
        payload, _, sig = token[len(PREFIX):].partition(".")
        if not hmac.compare_digest(self._sign(payload), sig):  # check the signature before trusting anything inside
            raise TokenError("bad_signature")
        try:
            body = json.loads(_unb64(payload))
            if body["v"] != 1:
                raise TokenError("unsupported")
            claims = Claims(str(body["sid"]), body["cid"], body["ag"], str(body["kid"]), str(body["jti"]), float(body["iat"]), float(body["exp"]))
        except TokenError:
            raise
        except (ValueError, KeyError, TypeError):
            raise TokenError("malformed") from None
        if self._clock() >= claims.exp:
            raise TokenError("expired")
        return claims
