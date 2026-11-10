"""A place for each tenant's secrets (WP2.5): encrypted with a master key the operator holds, never shown again, and tied to the tenant they belong to.

A value is sealed with AES-256-GCM. The key for a value is derived from the master key and the tenant id, and the tenant id and the secret's name are also authenticated
with it, so a stored value copied into another tenant's row, or under another name, cannot be opened. The master key comes from `NORTHCX_MASTER_KEY`; to change it, put the new one in
`NORTHCX_MASTER_KEY` and the old one in `NORTHCX_MASTER_KEY_PREVIOUS`, and ask the platform API to re-seal. Without a master key the vault is off and nothing is stored.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .tenancy import TENANT

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
MIN_KEY = 32
MAX_VALUE = 4096


class VaultError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _key(master: bytes, tenant: str, version: str) -> bytes:
    return hmac.new(master, f"northcx-vault|{version}|{tenant}".encode(), hashlib.sha256).digest()


def seal(master: bytes, tenant: str, name: str, value: str, version: str = "v1") -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key(master, tenant, version)).encrypt(nonce, value.encode(), f"{tenant}|{name}".encode())
    return f"{version}:" + base64.urlsafe_b64encode(nonce + ct).decode()


def open_(masters: list[bytes], tenant: str, name: str, sealed: str) -> str:
    try:
        version, _, blob = sealed.partition(":")
        raw = base64.urlsafe_b64decode(blob.encode())
    except (ValueError, TypeError) as e:
        raise VaultError(500, "A stored secret is damaged") from e
    for m in masters:
        try:
            return AESGCM(_key(m, tenant, version)).decrypt(raw[:12], raw[12:], f"{tenant}|{name}".encode()).decode()
        except InvalidTag:
            continue
    raise VaultError(500, "A stored secret cannot be opened with the master key (wrong key, or it belongs to another tenant)")


@dataclass
class Stored:
    name: str
    sealed: str
    updated_by: str
    updated_at: float


class SecretRepo(Protocol):
    async def put(self, tenant: str, s: Stored) -> None: ...
    async def get(self, tenant: str, name: str) -> Stored | None: ...
    async def names(self, tenant: str) -> list[Stored]: ...
    async def delete(self, tenant: str, name: str) -> bool: ...


class InMemorySecrets:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Stored] = {}

    async def put(self, tenant: str, s: Stored) -> None:
        self._items[(tenant, s.name)] = s

    async def get(self, tenant: str, name: str) -> Stored | None:
        return self._items.get((tenant, name))

    async def names(self, tenant: str) -> list[Stored]:
        return sorted((s for (t, _), s in self._items.items() if t == tenant), key=lambda s: s.name)

    async def delete(self, tenant: str, name: str) -> bool:
        return self._items.pop((tenant, name), None) is not None


class Vault:
    def __init__(self, repo: SecretRepo | None = None, master: str | None = None, previous: str | None = None):
        self.repo = repo or InMemorySecrets()
        self.masters = [m.encode() for m in (master, previous) if m]
        if master and len(master) < MIN_KEY:
            raise VaultError(500, f"NORTHCX_MASTER_KEY must be at least {MIN_KEY} characters")

    @property
    def enabled(self) -> bool:
        return bool(self.masters)

    def _need(self) -> bytes:
        if not self.masters:
            raise VaultError(501, "The secrets vault is off: set NORTHCX_MASTER_KEY")
        return self.masters[0]

    async def put(self, tenant: str, name: str, value: str, by: str) -> None:
        if not NAME_RE.match(name or ""):
            raise VaultError(400, "A secret name is 2 to 40 lowercase letters, digits and _, starting with a letter")
        if not isinstance(value, str) or not 1 <= len(value) <= MAX_VALUE:
            raise VaultError(400, f"A secret value is 1 to {MAX_VALUE} characters")
        await self.repo.put(tenant, Stored(name, seal(self._need(), tenant, name, value), by[:200], time.time()))

    async def get(self, tenant: str, name: str | None = None) -> str | None:
        """The plain value, for code that must use it. Never returned by any API."""
        self._need()
        s = await self.repo.get(tenant, name or "")
        return open_(self.masters, tenant, s.name, s.sealed) if s else None

    async def names(self, tenant: str) -> list[dict[str, Any]]:
        return [{"name": s.name, "updatedBy": s.updated_by, "updatedAt": s.updated_at} for s in await self.repo.names(tenant)]

    async def delete(self, tenant: str, name: str) -> bool:
        return await self.repo.delete(tenant, name)

    async def reseal(self, tenant: str) -> int:
        """Seal every value of a tenant again with the current master key (after the key changed)."""
        n = 0
        for s in await self.repo.names(tenant):
            value = open_(self.masters, tenant, s.name, s.sealed)
            await self.repo.put(tenant, Stored(s.name, seal(self._need(), tenant, s.name, value), s.updated_by, s.updated_at))
            n += 1
        return n


# ---- a tenant's own model provider ----
def _private_literal(host: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host in ("localhost",) or host.endswith(".local") or host.endswith(".internal")
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def validate_provider(data: Any) -> dict[str, Any]:
    from urllib.parse import urlsplit
    if not isinstance(data, dict):
        raise VaultError(400, "A provider is a mapping")
    unknown = set(data) - {"baseUrl", "defaultModel", "secret", "where"}
    if unknown:
        raise VaultError(400, f"Unknown setting(s): {', '.join(sorted(unknown))}")
    url = data.get("baseUrl")
    u = urlsplit(url) if isinstance(url, str) else None
    if u is None or u.scheme != "https" or not u.hostname or u.username or u.password:
        raise VaultError(400, "baseUrl must be an https address without a password in it")
    if _private_literal(u.hostname):
        raise VaultError(400, "baseUrl must be a public address; a tenant's model provider cannot point at the platform's own network")
    model, secret, where = data.get("defaultModel"), data.get("secret"), data.get("where", "public-cloud")
    if not isinstance(model, str) or not 1 <= len(model) <= 100:
        raise VaultError(400, "defaultModel is the model name to use")
    if not isinstance(secret, str) or not NAME_RE.match(secret):
        raise VaultError(400, "secret is the name of a stored secret that holds the provider's key")
    if where not in ("local", "private-cloud", "public-cloud"):
        raise VaultError(400, "where is local, private-cloud or public-cloud")
    return {"baseUrl": url.rstrip("/"), "defaultModel": model, "secret": secret, "where": where}


class TenantLLM:
    """The model behind the runtime, with one change: a tenant that has its own provider configured is served by it. Everything else passes through untouched,
    so a deployment with no tenant providers behaves exactly as before. A tenant's provider is never mixed with the platform's: if it cannot be used, the call fails."""

    def __init__(self, inner: Any, vault: Vault, settings: Any, client: Any = None):
        self.inner, self.vault, self.settings, self._client = inner, vault, settings, client
        self._cache: dict[str, tuple[float, Any]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def _own(self, tenant: str) -> Any:
        hit = self._cache.get(tenant)
        if hit and time.monotonic() - hit[0] < 30:
            return hit[1]
        token = TENANT.set(tenant)
        try:
            cfg = await self.settings.get("tenant_provider")
        finally:
            TENANT.reset(token)
        llm = None
        if cfg:
            from .providers.openai_compat import OpenAICompatibleLLM
            key = await self.vault.get(tenant, cfg["secret"])
            if key is None:
                from .providers.base import ProviderError
                raise ProviderError("this organization's model provider is set up but its key is missing")
            llm = OpenAICompatibleLLM("tenant", cfg["baseUrl"], cfg["defaultModel"], key, client=self._client)
        self._cache[tenant] = (time.monotonic(), llm)
        return llm

    def forget(self, tenant: str) -> None:
        self._cache.pop(tenant, None)

    async def complete(self, req: Any) -> Any:
        from .tenancy import current_tenant
        own = await self._own(current_tenant())
        if own is None:
            return await self.inner.complete(req)
        return await own.complete(dataclasses.replace(req, model=None))      # the tenant's own default model; a model name from the platform's list means nothing to it
