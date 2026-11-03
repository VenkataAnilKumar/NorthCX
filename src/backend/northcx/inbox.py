"""Human inbox integration (H5): every hand-off is pushed to the company's helpdesk, and its resolution is passed on.

Two connectors: a signed webhook that any system can receive, and a Chatwoot adapter that talks to its REST API. Delivery
is queued in the database and retried with back-off, so a helpdesk outage delays a hand-off's appearance there but never
loses it and never blocks the customer's conversation.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .handoffs import Handoff
from .notify import sign

MAX_ATTEMPTS = 12


class InboxError(RuntimeError):
    """A delivery failed. The message is safe to store and show: it never contains URLs, tokens or response bodies."""


class InboxConnector(Protocol):
    name: str

    async def created(self, handoff: Handoff) -> str: ...  # returns the system's reference for this hand-off
    async def resolved(self, handoff: Handoff, ref: str | None) -> None: ...


def event_payload(event: str, h: Handoff, console_url: str | None) -> dict[str, Any]:
    return {"event": event, "handoff": {
        "id": h.id, "state": h.state, "queue": h.queue, "afterHours": h.after_hours, "trigger": h.trigger, "reason": h.reason, "topics": h.topics,
        "customerId": h.customer_id, "sessionId": h.session_id, "agentId": h.agent_id, "createdAt": h.created_at, "resolvedBy": h.resolved_by,
        "resolvedAt": h.resolved_at, "note": h.note, "summary": h.package.get("summary"), "package": h.package},
        "consoleUrl": f"{console_url.rstrip('/')}/handoffs?open={h.id}" if console_url else None}


def _fail(what: str, e: Exception | None = None, status: int | None = None) -> InboxError:
    detail = f"returned {status}" if status is not None else (type(e).__name__ if e else "failed")
    return InboxError(f"{what}: {detail}")


class WebhookInbox:
    name = "webhook"

    def __init__(self, url: str, secret: str, console_url: str | None = None, client: httpx.AsyncClient | None = None, timeout: float = 8.0):
        if not url.startswith(("https://", "http://")):
            raise ValueError("NORTHCX_INBOX_WEBHOOK_URL must start with https:// (or http:// for local testing)")
        if not secret:
            raise ValueError("NORTHCX_INBOX_WEBHOOK_URL needs NORTHCX_INBOX_WEBHOOK_SECRET")
        self.url, self.secret, self.console = url, secret, console_url
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def _post(self, event: str, h: Handoff) -> httpx.Response:
        body = json.dumps(event_payload(event, h, self.console), sort_keys=True, default=str).encode()
        ts = str(int(time.time()))
        try:
            r = await self._client.post(self.url, content=body, headers={
                "content-type": "application/json", "x-northcx-timestamp": ts, "x-northcx-signature": sign(self.secret, ts, body),
                "x-northcx-event": event, "x-northcx-delivery": f"{h.id}:{event}"})
        except httpx.HTTPError as e:
            raise _fail("inbox webhook", e) from e
        if r.status_code >= 300:
            raise _fail("inbox webhook", status=r.status_code)
        return r

    async def created(self, h: Handoff) -> str:
        r = await self._post("handoff.created", h)
        try:  # the receiver may answer {"ref": "..."} so later events can refer to its record
            ref = r.json().get("ref")
            return str(ref)[:200] if ref else h.id
        except ValueError:
            return h.id

    async def resolved(self, h: Handoff, ref: str | None) -> None:
        await self._post("handoff.resolved", h)


class ChatwootInbox:
    """Creates a conversation with a private note holding the summary, transcript and actions; closes it on resolution.
    Only Chatwoot's public REST API is used."""
    name = "chatwoot"

    def __init__(self, base_url: str, account_id: str, inbox_id: str, token: str, client: httpx.AsyncClient | None = None, timeout: float = 8.0):
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("NORTHCX_CHATWOOT_URL must start with https:// (or http:// for local testing)")
        if not (account_id.isdigit() and inbox_id.isdigit()):
            raise ValueError("NORTHCX_CHATWOOT_ACCOUNT_ID and NORTHCX_CHATWOOT_INBOX_ID must be numbers")
        if not token:
            raise ValueError("Chatwoot needs NORTHCX_CHATWOOT_TOKEN")
        self.base, self.account, self.inbox, self.token = base_url.rstrip("/"), account_id, inbox_id, token
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    def _url(self, path: str) -> str:
        return f"{self.base}/api/v1/accounts/{self.account}{path}"

    async def _call(self, method: str, path: str, what: str, **kw: Any) -> httpx.Response:
        try:
            return await self._client.request(method, self._url(path), headers={"api_access_token": self.token}, **kw)
        except httpx.HTTPError as e:
            raise _fail(f"chatwoot {what}", e) from e

    async def _contact(self, h: Handoff) -> tuple[int, str | None]:
        ident = h.customer_id
        r = await self._call("POST", "/contacts", "create contact", json={"inbox_id": int(self.inbox), "name": ident or "Website visitor", **({"identifier": ident} if ident else {})})
        if r.status_code == 422 and ident:  # already known: find them
            s = await self._call("GET", "/contacts/search", "find contact", params={"q": ident})
            if s.status_code == 200 and (s.json().get("payload") or []):
                c = s.json()["payload"][0]
                src = next((ci.get("source_id") for ci in c.get("contact_inboxes", []) if str(ci.get("inbox", {}).get("id")) == self.inbox), None)
                return int(c["id"]), src
            raise _fail("chatwoot find contact", status=s.status_code)
        if r.status_code >= 300:
            raise _fail("chatwoot create contact", status=r.status_code)
        payload = r.json().get("payload", {})
        c = payload.get("contact", payload)
        ci = payload.get("contact_inbox") or next((x for x in c.get("contact_inboxes", []) if str(x.get("inbox", {}).get("id")) == self.inbox), None)
        return int(c["id"]), (ci or {}).get("source_id")

    @staticmethod
    def note(h: Handoff) -> str:
        p = h.package
        lines = [f"NorthCX hand-off ({h.queue or 'general'}{', arrived after hours' if h.after_hours else ''})", "", p.get("summary", ""), "", "Conversation:"]
        lines += [f"- {m['from']}: {m['text']}" for m in p.get("transcript", [])[-30:]]
        if p.get("actions"):
            lines += ["", "Actions taken:"] + [f"- {a['tool']}: {a['outcome']}" for a in p["actions"]]
        if p.get("customerFacts"):
            lines += ["", "Customer facts:"] + [f"- {k}: {v}" for k, v in p["customerFacts"].items()]
        return "\n".join(lines)[:10000]

    async def created(self, h: Handoff) -> str:
        contact_id, source = await self._contact(h)
        body: dict[str, Any] = {"inbox_id": int(self.inbox), "contact_id": contact_id, "status": "open",
                                "additional_attributes": {"northcx_handoff_id": h.id, "northcx_queue": h.queue or ""}}
        if source:
            body["source_id"] = source
        r = await self._call("POST", "/conversations", "create conversation", json=body)
        if r.status_code >= 300:
            raise _fail("chatwoot create conversation", status=r.status_code)
        cid = str(r.json()["id"])
        m = await self._call("POST", f"/conversations/{cid}/messages", "add note", json={"content": self.note(h), "message_type": "outgoing", "private": True})
        if m.status_code >= 300:
            raise _fail("chatwoot add note", status=m.status_code)
        return cid

    async def resolved(self, h: Handoff, ref: str | None) -> None:
        if not ref or not ref.isdigit():
            return
        r = await self._call("POST", f"/conversations/{ref}/toggle_status", "close conversation", json={"status": "resolved"})
        if r.status_code >= 300:
            raise _fail("chatwoot close conversation", status=r.status_code)


@dataclass
class InboxEvent:
    handoff_id: str
    connector: str
    event: str  # created | resolved
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    last_attempt_at: float | None = None
    delivered_at: float | None = None
    external_ref: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"connector": self.connector, "event": self.event, "attempts": self.attempts, "delivered": self.delivered_at is not None,
                "deliveredAt": self.delivered_at, "lastAttemptAt": self.last_attempt_at, "reference": self.external_ref, "error": self.error}


class InboxRepo(Protocol):
    async def enqueue(self, events: list[InboxEvent]) -> None: ...
    async def pending(self, limit: int = 100) -> list[InboxEvent]: ...
    async def record(self, event_id: str, delivered: bool, ref: str | None, error: str | None, at: float) -> None: ...
    async def for_handoff(self, handoff_id: str) -> list[InboxEvent]: ...
    async def erase_handoffs(self, handoff_ids: list[str]) -> int: ...


class InMemoryInbox:
    def __init__(self) -> None:
        self.events: list[InboxEvent] = []

    async def enqueue(self, events) -> None:
        self.events.extend(events)

    async def pending(self, limit=100) -> list[InboxEvent]:
        return [e for e in sorted(self.events, key=lambda e: e.created_at) if e.delivered_at is None and e.attempts < MAX_ATTEMPTS][:limit]

    async def record(self, event_id, delivered, ref, error, at) -> None:
        for e in self.events:
            if e.id == event_id:
                e.attempts += 1
                e.last_attempt_at, e.error = at, None if delivered else error
                if delivered:
                    e.delivered_at, e.external_ref = at, ref
                return

    async def for_handoff(self, handoff_id) -> list[InboxEvent]:
        return sorted((e for e in self.events if e.handoff_id == handoff_id), key=lambda e: e.created_at)

    async def erase_handoffs(self, handoff_ids) -> int:
        n = len(self.events)
        self.events = [e for e in self.events if e.handoff_id not in set(handoff_ids)]
        return n - len(self.events)


class InboxDispatcher:
    def __init__(self, repo: InboxRepo, connectors: list[InboxConnector]):
        self.repo, self.connectors = repo, {c.name: c for c in connectors}

    async def enqueue(self, handoff: Handoff, event: str) -> None:
        await self.repo.enqueue([InboxEvent(handoff.id, name, event) for name in self.connectors])

    @staticmethod
    def due(e: InboxEvent, now: float) -> bool:
        if e.attempts == 0 or e.last_attempt_at is None:
            return True
        return now >= e.last_attempt_at + min(30 * 2 ** max(e.attempts - 1, 0), 3600)

    async def flush(self, handoffs: Any, now: float | None = None) -> int:
        """Deliver what is due, oldest first. A 'resolved' event waits until its 'created' event has been delivered."""
        now = time.time() if now is None else now
        sent, blocked = 0, set()
        for e in await self.repo.pending():
            conn = self.connectors.get(e.connector)
            if conn is None or not self.due(e, now) or (e.connector, e.handoff_id) in blocked:
                if conn is not None and e.event == "created":
                    blocked.add((e.connector, e.handoff_id))
                continue
            h = await handoffs.get(e.handoff_id)
            if h is None:  # erased since it was queued
                await self.repo.record(e.id, True, None, None, now)
                continue
            ref = next((x.external_ref for x in await self.repo.for_handoff(e.handoff_id) if x.connector == e.connector and x.event == "created" and x.delivered_at), None)
            if e.event == "resolved" and ref is None and any(x.connector == e.connector and x.event == "created" and x.delivered_at is None for x in await self.repo.for_handoff(e.handoff_id)):
                continue
            try:
                if e.event == "created":
                    ref = await conn.created(h)
                else:
                    await conn.resolved(h, ref)
                await self.repo.record(e.id, True, ref if e.event == "created" else None, None, now)
                sent += 1
            except Exception as ex:
                await self.repo.record(e.id, False, None, str(ex)[:300] if isinstance(ex, InboxError) else type(ex).__name__, now)
                if e.event == "created":
                    blocked.add((e.connector, e.handoff_id))
        return sent
