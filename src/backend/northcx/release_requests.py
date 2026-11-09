"""The two-person rule for releases (WP3.5): in the environments an operator lists, publishing or promoting a version is a request that a
different person with the release permission must approve. Rolling back is never held up: an emergency must not wait for a second person.

The release gate (checklist and required scenarios) still decides whether the version may go live, and it is checked when the second
person approves, so what is approved is judged on the state at that moment."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class ApprovalError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class ReleaseRequest:
    id: str
    agent_id: str
    kind: str  # publish | promote
    environment: str
    version: int | None  # publish: the version; promote: None (whatever is live one step earlier)
    requested_by: str
    note: str | None = None
    status: str = "pending"  # pending | approved | rejected | cancelled | failed
    decided_by: str | None = None
    decision_note: str | None = None
    created_at: float = field(default_factory=time.time)
    decided_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "agent": self.agent_id, "kind": self.kind, "environment": self.environment, "version": self.version, "requestedBy": self.requested_by,
                "note": self.note, "status": self.status, "decidedBy": self.decided_by, "decisionNote": self.decision_note, "createdAt": self.created_at, "decidedAt": self.decided_at}


class RequestRepo(Protocol):
    async def add(self, r: ReleaseRequest) -> None: ...
    async def get(self, request_id: str) -> ReleaseRequest | None: ...
    async def list(self, status: str | None, agent_id: str | None, limit: int) -> list[ReleaseRequest]: ...
    async def decide(self, request_id: str, status: str, by: str, note: str | None) -> ReleaseRequest | None: ...  # only from pending; None if it was not pending
    async def mark(self, request_id: str, status: str, note: str | None) -> None: ...  # after approval: the release itself failed


class InMemoryRequests:
    def __init__(self) -> None:
        self._items: dict[str, ReleaseRequest] = {}

    async def add(self, r: ReleaseRequest) -> None:
        self._items[r.id] = r

    async def get(self, request_id: str) -> ReleaseRequest | None:
        return self._items.get(request_id)

    async def list(self, status: str | None, agent_id: str | None, limit: int) -> list[ReleaseRequest]:
        out = [r for r in self._items.values() if (status is None or r.status == status) and (agent_id is None or r.agent_id == agent_id)]
        return sorted(out, key=lambda r: r.created_at, reverse=True)[:limit]

    async def decide(self, request_id: str, status: str, by: str, note: str | None) -> ReleaseRequest | None:
        r = self._items.get(request_id)
        if r is None or r.status != "pending":
            return None
        r.status, r.decided_by, r.decision_note, r.decided_at = status, by, note, time.time()
        return r


    async def mark(self, request_id: str, status: str, note: str | None) -> None:
        r = self._items.get(request_id)
        if r is not None:
            r.status, r.decision_note = status, note


def principal(identity: Any) -> str:
    """Who a person is for the two-person rule: a single-sign-on session is the person's email (a new session is not a new person);
    any other key is itself. The bootstrap key is one principal, so give each approver their own key or sign in."""
    if identity.key_id and identity.name.startswith("sso: "):
        return identity.name
    return f"key:{identity.key_id}" if identity.key_id else "open"


class ReleaseApprovals:
    def __init__(self, required: set[str], repo: RequestRepo | None = None):
        self.required, self.repo = set(required), repo or InMemoryRequests()

    def needs_approval(self, environment: str) -> bool:
        return environment in self.required

    async def request(self, agent_id: str, kind: str, environment: str, version: int | None, by: str, note: str | None) -> ReleaseRequest:
        pending = await self.repo.list("pending", agent_id, 200)
        if any(p.environment == environment and p.kind == kind and p.version == version for p in pending):
            raise ApprovalError(409, "The same request is already waiting for a second person")
        r = ReleaseRequest(secrets.token_hex(6), agent_id, kind, environment, version, by, note)
        await self.repo.add(r)
        return r

    async def claim(self, request_id: str, approver: str, approve: bool, note: str | None) -> ReleaseRequest:
        """Record the decision, once. The approver must not be the requester."""
        r = await self.repo.get(request_id)
        if r is None:
            raise ApprovalError(404, "Unknown request")
        if r.status != "pending":
            raise ApprovalError(409, f"This request is already {r.status}")
        if approve and approver == r.requested_by:
            raise ApprovalError(403, "A release needs a second person: the person who asked cannot approve it")
        done = await self.repo.decide(request_id, "approved" if approve else "rejected", approver, note)
        if done is None:
            raise ApprovalError(409, "This request was decided by someone else just now")
        return done

    async def fail(self, request_id: str, reason: str) -> None:
        await self.repo.mark(request_id, "failed", reason[:900])

    async def cancel(self, request_id: str, by: str) -> ReleaseRequest:
        r = await self.repo.get(request_id)
        if r is None:
            raise ApprovalError(404, "Unknown request")
        if r.requested_by != by:
            raise ApprovalError(403, "Only the person who asked can withdraw the request (anyone with the release permission may reject it)")
        done = await self.repo.decide(request_id, "cancelled", by, None)
        if done is None:
            raise ApprovalError(409, f"This request is already {r.status}")
        return done
