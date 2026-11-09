"""Who may do what: roles, API keys (stored hashed), rate limits."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Any, Protocol

from .tenancy import DEFAULT_TENANT
from .tokens import PREFIX as TOKEN_PREFIX, TokenError, TokenSigner

# ---------------- roles and permissions ----------------
VIEW = {"workspace:use", "agents:read", "traces:read", "handoffs:read", "approvals:read", "simulations:read", "versions:read", "monitor:read", "knowledge:read", "insights:read"}
DEVELOP = VIEW | {"reviews:write", "scenarios:write", "conversations:tag", "feedback:send", "knowledge:write", "versions:create", "simulations:run", "chat:send", "outbox:read"}
ROLES: dict[str, frozenset[str]] = {
    "admin": frozenset(DEVELOP | {"releases:publish", "releases:rollback", "approvals:decide", "handoffs:resolve",
                                  "keys:manage", "audit:read", "chat:mint", "channel:inbound", "privacy:manage", "memory:read", "memory:manage", "scenarios:require"}),
    "release_manager": frozenset(DEVELOP | {"releases:publish", "releases:rollback", "memory:read", "scenarios:require"}),
    "developer": frozenset(DEVELOP | {"memory:read"}),
    "reviewer": frozenset(VIEW | {"approvals:decide", "handoffs:resolve", "memory:read", "conversations:tag", "reviews:write"}),
    "auditor": frozenset(VIEW | {"audit:read"}),
    "viewer": frozenset(VIEW),
    "channel": frozenset({"chat:send", "outbox:read", "chat:mint", "channel:inbound", "feedback:send"}),  # for the company's servers and channel adapters
}
# Roles that exist only inside the platform; a key can never be given one.
INTERNAL_ROLES: dict[str, frozenset[str]] = {
    "customer_session": frozenset({"chat:send", "outbox:read", "feedback:send"}),  # a chat token: limited further to its own conversation
}
SSO_CREATOR = "sso"
ENVIRONMENTS = ("dev", "staging", "production")
AGENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def _scope(values: list[str] | None, what: str, rx: Any) -> list[str] | None:
    """A scope list: None means unlimited. An empty list is refused (it would mean access to nothing, which is a mistake, not a key)."""
    if values is None:
        return None
    if not values or len(values) > 50 or len(set(values)) != len(values):
        raise ValueError(f"{what} must be a list of 1 to 50 different names (leave it out for no limit)")
    if rx is not None and not all(isinstance(v, str) and rx.fullmatch(v) for v in values):
        raise ValueError(f"{what} must be agent ids: letters, digits, . _ -")
    return list(values)
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
    # Set for a key limited to some agents and/or environments (WP3.1); None means no limit on that axis.
    scope_agents: tuple[str, ...] | None = None
    scope_envs: tuple[str, ...] | None = None
    tenant: str = DEFAULT_TENANT  # whose key this is (WP2.2); the request is scoped to it
    extra_roles: tuple[str, ...] = ()  # more roles from group membership (WP3.2); the permissions are the union with `role`

    def allows_agent(self, agent_id: str) -> bool:
        return self.scope_agents is None or agent_id in self.scope_agents

    def allows_env(self, environment: str) -> bool:
        return self.scope_envs is None or environment in self.scope_envs

    @property
    def permissions(self) -> frozenset[str]:
        base = ROLES[self.role] if self.role in ROLES else INTERNAL_ROLES[self.role]
        if not self.extra_roles:
            return base
        return frozenset(base.union(*(ROLES[r] for r in self.extra_roles if r in ROLES)))

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
    tenant_id: str = DEFAULT_TENANT
    extra_roles: list[str] | None = None  # roles added by group membership at sign-in (the permissions are the union with `role`)
    agents: list[str] | None = None  # limited to these agents (None: all)
    environments: list[str] | None = None  # limited to these environments (None: all)

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
    With several server processes use `PgLimiter` (NORTHCX_LIMITS_BACKEND=postgres) so they share one count."""

    def __init__(self, clock=time.monotonic, max_buckets: int = 20_000):
        self.clock, self.max_buckets = clock, max_buckets
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last)
        self._events: dict[str, deque[float]] = {}

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

    async def hit(self, key: str, limit_per_minute: float) -> tuple[bool, float]:
        """The interface the server uses (shared limiters are asynchronous): same answer as `allow`."""
        return self.allow(key, limit_per_minute)

    async def count(self, key: str, window_seconds: float) -> int:
        """Count one event for `key` and return how many fell in the last `window_seconds` (a sliding window, per process)."""
        now = self.clock()
        q = self._events.setdefault(key, deque())
        q.append(now)
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(self._events) > self.max_buckets:
            for k in [k for k, v in self._events.items() if not v or now - v[-1] > window_seconds][: self.max_buckets // 10]:
                self._events.pop(k, None)
        return len(q)

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
    channel_per_minute: float = 6000  # keys with the channel role (your servers minting chat tokens, telephony bridges) serve many customers at once


# ---------------- access control ----------------
class AccessControl:
    def __init__(self, keys: KeyRepo | None = None, bootstrap_key: str | None = None, limits: LimitConfig | None = None,
                 limiter: Any = None, touch_interval: float = 60.0, signer: TokenSigner | None = None):
        self.signer = signer
        self.keys = keys or InMemoryKeys()
        self._bootstrap = hash_secret(bootstrap_key) if bootstrap_key else None
        self.limits, self.limiter = limits, limiter or RateLimiter()
        self.touch_interval = touch_interval
        self._touched: dict[str, float] = {}
        self.tenants: Any = None  # northcx.tenancy.TenantService, set by the server (WP2.2)
        self.scim: Any = None  # northcx.scim.ScimService, set by the server when NORTHCX_SCIM_TOKEN is set (WP3.3)
        self.groups: Any = None  # northcx.groups.GroupService, set by the server (WP3.2)
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
        if self.tenants is not None and k.tenant_id != DEFAULT_TENANT and not await self.tenants.is_active(k.tenant_id):
            return None  # a suspended (or removed) tenant's keys stop working at once
        return Identity(k.name, k.role, k.key_id, tenant=k.tenant_id, extra_roles=tuple(k.extra_roles or ()), scope_agents=tuple(k.agents) if k.agents is not None else None,
                        scope_envs=tuple(k.environments) if k.environments is not None else None)

    async def issue(self, name: str, role: str, created_by: str, expires_in_days: float | None = None,
                    agents: list[str] | None = None, environments: list[str] | None = None, tenant_id: str = DEFAULT_TENANT) -> tuple[ApiKey, str]:
        """Create a key. The secret is returned once and never stored. `agents` and `environments` limit what it can reach."""
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}' (roles: {', '.join(sorted(ROLES))})")
        if not NAME_RE.fullmatch(name) or name != name.strip():
            raise ValueError("Key names use letters, digits, spaces and . _ @ - (1 to 80 characters)")
        if expires_in_days is not None and not 0 < expires_in_days <= 3650:
            raise ValueError("expiresInDays must be between 0 and 3650")
        if any(k.name.lower() == name.lower() and k.active() and k.tenant_id == tenant_id for k in await self.keys.list()):
            raise ValueError(f"An active key named '{name}' already exists")
        agents, environments = _scope(agents, "agents", AGENT_ID_RE), _scope(environments, "environments", None)
        if environments and any(e not in ENVIRONMENTS for e in environments):
            raise ValueError(f"environments must be from: {', '.join(ENVIRONMENTS)}")
        if (agents is not None or environments is not None) and role in ("channel", "admin"):
            raise ValueError(f"The '{role}' role cannot be limited to agents or environments: it manages keys and platform settings (use release_manager, developer, reviewer, auditor or viewer)")
        secret = secrets.token_urlsafe(32)
        key = ApiKey(name, role, secrets.token_hex(4), hash_secret(secret), created_by,
                     expires_at=time.time() + expires_in_days * 86400 if expires_in_days else None, agents=agents, environments=environments, tenant_id=tenant_id)
        await self.keys.create(key)
        self._has_keys = True
        return key, f"{key.prefix}_{secret}"

    async def issue_session(self, display: str, role: str, hours: float, extra_roles: list[str] | None = None) -> tuple[ApiKey, str]:
        """A short-lived key for a person who signed in through the identity provider. It is an ordinary key in every other way
        (role, audit, revocation, expiry), recorded as created by 'sso'."""
        if role not in ROLES or role == "channel" or any(r not in ROLES or r == "channel" for r in extra_roles or []):
            raise ValueError(f"Cannot sign in with the '{role}' role")
        secret = secrets.token_urlsafe(32)
        key = ApiKey(("sso: " + display)[:80], role, secrets.token_hex(4), hash_secret(secret), SSO_CREATOR, expires_at=time.time() + hours * 3600,
                     extra_roles=[r for r in (extra_roles or []) if r != role] or None)
        await self.keys.create(key)
        self._has_keys = True
        return key, f"{key.prefix}_{secret}"

    async def revoke_sessions_for(self, email: str, by: str) -> int:
        """End every active sign-in session of one person (their keys are named `sso: <email>`). Returns how many were revoked."""
        name = ("sso: " + email)[:80]
        n = 0
        for k in await self.keys.list():
            if k.created_by == SSO_CREATOR and k.name == name and k.active():
                await self.keys.revoke(k.key_id, by)
                n += 1
        return n

    async def keys_of(self, tenant_id: str) -> list[ApiKey]:
        return [k for k in await self.keys.list() if k.tenant_id == tenant_id]

    async def revoke(self, key_id: str, by: str, tenant_id: str | None = None) -> ApiKey:
        """`tenant_id` limits the revoke to that tenant's keys: another tenant's key is 'unknown', not 'forbidden', so its existence is not revealed."""
        keys = await self.keys.list()
        target = next((k for k in keys if k.key_id == key_id and (tenant_id is None or k.tenant_id == tenant_id)), None)
        if target is None:
            raise KeyError(key_id)
        others = [k for k in keys if k.key_id != key_id and k.role == "admin" and k.active() and k.created_by != SSO_CREATOR and k.tenant_id == target.tenant_id]  # a sign-in session expires; it is not a lasting way in
        if target.role == "admin" and target.active() and not others and not (self.configured_keys and target.tenant_id == DEFAULT_TENANT):
            raise ValueError("This is the last active admin key; create another admin key first")
        return await self.keys.revoke(key_id, by)
