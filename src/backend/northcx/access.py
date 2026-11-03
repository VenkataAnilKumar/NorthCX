"""Who may do what: roles, API keys (stored hashed), rate limits."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Protocol

from .tokens import PREFIX as TOKEN_PREFIX, TokenError, TokenSigner

# ---------------- roles and permissions ----------------
VIEW = {"agents:read", "traces:read", "handoffs:read", "approvals:read", "simulations:read", "versions:read", "monitor:read", "knowledge:read"}
DEVELOP = VIEW | {"knowledge:write", "versions:create", "simulations:run", "chat:send", "outbox:read"}
ROLES: dict[str, frozenset[str]] = {
    "admin": frozenset(DEVELOP | {"releases:publish", "releases:rollback", "approvals:decide", "handoffs:resolve",
                                  "keys:manage", "audit:read", "chat:mint", "channel:inbound", "privacy:manage", "memory:read", "memory:manage"}),
    "release_manager": frozenset(DEVELOP | {"releases:publish", "releases:rollback", "memory:read"}),
    "developer": frozenset(DEVELOP | {"memory:read"}),
    "reviewer": frozenset(VIEW | {"approvals:decide", "handoffs:resolve", "memory:read"}),
    "auditor": frozenset(VIEW | {"audit:read"}),
    "viewer": frozenset(VIEW),
    "channel": frozenset({"chat:send", "outbox:read", "chat:mint", "channel:inbound"}),  # for the company's servers and channel adapters
}
# Roles that exist only inside the platform; a key can never be given one.
INTERNAL_ROLES: dict[str, frozenset[str]] = {
    "customer_session": frozenset({"chat:send", "outbox:read"}),  # a chat token: limited further to its own conversation
}
NAME_RE = re.compile(r"^[A-Za-z0-9 _.@-]{1,80}$")


@dataclass(frozen=True)
class Identity:
    name: str
    role: str
    key_id: str | None = None
    open_mode: bool = False  # no authentication is configured
    # Set for a customer's chat token: the one conversation, customer and agent it is limited to.
    session_id: str | None = None
    customer_id: str | None = None
    agent: str | None = None

    @property
    def permissions(self) -> frozenset[str]:
        return ROLES[self.role] if self.role in ROLES else INTERNAL_ROLES[self.role]

    def can(self, permission: str) -> bool:
        return permission in self.permissions


OPEN_IDENTITY = Identity("anonymous", "admin", None, True)


# ---------------- keys ----------------
@dataclass
class ApiKey:
    name: str
    role: str
    key_id: str
    key_hash: str
    created_by: str
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    revoked_at: float | None = None
    revoked_by: str | None = None
    last_used_at: float | None = None

    @property
    def prefix(self) -> str:
        return f"ncx_{self.key_id}"

    def active(self, now: float | None = None) -> bool:
        now = now or time.time()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)


def hash_secret(secret: str) -> str:
    """Keys are 256-bit random values, so a plain SHA-256 is enough; there is nothing to brute-force."""
    return hashlib.sha256(secret.encode()).hexdigest()


def parse_token(token: str) -> tuple[str, str] | None:
    m = re.fullmatch(r"ncx_([0-9a-f]{8})_([A-Za-z0-9_-]{20,})", token)
    return (m.group(1), m.group(2)) if m else None


class KeyRepo(Protocol):
    async def create(self, key: ApiKey) -> ApiKey: ...
    async def get(self, key_id: str) -> ApiKey | None: ...
    async def list(self) -> list[ApiKey]: ...
    async def revoke(self, key_id: str, by: str) -> ApiKey: ...
    async def touch(self, key_id: str, at: float) -> None: ...


class InMemoryKeys:
    def __init__(self) -> None:
        self._items: dict[str, ApiKey] = {}
        self._lock = asyncio.Lock()

    async def create(self, key: ApiKey) -> ApiKey:
        async with self._lock:
            if key.key_id in self._items:
                raise ValueError("key id collision")
            self._items[key.key_id] = key
            return key

    async def get(self, key_id: str) -> ApiKey | None:
        return self._items.get(key_id)

    async def list(self) -> list[ApiKey]:
        return sorted(self._items.values(), key=lambda k: k.created_at, reverse=True)

    async def revoke(self, key_id: str, by: str) -> ApiKey:
        k = self._items.get(key_id)
        if k is None:
            raise KeyError(key_id)
        if k.revoked_at is not None:
            raise ValueError(f"Key {key_id} is already revoked")
        k.revoked_at, k.revoked_by = time.time(), by
        return k

    async def touch(self, key_id: str, at: float) -> None:
        if key_id in self._items:
            self._items[key_id].last_used_at = at


# ---------------- rate limiting ----------------
class RateLimiter:
    """Token buckets: `limit` requests per minute per key, bursts up to the limit. Per process.
    (Several server processes each keep their own buckets; a shared limiter is a later step.)"""

    def __init__(self, clock=time.monotonic, max_buckets: int = 20_000):
        self.clock, self.max_buckets = clock, max_buckets
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last)

    def allow(self, key: str, limit_per_minute: float) -> tuple[bool, float]:
        """Returns (allowed, seconds until a retry could succeed)."""
        now = self.clock()
        tokens, last = self._buckets.get(key, (float(limit_per_minute), now))
        tokens = min(float(limit_per_minute), tokens + (now - last) * limit_per_minute / 60.0)
        if tokens >= 1:
            self._store(key, tokens - 1, now)
            return True, 0.0
        self._store(key, tokens, now)
        return False, (1 - tokens) * 60.0 / limit_per_minute

    def _store(self, key: str, tokens: float, now: float) -> None:
        self._buckets[key] = (tokens, now)
        if len(self._buckets) > self.max_buckets:  # forget the buckets that have been idle longest
            for k, _ in sorted(self._buckets.items(), key=lambda kv: kv[1][1])[: self.max_buckets // 10]:
                self._buckets.pop(k, None)


@dataclass
class LimitConfig:
    per_key_per_minute: float = 600
    chat_per_session_per_minute: float = 30
    auth_failures_per_minute: float = 20  # per client address


# ---------------- access control ----------------
class AccessControl:
    def __init__(self, keys: KeyRepo | None = None, bootstrap_key: str | None = None, limits: LimitConfig | None = None,
                 limiter: RateLimiter | None = None, touch_interval: float = 60.0, signer: TokenSigner | None = None):
        self.signer = signer
        self.keys = keys or InMemoryKeys()
        self._bootstrap = hash_secret(bootstrap_key) if bootstrap_key else None
        self.limits, self.limiter = limits, limiter or RateLimiter()
        self.touch_interval = touch_interval
        self._touched: dict[str, float] = {}
        self.configured_keys = bootstrap_key is not None
        self._has_keys = False  # once any key exists, authentication stays on

    async def enabled(self) -> bool:
        """Authentication is on when a bootstrap key is set or any key has ever been created (revoking keys never
        turns it back off)."""
        if self.configured_keys or self._has_keys:
            return True
        self._has_keys = bool(await self.keys.list())
        return self._has_keys

    async def authenticate(self, token: str | None) -> Identity | None:
        return (await self.authenticate_detail(token))[0]

    async def authenticate_detail(self, token: str | None) -> tuple[Identity | None, str | None]:
        """(identity, None) on success, or (None, why) where why is `expired` for a lapsed chat token and `invalid` otherwise."""
        if token and token.startswith(TOKEN_PREFIX):
            return await self._chat_token(token)
        who = await self._key(token)
        return (who, None) if who else (None, "invalid")

    async def _chat_token(self, token: str) -> tuple[Identity | None, str | None]:
        if self.signer is None:
            return None, "invalid"
        try:
            c = self.signer.verify(token)
        except TokenError as e:
            return None, "expired" if e.kind == "expired" else "invalid"
        # The minting key must still be good: revoking it ends every conversation it opened.
        if c.kid == "bootstrap":
            if not self.configured_keys:
                return None, "invalid"
        else:
            k = await self.keys.get(c.kid)
            if k is None or not k.active() or "chat:mint" not in ROLES.get(k.role, frozenset()):
                return None, "invalid"
        return Identity(f"customer session {c.sid[:12]}", "customer_session", f"tok:{c.sid}", False, c.sid, c.cid, c.agent), None

    async def _key(self, token: str | None) -> Identity | None:
        if not token:
            return None
        if self._bootstrap and hmac.compare_digest(hash_secret(token), self._bootstrap):
            return Identity("bootstrap", "admin", "bootstrap")
        parsed = parse_token(token)
        if parsed is None:
            return None
        key_id, secret = parsed
        k = await self.keys.get(key_id)
        if k is None or not hmac.compare_digest(hash_secret(secret), k.key_hash) or not k.active():
            return None
        now = time.time()
        if now - self._touched.get(key_id, 0) >= self.touch_interval:  # record use at most once a minute
            self._touched[key_id] = now
            await self.keys.touch(key_id, now)
        return Identity(k.name, k.role, k.key_id)

    async def issue(self, name: str, role: str, created_by: str, expires_in_days: float | None = None) -> tuple[ApiKey, str]:
        """Create a key. The secret is returned once and never stored."""
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}' (roles: {', '.join(sorted(ROLES))})")
        if not NAME_RE.fullmatch(name) or name != name.strip():
            raise ValueError("Key names use letters, digits, spaces and . _ @ - (1 to 80 characters)")
        if expires_in_days is not None and not 0 < expires_in_days <= 3650:
            raise ValueError("expiresInDays must be between 0 and 3650")
        if any(k.name.lower() == name.lower() and k.active() for k in await self.keys.list()):
            raise ValueError(f"An active key named '{name}' already exists")
        secret = secrets.token_urlsafe(32)
        key = ApiKey(name, role, secrets.token_hex(4), hash_secret(secret), created_by,
                     expires_at=time.time() + expires_in_days * 86400 if expires_in_days else None)
        await self.keys.create(key)
        self._has_keys = True
        return key, f"{key.prefix}_{secret}"

    async def revoke(self, key_id: str, by: str) -> ApiKey:
        keys = await self.keys.list()
        target = next((k for k in keys if k.key_id == key_id), None)
        if target is None:
            raise KeyError(key_id)
        others = [k for k in keys if k.key_id != key_id and k.role == "admin" and k.active()]
        if target.role == "admin" and target.active() and not others and not self.configured_keys:
            raise ValueError("This is the last active admin key; create another admin key first")
        return await self.keys.revoke(key_id, by)
