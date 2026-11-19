"""A fake MCP server for tests: the official SDK's server behind a small ASGI wrapper that can misbehave on request. It answers over HTTP in memory
(no network), so the client under test uses its real transport. The server is dual-era: it serves the 2026-07-28 revision and, when the client asks, the
earlier handshake."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import anyio
import httpx2
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import BaseModel

SECRET = "mcp-token-0123456789"
URL = "http://localhost/mcp"


class Confirm(BaseModel):
    confirm: bool


class FakeMcp:
    """`mode`: normal | redirect (every request answered with a same-origin 307) | slow | legacy_only (refuses `server/discover` like an older server)."""

    def __init__(self) -> None:
        self.mode = "normal"
        self.note = "fine"
        self.big = 0  # make the lookup return this many extra characters
        self.requests: list[tuple[str, str, str | None]] = []  # (method, path, authorization)
        self.executed: list[tuple[str, dict[str, Any]]] = []
        self.tool_list_extra: list[str] = []
        self.token = SECRET
        server = MCPServer("fake-orders")

        @server.tool(annotations=ToolAnnotations(read_only_hint=True))
        def orders_lookup(order_id: str) -> dict:
            """Look up an order."""
            self.executed.append(("orders_lookup", {"order_id": order_id}))
            return {"id": order_id, "note": self.note.replace("{secret}", SECRET) + "x" * self.big}

        @server.tool()
        def orders_refund(order_id: str, amount: float) -> dict:
            """Refund an order."""
            self.executed.append(("orders_refund", {"order_id": order_id, "amount": amount}))
            return {"refunded": amount}

        @server.tool(annotations=ToolAnnotations(read_only_hint=True))
        async def asks_a_question(ctx: Context) -> str:
            """A tool that wants the user to answer something first."""
            await ctx.elicit("Are you sure?", Confirm)
            return "done"

        self.server = server
        self.app = server.streamable_http_app(transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    @asynccontextmanager
    async def running(self) -> AsyncIterator["FakeMcp"]:
        async with self.app.router.lifespan_context(self.app):
            yield self

    async def start(self) -> None:
        """Run the server in a task of its own, for a fixture whose setup and teardown are not the same task (`running` must enter and leave in one)."""
        ready, self._stop = asyncio.Event(), asyncio.Event()

        async def serve() -> None:
            async with self.running():
                ready.set()
                await self._stop.wait()

        self._task = asyncio.create_task(serve())
        await ready.wait()

    async def stop(self) -> None:
        self._stop.set()
        await self._task

    def transport(self) -> httpx2.AsyncBaseTransport:
        return httpx2.ASGITransport(app=self._call)

    async def _call(self, scope: dict, receive: Any, send: Any) -> None:
        headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        self.requests.append((scope["method"], scope["path"], headers.get("authorization")))
        if headers.get("authorization") != f"Bearer {self.token}" and self.token:
            await self._reply(send, 401, b'{"error":"unauthorized"}')
            return
        if self.mode == "redirect":
            await send({"type": "http.response.start", "status": 307, "headers": [(b"location", b"/elsewhere")]})
            await send({"type": "http.response.body", "body": b""})
            return
        if self.mode == "slow":
            await anyio.sleep(1.0)
        body = b""
        more = True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
        if self.mode == "legacy_only" and b"server/discover" in body:
            await self._reply(send, 400, b"{}")
            return
        sent = False

        async def replay() -> dict:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reply(send: Any, status: int, body: bytes) -> None:
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
