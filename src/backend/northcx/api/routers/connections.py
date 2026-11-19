"""Routes for connections to MCP servers: the operator adds one, reviews what the server offers, approves tools, switches it off and checks it for changes."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from northcx.api.common import _err
from northcx.api.deps import AppDeps
from northcx.api.models import ApproveBody, ConnectionBody, ConnectionUpdateBody
from northcx.mcp_connections import McpConnection, McpConnectionError, McpConnections


def register(app: FastAPI, d: AppDeps) -> None:
    access, record, runtime, too_many = d.access, d.record, d.runtime, d.too_many

    def svc() -> McpConnections | JSONResponse:
        return getattr(runtime, "mcp", None) or _err(501, "not_configured", "MCP connections are not configured on this server")

    def fail(e: McpConnectionError) -> JSONResponse:
        return _err(e.status, {400: "bad_request", 404: "not_found", 409: "conflict", 502: "server_unreachable", 501: "not_configured"}.get(e.status, "error"), str(e))

    def view(c: McpConnection) -> dict[str, Any]:
        return {"id": c.id, "name": c.name, "url": c.url, "host": urlsplit(c.url).hostname, "trusted": c.trusted, "secret": c.secret, "enabled": c.enabled,
                "approvedTools": [f"{c.name}__{t['name']}" for t in c.approved], "createdBy": c.created_by, "createdAt": c.created_at, "updatedBy": c.updated_by, "updatedAt": c.updated_at}

    async def asks_the_server(request: Request, what: str) -> JSONResponse | None:
        who = request.state.identity
        if not (await access.limiter.hit(f"mcp-{what}:{who.key_id or 'open'}", 12))[0]:
            return too_many(60, "requests to MCP servers")
        return None

    @app.get("/v1/connections")
    async def list_connections() -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            return {"connections": [view(c) for c in await s.list()], "allowedHosts": sorted(s.allowed_hosts)}
        except McpConnectionError as e:
            return fail(e)

    @app.post("/v1/connections", status_code=201)
    async def create_connection(body: ConnectionBody, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            c = await s.create(body.name, body.url, body.secret, body.trusted, request.state.identity.name)
        except McpConnectionError as e:
            return fail(e)
        await record(request, "connection.create", c.name, id=c.id, host=urlsplit(c.url).hostname, trusted=c.trusted)
        return view(c)

    @app.get("/v1/connections/{connection_id}")
    async def get_connection(connection_id: str) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            return view(await s.get(connection_id))
        except McpConnectionError as e:
            return fail(e)

    @app.put("/v1/connections/{connection_id}")
    async def update_connection(connection_id: str, body: ConnectionUpdateBody, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            c = await s.update(connection_id, request.state.identity.name, trusted=body.trusted, enabled=body.enabled, secret=body.secret, clear_secret=body.clear_secret)
        except McpConnectionError as e:
            return fail(e)
        await record(request, "connection.update", c.name, id=c.id, trusted=c.trusted, enabled=c.enabled, secret=c.secret)
        return view(c)

    @app.delete("/v1/connections/{connection_id}")
    async def delete_connection(connection_id: str, request: Request) -> Any:
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        try:
            c = await s.delete(connection_id)
        except McpConnectionError as e:
            return fail(e)
        await record(request, "connection.delete", c.name, id=c.id)
        return {"deleted": True}

    @app.post("/v1/connections/{connection_id}/review")
    async def review_connection(connection_id: str, request: Request) -> Any:
        """Ask the server what it offers now. Nothing is approved by looking."""
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        if (limited := await asks_the_server(request, "review")) is not None:
            return limited
        try:
            out = await s.review(connection_id)
        except McpConnectionError as e:
            return fail(e)
        await record(request, "connection.review", connection_id, tools=len(out["tools"]), skipped=len(out["skipped"]))
        return out

    @app.post("/v1/connections/{connection_id}/approve")
    async def approve_tools(connection_id: str, body: ApproveBody, request: Request) -> Any:
        """Approve exactly these tools, each with the fingerprint seen in the review. An empty list withdraws every approval."""
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        if (limited := await asks_the_server(request, "approve")) is not None:
            return limited
        try:
            c = await s.approve(connection_id, body.tools, request.state.identity.name)
        except McpConnectionError as e:
            return fail(e)
        await record(request, "connection.approve", c.name, id=c.id, tools=sorted(body.tools))
        return view(c)

    @app.post("/v1/connections/{connection_id}/check")
    async def check_connection(connection_id: str, request: Request) -> Any:
        """Whether the server still offers what was approved: tools added, changed or removed, or the server not answering."""
        s = svc()
        if isinstance(s, JSONResponse):
            return s
        if (limited := await asks_the_server(request, "check")) is not None:
            return limited
        try:
            out = await s.check(connection_id)
        except McpConnectionError as e:
            return fail(e)
        await record(request, "connection.check", connection_id, reachable=out["reachable"], changed=len(out["changed"]), added=len(out["added"]), removed=len(out["removed"]))
        return out
