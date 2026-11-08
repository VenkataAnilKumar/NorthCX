"""Status events for other systems (P8): what happened on the platform, as small signed webhook calls or a pollable feed.

An event says that something happened and names it (ids, the tool, the queue, the outcome); it never carries what a customer
said or what an agent replied. Events come from two places: the audit trail (every staff action is already recorded there, so the
feed cannot drift from it) and a few moments inside conversations (a hand-off was created, an approval was requested, a rating was
left, an alert fired). They are stored in the outbox, so a receiver that is down gets them again later, and the signature scheme is
the same as for reply webhooks.
"""
from __future__ import annotations

import logging
from typing import Any

from .audit import AuditEntry
from .notify import WebhookNotifier
from .outbox import Outbox, OutboxMessage

log = logging.getLogger("northcx.events")
KIND = "event:"
FEED_SESSION = "-"

EVENTS: dict[str, str] = {
    "handoff.created": "A conversation was put in a hand-off queue for a person",
    "handoff.resolved": "A person resolved a hand-off",
    "approval.requested": "A tool call is waiting for a person's approval",
    "approval.decided": "A person approved or rejected a tool call",
    "approval.expired": "An approval was not decided in time and the conversation was handed to a person",
    "conversation.abuse": "Abusive language, a threat, repeated messages or a burst was noticed in a conversation (kinds and strikes only)",
    "conversation.rated": "A customer rated a conversation (the rating only, not the comment)",
    "alert.fired": "A monitoring alert rule started firing",
    "version.created": "A new agent version was saved",
    "release.published": "An agent version went live in an environment",
    "release.rolled_back": "An environment was rolled back to an earlier version",
    "rollout.changed": "A staged rollout was started, changed, promoted or stopped",
    "key.created": "An API key was created",
    "key.revoked": "An API key was revoked",
    "knowledge.changed": "A knowledge document or source was added, changed or removed",
    "privacy.erased": "A conversation or customer was erased",
}
# audit action -> event type
FROM_AUDIT = {
    "version.create": "version.created", "template.create_version": "version.created",
    "release.publish": "release.published", "release.promote": "release.published", "release.rollback": "release.rolled_back",
    "rollout.start": "rollout.changed", "rollout.percent": "rollout.changed", "rollout.promote": "rollout.changed", "rollout.abort": "rollout.changed",
    "key.create": "key.created", "key.revoke": "key.revoked",
    "approval.decide": "approval.decided", "approval.expire": "approval.expired", "handoff.resolve": "handoff.resolved",
    "knowledge.document.put": "knowledge.changed", "knowledge.document.delete": "knowledge.changed", "knowledge.source.create": "knowledge.changed",
    "knowledge.source.delete": "knowledge.changed", "knowledge.import": "knowledge.changed",
    "privacy.erase.customer": "privacy.erased", "privacy.erase.session": "privacy.erased",
}
_SAFE_TYPES = (str, int, float, bool)


def scalars(d: dict[str, Any] | None, limit: int = 12) -> dict[str, Any]:
    """Only short plain values: nothing nested, nothing long enough to be a message."""
    out: dict[str, Any] = {}
    for k, v in (d or {}).items():
        if isinstance(v, _SAFE_TYPES) and not isinstance(v, bytes) and len(out) < limit and (not isinstance(v, str) or len(v) <= 200):
            out[str(k)[:40]] = v
    return out


class EventFeed:
    def __init__(self, outbox: Outbox, types: set[str] | None = None):
        self.outbox = outbox
        self.types = set(types) if types else set(EVENTS)
        self.webhook: Any = None  # the EventWebhook, so a test call can use exactly the configured address and secret

    async def emit(self, type_: str, data: dict[str, Any] | None = None, session_id: str | None = None) -> None:
        """Never raises: a problem with the feed must not break the thing that happened."""
        if type_ not in self.types:
            return
        try:
            await self.outbox.publish(FEED_SESSION, KIND + type_, {"type": type_, "sessionId": session_id, "data": scalars(data)})
        except Exception:
            log.exception("could not record event %s", type_)

    async def listing(self, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        items = await self.outbox.repo.list(FEED_SESSION, after_id, max(1, min(limit, 500)))
        return [{"id": m.id, "type": m.payload.get("type"), "sessionId": m.payload.get("sessionId"), "createdAt": m.created_at, "data": m.payload.get("data", {}),
                 "delivered": m.delivered_at is not None} for m in items if m.kind.startswith(KIND)]


class EventingAudit:
    """Wraps the audit log: every entry is stored exactly as before, then the matching event (if any) is emitted."""

    def __init__(self, inner: Any, feed: EventFeed):
        self.inner, self.feed = inner, feed

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def append(self, entry: AuditEntry) -> AuditEntry:
        saved = await self.inner.append(entry)
        type_ = FROM_AUDIT.get(entry.action)
        if type_ is not None and entry.outcome == "success":
            await self.feed.emit(type_, {"action": entry.action, "target": entry.target, "actor": entry.actor, **scalars(entry.detail)})
        return saved


class EventWebhook(WebhookNotifier):
    """The signed webhook for events only. Replies and other messages are not its business."""

    def __init__(self, *a: Any, types: set[str] | None = None, **kw: Any):
        super().__init__(*a, **kw)
        self.types = set(types) if types else set(EVENTS)

    async def send_test(self, type_: str, now: float | None = None) -> dict[str, Any]:
        """One signed sample event, sent right now to the configured address, marked as a test. It is not stored, not retried and does not
        appear in the feed. Returns what happened (the receiver's status code and how long it took), never the receiver's answer."""
        import json
        import time
        import httpx
        from .notify import sign
        began = time.monotonic()
        ts = str(int(now if now is not None else time.time()))
        body = json.dumps({"id": 0, "type": type_, "createdAt": float(ts), "sessionId": None, "test": True,
                           "data": {"test": True, "note": "A sample event from NorthCX. Nothing happened.", "description": EVENTS.get(type_, "")}}, sort_keys=True).encode()
        try:
            r = await self._client.post(self.url, content=body, headers={"content-type": "application/json", "x-northcx-timestamp": ts, "x-northcx-signature": sign(self.secret, ts, body),
                                                                         "x-northcx-event": type_, "x-northcx-test": "1"})
            ok = r.status_code < 300
            return {"status": "sent" if ok else "failed", "httpStatus": r.status_code, "milliseconds": round((time.monotonic() - began) * 1000),
                    **({} if ok else {"error": f"The receiver answered {r.status_code}"})}
        except httpx.HTTPError as e:
            return {"status": "failed", "httpStatus": None, "milliseconds": round((time.monotonic() - began) * 1000), "error": f"Could not reach the receiver ({type(e).__name__})"}

    async def deliver(self, message: OutboxMessage) -> None:
        if not message.kind.startswith(KIND) or message.kind[len(KIND):] not in self.types:
            return
        import json
        import time
        from .notify import sign
        import asyncio
        import httpx
        body = json.dumps({"id": message.id, "type": message.payload.get("type"), "createdAt": message.created_at, "sessionId": message.payload.get("sessionId"),
                           "data": message.payload.get("data", {})}, sort_keys=True).encode()
        last: Exception | None = None
        for i in range(self.attempts):
            ts = str(int(time.time()))
            try:
                r = await self._client.post(self.url, content=body, headers={"content-type": "application/json", "x-northcx-timestamp": ts,
                                                                             "x-northcx-signature": sign(self.secret, ts, body), "x-northcx-event": str(message.payload.get("type"))})
                if r.status_code < 300:
                    return
                last = RuntimeError(f"webhook returned {r.status_code}")
            except httpx.HTTPError as e:
                last = e
            if i < self.attempts - 1:
                await asyncio.sleep(self.backoff * (2 ** i))
        raise RuntimeError(f"event delivery failed: {type(last).__name__ if last else 'unknown'}")
