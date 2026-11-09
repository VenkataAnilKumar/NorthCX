"""Tenants (WP2.2): who a request belongs to. First slice of multi-tenancy; see docs/05-technical/NorthCX_Tenancy-ADR.md.

What exists: the `tenants` and `channel_bindings` tables, a request-scoped current tenant (set from the key), keys and the audit log carrying a
tenant, and the key and audit APIs showing a caller only their own tenant. What does NOT exist yet: tenant columns on every other table (WP2.3
batches b to f), row-level security (WP2.4) and the isolation gates (WP2.9). Until those are done a second tenant must not be created on a
real deployment, so creating one needs NORTHCX_TENANCY_PREVIEW=1. A deployment with no tenants configured is the single tenant `default`
and behaves exactly as before."""
from __future__ import annotations

import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_TENANT = "default"
TENANT: ContextVar[str] = ContextVar("northcx_tenant", default=DEFAULT_TENANT)
TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
BINDING_KINDS = ("phone", "sms", "whatsapp", "telegram", "email_domain", "voice")


def current_tenant() -> str:
    return TENANT.get()


class TenantError(ValueError):
    pass


@dataclass
class Tenant:
    id: str
    name: str
    status: str = "active"  # active | suspended
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "status": self.status, "createdAt": self.created_at}


@dataclass
class Binding:
    kind: str
    address: str  # a phone number id, bot id, SMS number, email domain or voice number, lower case
    tenant_id: str
    created_at: float = field(default_factory=time.time)


class TenantRepo(Protocol):
    async def list(self) -> list[Tenant]: ...
    async def get(self, tenant_id: str) -> Tenant | None: ...
    async def save(self, t: Tenant) -> None: ...
    async def bind(self, b: Binding) -> bool: ...  # False when that address already belongs to someone
    async def unbind(self, kind: str, address: str) -> bool: ...
    async def resolve(self, kind: str, address: str) -> str | None: ...
    async def bindings(self, tenant_id: str) -> list[Binding]: ...


class InMemoryTenants:
    def __init__(self) -> None:
        self._t: dict[str, Tenant] = {DEFAULT_TENANT: Tenant(DEFAULT_TENANT, "Default")}
        self._b: dict[tuple[str, str], Binding] = {}

    async def list(self) -> list[Tenant]:
        return sorted(self._t.values(), key=lambda t: t.created_at)

    async def get(self, tenant_id: str) -> Tenant | None:
        t = self._t.get(tenant_id)
        return Tenant(t.id, t.name, t.status, t.created_at) if t else None

    async def save(self, t: Tenant) -> None:
        self._t[t.id] = Tenant(t.id, t.name, t.status, t.created_at)

    async def bind(self, b: Binding) -> bool:
        if (b.kind, b.address) in self._b:
            return False
        self._b[(b.kind, b.address)] = b
        return True

    async def unbind(self, kind: str, address: str) -> bool:
        return self._b.pop((kind, address), None) is not None

    async def resolve(self, kind: str, address: str) -> str | None:
        b = self._b.get((kind, address))
        return b.tenant_id if b else None

    async def bindings(self, tenant_id: str) -> list[Binding]:
        return [b for b in self._b.values() if b.tenant_id == tenant_id]


class TenantService:
    def __init__(self, repo: TenantRepo | None = None, preview: bool = False):
        self.repo, self.preview = repo or InMemoryTenants(), preview

    async def create(self, tenant_id: str, name: str) -> Tenant:
        if not self.preview:
            raise TenantError("Creating a tenant other than the default one needs NORTHCX_TENANCY_PREVIEW=1: tenant isolation is not finished yet "
                              "(see docs/05-technical/NorthCX_Tenancy-ADR.md), so a second tenant is for evaluation only")
        if not TENANT_ID_RE.fullmatch(tenant_id) or tenant_id == DEFAULT_TENANT:
            raise TenantError("A tenant id is 3 to 40 lower-case letters, digits and hyphens, and is not 'default'")
        if not name.strip() or len(name) > 120:
            raise TenantError("A tenant needs a name of up to 120 characters")
        if await self.repo.get(tenant_id) is not None:
            raise TenantError(f"Tenant '{tenant_id}' already exists")
        t = Tenant(tenant_id, name.strip())
        await self.repo.save(t)
        return t

    async def set_status(self, tenant_id: str, status: str) -> Tenant:
        t = await self.repo.get(tenant_id)
        if t is None:
            raise KeyError(tenant_id)
        if tenant_id == DEFAULT_TENANT and status != "active":
            raise TenantError("The default tenant cannot be suspended")
        if status not in ("active", "suspended"):
            raise TenantError("status must be active or suspended")
        t.status = status
        await self.repo.save(t)
        return t

    async def is_active(self, tenant_id: str) -> bool:
        t = await self.repo.get(tenant_id)
        return t is not None and t.status == "active"

    async def bind(self, tenant_id: str, kind: str, address: str) -> Binding:
        address = address.strip().lower()
        if kind not in BINDING_KINDS or not address or len(address) > 200:
            raise TenantError(f"A binding is one of {', '.join(BINDING_KINDS)} and a non-empty address")
        if await self.repo.get(tenant_id) is None:
            raise KeyError(tenant_id)
        b = Binding(kind, address, tenant_id)
        if not await self.repo.bind(b):
            raise TenantError(f"The {kind} address '{address}' already belongs to a tenant; an address can belong to only one")
        return b

    async def resolve(self, kind: str, address: str) -> str | None:
        """The tenant an inbound message belongs to. None means unbound: the caller must ignore it (never guess a tenant)."""
        return await self.repo.resolve(kind, address.strip().lower())
