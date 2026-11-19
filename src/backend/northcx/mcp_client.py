"""The MCP client: the only module that imports the official SDK (decision 200), so it can be replaced without touching anything else.

Every call opens its own connection, because the 2026-07-28 revision has no sessions (older servers are reached through the SDK's handshake fallback).
The operator's rules are applied here, not by the server's good behaviour: the server's host must be on the allowlist, the address must be https (http
only for localhost), a redirect of any kind is refused, a call times out, a result over the size cap is refused, and calls are rate limited. The
credential is looked up by name in the secret store when the call is made and is never part of a message that is returned.

Every failure is an `McpError` whose text is written for the person or agent who reads it (what failed and what to do), never a traceback or an address."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from .access import RateLimiter
from .secrets import NO_SECRETS, SecretStore

MAX_RESULT_BYTES = 256 * 1024
MAX_PAGES, MAX_TOOLS = 10, 200
MAX_ERROR_TEXT = 500


class McpError(Exception):
    """A failure with a message for the reader."""


@dataclass(frozen=True)
class McpToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only_hint: bool | None = None  # the server's claim, which counts only on a connection the operator trusts


async def _refuse_redirect(response: httpx2.Response) -> None:
    if response.is_redirect:
        raise McpError("The server answered with a redirect, which is not followed. Use the server's final address in the connection.")


def _leaf(e: BaseException) -> BaseException:
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


class McpClient:
    def __init__(self, name: str, url: str, allowed_hosts: set[str], *, secret: str | None = None, timeout: float = 30.0, max_result_bytes: int = MAX_RESULT_BYTES,
                 calls_per_minute: float = 60, limiter: RateLimiter | None = None, transport: httpx2.AsyncBaseTransport | None = None, mode: str = "auto"):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        local = host in ("localhost", "127.0.0.1", "::1")
        if parts.scheme != "https" and not (parts.scheme == "http" and local):
            raise McpError(f"The address of '{name}' must start with https:// (http:// is allowed only for localhost). Change the connection's address.")
        if host not in {h.lower().split(":")[0] for h in allowed_hosts}:
            raise McpError(f"The host '{host}' is not on the allowed list for MCP servers. Ask the operator to add it if the server is trusted.")
        if parts.username or parts.password:
            raise McpError(f"The address of '{name}' must not contain a user name or password; use a secret for the credential.")
        self.name, self.url, self.secret, self.timeout, self.mode = name, url, secret, timeout, mode
        self.max_result_bytes, self.calls_per_minute = max_result_bytes, calls_per_minute
        self.limiter = limiter or RateLimiter()
        self._transport = transport

    @asynccontextmanager
    async def _connect(self, secrets: SecretStore) -> AsyncIterator[Client]:
        headers: dict[str, str] = {}
        if self.secret:
            try:
                headers["authorization"] = f"Bearer {secrets.get(self.secret)}"
            except KeyError:
                raise McpError(f"The credential '{self.secret}' for '{self.name}' is not configured. Set it in the secrets before using this connection.") from None
        http = httpx2.AsyncClient(transport=self._transport, timeout=httpx2.Timeout(self.timeout), headers=headers, follow_redirects=False,
                                  event_hooks={"response": [_refuse_redirect]})
        try:
            with anyio.fail_after(self.timeout):
                async with http, Client(streamable_http_client(self.url, http_client=http), mode=self.mode, read_timeout_seconds=self.timeout) as client:
                    yield client
        except McpError:
            raise
        except Exception as e:  # an SDK or transport failure becomes a message for the reader; cancellation is not an Exception and passes through
            raise McpError(self._explain(_leaf(e))) from None

    def _explain(self, e: BaseException) -> str:
        if isinstance(e, McpError):
            return str(e)
        if isinstance(e, (TimeoutError, httpx2.TimeoutException)):
            return f"The {self.name} system did not answer in time. Try again, or hand this to a person."
        if isinstance(e, (httpx2.ConnectError, httpx2.NetworkError)):
            return f"The {self.name} system could not be reached. Try again, or hand this to a person."
        if isinstance(e, MCPError):
            return f"The {self.name} system refused the request. Check the connection's credential and permissions."
        return f"The {self.name} system returned an answer that could not be used. Try again, or hand this to a person."

    async def list_tools(self, secrets: SecretStore = NO_SECRETS) -> list[McpToolInfo]:
        tools: list[McpToolInfo] = []
        async with self._connect(secrets) as client:
            cursor = None
            for _ in range(MAX_PAGES):
                page = await client.list_tools(cursor=cursor)
                for t in page.tools:
                    ann = t.annotations
                    tools.append(McpToolInfo(t.name, t.description or t.title or "", dict(t.input_schema or {}), ann.read_only_hint if ann else None))
                if len(tools) > MAX_TOOLS:
                    raise McpError(f"The {self.name} system lists more than {MAX_TOOLS} tools. Use a server that offers fewer.")
                cursor = page.next_cursor
                if not cursor:
                    return tools
        raise McpError(f"The {self.name} system's tool list has more than {MAX_PAGES} pages, which is more than NorthCX reads.")

    async def call_tool(self, tool: str, arguments: dict[str, Any], secrets: SecretStore = NO_SECRETS) -> Any:
        allowed, wait = await self.limiter.hit(f"mcp:{self.name}", self.calls_per_minute)
        if not allowed:
            raise McpError(f"Too many calls to the {self.name} system. Try again in {int(wait) + 1} seconds.")
        async with self._connect(secrets) as client:
            result = await client.call_tool(tool, arguments, read_timeout_seconds=self.timeout)
        text = "\n".join(b.text for b in result.content if getattr(b, "type", None) == "text")
        if result.result_type != "complete":
            raise McpError(f"The {self.name} system asked for more input, which an agent cannot give. Hand this to a person.")
        if result.is_error:
            raise McpError(f"The {self.name} system reported a problem: {text[:MAX_ERROR_TEXT]}")
        out: Any = result.structured_content if result.structured_content is not None else {"text": text}
        omitted = sum(1 for b in result.content if getattr(b, "type", None) != "text")
        if omitted and isinstance(out, dict) and result.structured_content is None:
            out["omitted"] = f"{omitted} item(s) that are not text"
        if len(json.dumps(out, default=str).encode()) > self.max_result_bytes:
            raise McpError(f"The {self.name} system's answer is larger than the {self.max_result_bytes // 1024} KB allowed, so it was not used.")
        return out
