"""Protections that apply to every request, whatever the endpoint: a cap on how much a request may send, and safe default response headers.

Both are plain ASGI middleware so they work for streaming responses and cannot be skipped by a route that forgets them.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

DEFAULT_LIMIT = 1 * 1024 * 1024
# Endpoints that legitimately take more: (path prefix, bytes)
LARGER = (("/v1/sessions/", 11 * 1024 * 1024, "/attachments"), ("/v1/knowledge/", 11 * 1024 * 1024, "/import"), ("/v1/knowledge/", 4 * 1024 * 1024, ""), ("/v1/channels/email/inbound", 1_100_000, ""))


def limit_for(method: str, path: str) -> int:
    if method in ("GET", "HEAD", "OPTIONS", "DELETE"):
        return 64 * 1024
    for prefix, size, contains in LARGER:
        if path.startswith(prefix) and contains in path:
            return size
    return DEFAULT_LIMIT


class BodyLimit:
    """Refuses a request whose body is bigger than its endpoint allows, by its declared length or, when it does not declare one, as it arrives."""

    def __init__(self, app: Callable[..., Awaitable[None]]):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cap = limit_for(scope["method"], scope["path"])
        declared = next((v for k, v in scope["headers"] if k == b"content-length"), None)
        if declared is not None and declared.isdigit() and int(declared) > cap:
            await self._refuse(send)
            return
        seen = 0
        over = False
        replied = False

        async def counting() -> dict[str, Any]:
            nonlocal seen, over
            if over:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > cap:  # stop feeding the app; whatever it answers is replaced by a 413
                    over = True
                    return {"type": "http.disconnect"}
            return msg

        async def watching(msg: dict[str, Any]) -> None:
            nonlocal replied
            if over:
                if not replied:
                    replied = True
                    await self._refuse(send)
                return
            await send(msg)

        await self.app(scope, counting, watching)
        if over and not replied:
            await self._refuse(send)

    @staticmethod
    async def _refuse(send: Send) -> None:
        body = json.dumps({"error": {"code": "too_large", "message": "The request is too large"}}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})


SECURITY_HEADERS = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"), (b"x-frame-options", b"DENY"),
                    (b"cross-origin-resource-policy", b"cross-origin"), (b"permissions-policy", b"camera=(), microphone=(), geolocation=()")]


class SecurityHeaders:
    """Adds protective headers to every response that does not set its own; API responses are never cached."""

    def __init__(self, app: Callable[..., Awaitable[None]]):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        api = scope["path"].startswith("/v1/") or scope["path"].startswith("/auth/")

        async def wrapped(msg: dict[str, Any]) -> None:
            if msg["type"] == "http.response.start":
                have = {k.lower() for k, _ in msg.get("headers", [])}
                extra = [(k, v) for k, v in SECURITY_HEADERS if k not in have]
                if api and b"cache-control" not in have:
                    extra.append((b"cache-control", b"no-store"))
                msg = {**msg, "headers": [*msg.get("headers", []), *extra]}
            await send(msg)

        await self.app(scope, receive, wrapped)
