"""Response bodies of the Agent API routes that are typed so far (the stability rule in docs/04-integrations/NorthCX_API-Design.md covers them).

The models describe a response in the API reference; they do not filter or validate what a route sends (extra fields pass through),
so adding a field to a route never needs a change here. A field listed here is always present; `None` is allowed where the route sends null.
tests/test_agent_api_responses.py checks the real responses against them.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    choices: list[str] = []
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


class Attachment(Response):
    id: str
    name: str
    kind: str
    mediaType: str
    size: int
    sha256: str
    createdAt: float


class Attachments(Response):
    attachments: list[Attachment]


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


# ---- agents, versions and releases ----
class AgentSummary(Response):
    id: str
    version: int | None
    digest: str | None
    instructions: str
    model: str | None
    maxSteps: int
    tools: list[Any]
    guardrails: list[str]
    inputGuardrails: list[str]
    outputGuardrails: list[str]
    forcedTopics: list[str]


class AgentList(Response):
    agents: list[AgentSummary]


class Version(Response):
    id: str
    agentId: str
    number: int
    digest: str
    author: str
    note: str | None
    createdAt: float
    live: bool
    everReleased: bool


class VersionList(Response):
    versions: list[Version]


class VersionDetail(Version):
    spec: dict[str, Any]
    specYaml: str


class VersionPreview(Response):
    valid: bool
    problems: list[str]
    digest: str | None = None
    unchangedSinceLatest: bool | None = None
    diffFromLive: dict[str, Any] | None = None
    summary: list[str] = []  # what the agent will do, in plain sentences


class VersionDiff(Response):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    from_: int = Field(alias="from")  # `from` is a Python keyword
    to: int
    identical: bool


class ChecklistItem(Response):
    key: str
    title: str
    status: str
    detail: str


class Checklist(Response):
    agent: str
    version: int
    environment: str
    ready: bool
    checks: list[ChecklistItem]
    changes: dict[str, Any]
    liveVersion: int | None


class Release(Response):
    id: str
    agentId: str
    environment: str
    action: str
    version: int | None
    versionId: str | None
    previousVersion: int | None
    by: str
    note: str | None
    gate: dict[str, Any]
    createdAt: float
    toBaseline: bool


class ReleaseList(Response):
    releases: list[Release]


class Environments(Response):
    agentId: str
    strictPromotion: bool
    environments: dict[str, dict[str, Any]]


class LiveAgent(Response):
    agentId: str
    environment: str
    servedFrom: str
    source: str
    version: int | None
    digest: str | None
    release: Any
    spec: dict[str, Any]
    specYaml: str


class Rollout(Response):
    id: str
    agentId: str
    environment: str
    candidateVersion: int
    controlVersion: int | None
    percent: int
    state: str
    startedBy: str
    startedAt: float
    endedBy: str | None
    endedAt: float | None
    note: str | None


class RolloutList(Response):
    rollouts: list[Rollout]


class RolloutComparison(Response):
    rollout: Rollout
    arms: dict[str, dict[str, Any]]
    enoughData: bool
    note: str
    versions: dict[str, int | None]


# ---- simulations and conversation review ----
class ScenarioSummary(Response):
    name: str
    agent: str
    required: bool
    description: str
    steps: int
    tags: list[str]
    judge: bool
    digest: str
    source: str
    editable: bool


class ScenarioList(Response):
    modes: list[str]
    managedAvailable: bool
    scenarios: list[ScenarioSummary]


class ScenarioDetail(Response):
    name: str
    source: str
    editable: bool
    required: bool
    digest: str
    definition: dict[str, Any]
    yaml: str
    revision: int | None
    updatedBy: str | None
    updatedAt: float | None


class ScenarioCheck(Response):
    valid: bool
    problems: list[str]


class Gate(Response):
    agent: str
    agentDigest: str | None
    satisfied: bool
    required: int
    covered: int
    reasons: list[str]
    runIds: list[str]


class GateList(Response):
    gates: list[Gate]


class SimulationRun(Response):
    id: str
    createdAt: float
    mode: str
    source: str
    passed: bool
    counts: dict[str, int]
    seconds: float
    meta: dict[str, Any]
    agentDigests: dict[str, str]


class SimulationRunDetail(SimulationRun):
    results: list[dict[str, Any]]


class SimulationRunList(Response):
    runs: list[SimulationRun]


class ScenarioDraft(Response):
    yaml: str
    scenario: dict[str, Any]
    warnings: list[str]


class Saved(Response):
    saved: bool
    replaced: bool


# ---- routes that answer only when a service or a model is configured ----
class ScenarioSaved(Response):
    name: str
    revision: int
    digest: str
    required: bool


class ScenarioDeleted(Response):
    deleted: bool


class Qualification(Response):
    agent: str
    model: str
    agentDigest: str
    qualified: bool
    required: dict[str, int]
    other: dict[str, int]
    runId: str
    createdAt: float
    reasons: list[str]


class QualificationList(Response):
    qualifications: list[Qualification]


class StatusEvent(Response):
    id: int
    type: str | None
    sessionId: str | None
    createdAt: float
    data: dict[str, Any]
    delivered: bool


class EventFeed(Response):
    events: list[StatusEvent]


class EventTestResult(Response):
    type: str
    status: str


class HandoffAssist(Response):
    assist: dict[str, Any]


class AgentImprovement(Response):
    findings: dict[str, Any]
    proposal: dict[str, Any]
    tests: dict[str, Any]
    draftVersion: int | None
    note: str


class JourneyDraft(Response):
    journey: dict[str, Any]
    yaml: str
    warnings: list[str]
    note: str


class JourneyScenarios(Response):
    scenarios: list[dict[str, Any]]
    yaml: str
