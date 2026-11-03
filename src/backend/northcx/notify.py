from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

import httpx

from .outbox import OutboxMessage


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify(secret: str, timestamp: str, body: bytes, signature: str, tolerance: float = 300, now: float | None = None) -> bool:
    """For receivers: constant-time signature check plus a replay window."""
    if abs((now or time.time()) - float(timestamp)) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)


class CompositeNotifier:
    """Several notifiers behind one outbox. Each ignores messages that are not its business; if any that applies fails,
    the message is retried (the others must therefore tolerate being told again)."""

    def __init__(self, *notifiers) -> None:
        self.notifiers = notifiers

    async def deliver(self, message: OutboxMessage) -> None:
        errors = []
        for n in self.notifiers:
            try:
                await n.deliver(message)
            except Exception as e:
                errors.append(e)
        if errors:
            raise RuntimeError("; ".join(str(e) for e in errors))


class WebhookNotifier:
    """POSTs each message as JSON, signed with HMAC-SHA256 over `timestamp.body`. Retries with backoff."""

    def __init__(self, url: str, secret: str, client: httpx.AsyncClient | None = None,
                 attempts: int = 3, backoff: float = 0.5, timeout: float = 5.0):
        self.url, self.secret, self.attempts, self.backoff = url, secret, attempts, backoff
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def deliver(self, message: OutboxMessage) -> None:
        body = json.dumps({"id": message.id, "sessionId": message.session_id, "kind": message.kind,
                           "payload": message.payload, "createdAt": message.created_at}, sort_keys=True).encode()
        last: Exception | None = None
        for i in range(self.attempts):
            ts = str(int(time.time()))
            try:
                r = await self._client.post(self.url, content=body, headers={
                    "content-type": "application/json", "x-northcx-timestamp": ts,
                    "x-northcx-signature": sign(self.secret, ts, body)})
                if r.status_code < 300:
                    return
                last = RuntimeError(f"webhook returned {r.status_code}")
            except httpx.HTTPError as e:
                last = e
            if i < self.attempts - 1:
                await asyncio.sleep(self.backoff * (2 ** i))
        raise RuntimeError(f"webhook delivery failed: {last}")
