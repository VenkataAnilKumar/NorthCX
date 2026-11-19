"""Connections to MCP servers (Phase 2, WP 2.3): what the operator sets up, approves and switches off.

A connection is a name (the prefix of its tools), the server's address, an optional credential (the name of a tool secret), whether the operator trusts
the server, whether it is switched on, and the tool definitions the operator approved. Approval stores the definitions, so start-up needs no network and
agents always see exactly what was approved, whatever the server offers later. Every call checks, through a gate, that the connection is still on and the
tool is still the approved one, so a switched-off or changed connection stops agents that were built earlier.

Connections belong to the operator's own tenant for now: in the multi-tenant preview the tool registry is shared by every tenant, so a tenant other than
the default is refused (fail closed) until each tenant has its own."""
from __future__ import annotations

import asyncio
import logging
import re
import secrets as _secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .agent import tool_fingerprint
from .mcp_client import McpClient, McpError, McpToolInfo
from .mcp_source import CONNECTION_NAME, McpSource
from .secrets import SecretStore
from .tenancy import DEFAULT_TENANT, TENANT

SECRET_NAME = re.compile(r"[a-z][a-z0-9_]{1,39}")
log = logging.getLogger("northcx.mcp")


class McpConnectionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class McpConnection:
    id: str
    name: str
    url: str
    trusted: bool = False
    secret: str | None = None
    enabled: bool = True
    approved: list[dict[str, Any]] = field(default_factory=list)  # the approved tool definitions (McpToolInfo as a dict)
    created_by: str = ""
    created_at: float = 0.0
    updated_by: str = ""
    updated_at: float = 0.0


class McpConnectionRepo(Protocol):
    async def save(self, c: McpConnection) -> None: ...
    async def get(self, connection_id: str) -> McpConnection | None: ...
    async def get_by_name(self, name: str) -> McpConnection | None: ...
    async def list(self) -> list[McpConnection]: ...
    async def delete(self, connection_id: str) -> bool: ...


class InMemoryMcpConnections:
    def __init__(self) -> None:
        self._items: dict[str, McpConnection] = {}

    async def save(self, c: McpConnection) -> None:
        self._items[c.id] = c

    async def get(self, connection_id: str) -> McpConnection | None:
        return self._items.get(connection_id)

    async def get_by_name(self, name: str) -> McpConnection | None:
        return next((c for c in self._items.values() if c.name == name), None)

    async def list(self) -> list[McpConnection]:
        return sorted(self._items.values(), key=lambda c: c.name)

    async def delete(self, connection_id: str) -> bool:
        return self._items.pop(connection_id, None) is not None


def visible_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """The tool catalogue as the current tenant may see it: the operator's MCP tools are not listed to any other tenant."""
    if TENANT.get() == DEFAULT_TENANT:
        return catalog
    return {**catalog, "tools": [t for t in catalog["tools"] if t["source"] != "mcp"]}


def _infos(c: McpConnection) -> list[McpToolInfo]:
    return [McpToolInfo(**d) for d in c.approved]


class McpConnections:
    def __init__(self, repo: McpConnectionRepo | None, registry: Any, allowed_hosts: set[str], secrets: SecretStore, *, transport: Any = None, limiter: Any = None):
        self.repo = repo or InMemoryMcpConnections()
        self.registry, self.allowed_hosts, self.secrets, self.transport, self.limiter = registry, allowed_hosts, secrets, transport, limiter
        self._synced: dict[str, tuple[float, str]] = {}  # connection id to (when it last changed, its name) as of the last registration

    # ---- building blocks ----
    @staticmethod
    def _only_here() -> None:
        if TENANT.get() != DEFAULT_TENANT:
            raise McpConnectionError(501, "MCP connections are not available to tenants in the multi-tenant preview yet. Ask the operator.")

    def _client(self, c: McpConnection) -> McpClient:
        try:
            return McpClient(c.name, c.url, self.allowed_hosts, secret=c.secret, transport=self.transport, limiter=self.limiter)
        except McpError as e:
            raise McpConnectionError(400, str(e)) from None

    def _gate(self, connection_id: str):
        async def gate(name: str, info: McpToolInfo, trusted: bool) -> None:
            c = await self.repo.get(connection_id)
            if c is None or not c.enabled:
                raise McpError("This connection is switched off. Ask the operator to switch it on.")
            if c.trusted != trusted or info not in _infos(c):
                raise McpError("This tool changed since it was approved, or was withdrawn. Ask the operator to approve it again, then publish the agent again.")
        return gate

    def _source(self, c: McpConnection) -> McpSource:
        return McpSource(c.name, self._client(c), trusted=c.trusted, secrets=self.secrets, gate=self._gate(c.id))

    async def _sync(self, c: McpConnection) -> None:
        """Make the registry hold exactly the approved tools of this connection (none when it is switched off)."""
        self.registry.remove_tools("mcp", f"{c.name}__")
        self._synced.pop(c.id, None)
        if c.enabled and c.approved:
            self.registry.add_tools("mcp", await self._source(c).tools_from(_infos(c)))
        self._synced[c.id] = (c.updated_at, c.name)

    async def load(self) -> None:
        """Register the approved tools of every connection from the stored definitions, without asking any server, and drop those of connections that are gone. Run at
        start-up and then every half minute, so a change made through another server process is picked up. A connection that cannot be built (its host is no longer
        allowed) is left out and logged, never half-registered."""
        present = set()
        for c in await self.repo.list():
            present.add(c.id)
            if self._synced.get(c.id, (None, ""))[0] == c.updated_at:
                continue
            try:
                await self._sync(c)
            except Exception as e:  # noqa: BLE001
                self.registry.remove_tools("mcp", f"{c.name}__")
                log.warning("MCP connection '%s' was not registered: %s", c.name, e)
        for gone in set(self._synced) - present:
            self.registry.remove_tools("mcp", f"{self._synced.pop(gone)[1]}__")

    async def keep_current(self, every: float = 30.0) -> None:
        while True:
            try:
                await self.load()
            except Exception as e:  # noqa: BLE001  (the database was unreachable: try again)
                log.warning("MCP connections could not be reloaded: %s", e)
            await asyncio.sleep(every)

    async def _get(self, connection_id: str) -> McpConnection:
        self._only_here()
        c = await self.repo.get(connection_id)
        if c is None:
            raise McpConnectionError(404, "Unknown connection")
        return c

    # ---- what the operator does ----
    async def list(self) -> list[McpConnection]:
        self._only_here()
        return await self.repo.list()

    async def get(self, connection_id: str) -> McpConnection:
        return await self._get(connection_id)

    async def create(self, name: str, url: str, secret: str | None, trusted: bool, by: str) -> McpConnection:
        self._only_here()
        if not CONNECTION_NAME.fullmatch(name or ""):
            raise McpConnectionError(400, "A connection name is 1 to 24 lowercase letters, digits or hyphens.")
        if await self.repo.get_by_name(name):
            raise McpConnectionError(409, f"There is already a connection named '{name}'.")
        now = time.time()
        c = McpConnection(_secrets.token_hex(8), name, url, trusted, None, True, [], by, now, by, now)
        self._check_secret(secret)
        c.secret = secret
        self._client(c)  # the address, scheme and host rules
        await self.repo.save(c)
        return c

    def _check_secret(self, secret: str | None) -> None:
        if secret is None:
            return
        if not SECRET_NAME.fullmatch(secret) or secret not in self.secrets.names():
            raise McpConnectionError(400, f"The secret '{secret}' is not configured. Set NORTHCX_SECRET_{secret.upper()} for the server first.")

    async def update(self, connection_id: str, by: str, *, trusted: bool | None = None, enabled: bool | None = None, secret: str | None = None, clear_secret: bool = False) -> McpConnection:
        c = await self._get(connection_id)
        if trusted is not None:
            c.trusted = trusted
        if enabled is not None:
            c.enabled = enabled
        if clear_secret:
            c.secret = None
        elif secret is not None:
            self._check_secret(secret)
            c.secret = secret
        c.updated_by, c.updated_at = by, time.time()
        await self.repo.save(c)
        await self._sync(c)
        return c

    async def delete(self, connection_id: str) -> McpConnection:
        c = await self._get(connection_id)
        await self.repo.delete(connection_id)
        self.registry.remove_tools("mcp", f"{c.name}__")
        self._synced.pop(connection_id, None)
        return c

    async def review(self, connection_id: str) -> dict[str, Any]:
        """Ask the server what it offers now, for the operator to look at. Each tool carries the fingerprint to send back when approving it."""
        c = await self._get(connection_id)
        source = self._source(c)
        try:
            tools = await source.review()
        except McpError as e:
            raise McpConnectionError(502, str(e)) from None
        pinned = {t.name: tool_fingerprint(t) for t in await self._source(c).tools_from(_infos(c))}
        return {"tools": [{"name": t.name, "serverName": source.offered[t.name].name, "description": t.description, "inputs": list(t.spec()["input_schema"].get("properties", {})),
                           "access": "reads" if t.effect == "read" else "changes", "fingerprint": tool_fingerprint(t), "approved": pinned.get(t.name) == tool_fingerprint(t)}
                          for t in tools],
                "skipped": [{"name": n, "reason": why} for n, why in source.skipped]}

    async def approve(self, connection_id: str, chosen: dict[str, str], by: str) -> McpConnection:
        """Approve exactly these tools, each with the fingerprint the operator saw. If the server changed a tool since, nothing is approved."""
        c = await self._get(connection_id)
        source = self._source(c)
        try:
            tools = {t.name: t for t in await source.review()}
        except McpError as e:
            raise McpConnectionError(502, str(e)) from None
        for name, seen in chosen.items():
            if name not in tools:
                raise McpConnectionError(400, f"The server does not offer '{name}' (any more). Review the tools again.")
            if tool_fingerprint(tools[name]) != seen:
                raise McpConnectionError(409, f"'{name}' changed since you looked at it. Review the tools again before approving.")
        c.approved = [asdict(source.offered[n]) for n in sorted(chosen)]
        c.updated_by, c.updated_at = by, time.time()
        await self.repo.save(c)
        await self._sync(c)
        return c

    async def check(self, connection_id: str) -> dict[str, Any]:
        """Whether the server still offers what was approved: added, changed and removed tools."""
        c = await self._get(connection_id)
        source = McpSource(c.name, self._client(c), trusted=c.trusted, secrets=self.secrets,
                           approved={t.name: tool_fingerprint(t) for t in await self._source(c).tools_from(_infos(c))})
        try:
            await source.discover()
        except McpError as e:
            return {"reachable": False, "message": str(e), "added": [], "changed": [], "removed": []}
        ch = source.changes
        return {"reachable": True, "message": None, "added": ch.added, "changed": ch.changed, "removed": ch.removed}
