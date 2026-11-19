"""Response bodies of the Agent API routes that are typed so far (the stability rule in docs/04-integrations/NorthCX_API-Design.md covers them).

The models describe a response in the API reference; they do not filter or validate what a route sends (extra fields pass through),
so adding a field to a route never needs a change here. A field listed here is always present; `None` is allowed where the route sends null.
tests/test_agent_api_responses.py checks the real responses against them.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Response(BaseModel):
    model_config = ConfigDict(extra="allow")


class PendingApproval(Response):
    id: str
    tool: str
    input: Any
    reason: str


class ChatResponse(Response):
    reply: str
    status: str
    traceId: str
    pendingApprovals: list[PendingApproval]
    handoffId: str | None
    agentVersion: int | None


class Approval(Response):
    """Field names here are snake_case, as the route has always sent them."""
    id: str
    trace_id: str
    session_id: str
    tool: str
    input: Any
    reason: str
    agent_id: str
    customer_id: str | None
    state: str
    created_at: float
    decided_by: str | None
    decided_at: float | None
    note: str | None
    result: Any


class ApprovalList(Response):
    approvals: list[Approval]


class ApprovalResume(Response):
    reply: str | None = None
    status: str | None = None
    traceId: str | None = None
    error: str | None = None


class ApprovalDecision(Approval):
    resume: ApprovalResume


class ApprovalExpiry(Response):
    expired: list[str]


class Handoff(Response):
    id: str
    sessionId: str
    traceId: str
    agentId: str
    customerId: str | None
    trigger: str
    reason: str | None
    topics: list[str]
    state: str
    createdAt: float
    resolvedBy: str | None
    resolvedAt: float | None
    note: str | None
    summary: str | None
    queue: str
    afterHours: bool


class HandoffDetail(Handoff):
    package: dict[str, Any]


class HandoffList(Response):
    handoffs: list[Handoff]


class HandoffInbox(Response):
    configured: bool
    deliveries: list[dict[str, Any]]


class HandoffReply(Response):
    sent: bool
    messageId: int


class TraceSummary(Response):
    id: str
    agentId: str
    sessionId: str
    events: int
    status: str
    startedAt: float | None
    tools: list[str]
    agentVersion: int | None
    environment: str


class TraceList(Response):
    traces: list[TraceSummary]


class TraceEvent(Response):
    t: float
    type: str
    data: dict[str, Any]


class Trace(Response):
    """The full record of one turn. Field names are snake_case, as the route has always sent them."""
    id: str
    agent_id: str
    session_id: str
    events: list[TraceEvent]
    agent_version: int | None
    environment: str


class TraceExports(Response):
    configured: bool
    deliveries: list[dict[str, Any]]


class OutboxMessage(Response):
    id: int
    kind: str
    createdAt: float


class Outbox(Response):
    messages: list[OutboxMessage]


class Attachments(Response):
    attachments: list[dict[str, Any]]


class SessionTags(Response):
    sessionId: str
    tags: list[str]


class TagAdded(SessionTags):
    tag: str
    added: bool


class TagRemoved(Response):
    removed: bool
    tags: list[str]


class Transcript(Response):
    sessionId: str
    transcript: list[dict[str, Any]]
    tags: list[str]
    traces: list[dict[str, Any]]
    handoffs: list[dict[str, Any]]
    rating: Any
    review: dict[str, Any] | None


class EventTypes(Response):
    enabled: bool
    types: list[dict[str, Any]]
