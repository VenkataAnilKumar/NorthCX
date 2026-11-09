from __future__ import annotations

from typing import Any

import logging
import re
import secrets

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from fastapi.middleware.cors import CORSMiddleware

from .access import AccessControl, OPEN_IDENTITY
from .channels.email import EmailChannel
from .tokens import TokenSigner, derive_secret
from .approval_flow import ApprovalFlow
from .channels.sms import SmsChannel
from .channels.telegram import TelegramChannel
from .channels.whatsapp import WhatsAppChannel
from .templates import Template
from .alerts import AlertManager
from .sso import Sso
from .rollout import RolloutService
from .reviews import InMemoryReviews, ReviewRepo
from .events import EventFeed, EventingAudit
from .crawler import Crawler
from .crawl_schedule import CrawlScheduler
from .hardening import BodyLimit, SecurityHeaders
from .voice import CallRepo, InMemoryCalls, VoiceConfig
from .attachments import AttachmentRepo, InMemoryAttachments, Scanner
from .transcribe import HttpTranscriber
from .insights import InMemoryTags, TagRepo, FeedbackRepo, InMemoryFeedback, InMemoryInsightsSource, InsightsService
from .regression import RegressionRunner
from .privacy import InMemoryPrivacy, PrivacyService
from .knowledge import InMemoryKnowledge, KnowledgeStore
from .idempotency import IdempotencyStore, InMemoryIdempotency
from .audit import AuditEntry, AuditRepo, InMemoryAudit
from .agent import Agent
from .catalog import as_provider
from .runtime import Runtime
from .simulation import SimulationService
from .versions import ReleaseService
from .trace import TraceRepo
from .api.common import _err, _pieces  # noqa: F401  (re-exported: a test imports it from here)
from .api.deps import AppDeps
from .api.routers import templates as _templates_router
from .api.routers import memory as _memory_router
from .api.routers import privacy as _privacy_router
from .api.routers import tokens as _tokens_router
from .api.routers import sso as _sso_router
from .api.routers import email as _email_router
from .api.routers import sms as _sms_router
from .api.routers import whatsapp as _whatsapp_router
from .api.routers import telegram as _telegram_router
from .api.routers import identity as _identity_router
from .api.routers import insights as _insights_router
from .api.routers import observability as _observability_router
from .api.routers import builder as _builder_router
from .api.routers import simulations as _simulations_router
from .api.routers import knowledge as _knowledge_router
from .api.routers import approvals as _approvals_router
from .api.routers import handoffs as _handoffs_router
from .api.routers import rollouts as _rollouts_router
from .api.routers import groups as _groups_router
from .api.routers import scim as _scim_router
from .api.routers import workspace as _workspace_router
from .api.routers import hub as _hub_router
from .api.routers import org_policies as _org_policies_router
from .api.routers import org_templates as _org_templates_router
from .api.routers import quality as _quality_router
from .api.routers import customers as _customers_router
from .api.routers import automations as _automations_router
from .api.routers import workspace_content as _workspace_content_router
from .api.routers import admin_overview as _admin_overview_router
from .tenancy import TENANT
from .api.routers import voice as _voice_router
from .api.routers import public as _public_router
from .api.routers import chat as _chat_router
from .api.routers import releases as _releases_router
from .api.background import start_background
from .api.helpers import actor, make_guards, rel_error, too_many, version_json


# Every /v1 route must appear here. A route that is not listed is refused (a test checks the table against the app).
ROUTE_PERMISSIONS: list[tuple[str, str, str]] = [
    ("GET", r"/v1/me", "authenticated"),
    ("POST", r"/v1/me/logout", "authenticated"),
    ("POST", r"/v1/chat-tokens", "chat:mint"),
    ("POST", r"/v1/channels/email/inbound", "channel:inbound"),
    ("POST", r"/v1/agents/[^/]+/chat", "chat:send"),
    ("POST", r"/v1/agents/[^/]+/chat/stream", "chat:send"),
    ("GET", r"/v1/sessions/[^/]+/outbox", "outbox:read"),
    ("GET", r"/v1/memories", "memory:read"),
    ("DELETE", r"/v1/memories", "memory:manage"),
    ("DELETE", r"/v1/memories/[^/]+", "memory:manage"),
    ("GET", r"/v1/privacy/customers/.+/export", "privacy:manage"),
    ("DELETE", r"/v1/privacy/customers/.+", "privacy:manage"),
    ("DELETE", r"/v1/privacy/sessions/.+", "privacy:manage"),
    ("POST", r"/v1/privacy/retention/run", "privacy:manage"),
    ("GET", r"/v1/knowledge/sources", "knowledge:read"),
    ("POST", r"/v1/knowledge/sources", "knowledge:write"),
    ("DELETE", r"/v1/knowledge/sources/[^/]+", "knowledge:write"),
    ("PUT", r"/v1/knowledge/sources/[^/]+/documents/.+", "knowledge:write"),
    ("DELETE", r"/v1/knowledge/sources/[^/]+/documents/.+", "knowledge:write"),
    ("GET", r"/v1/knowledge/documents", "knowledge:read"),
    ("GET", r"/v1/knowledge/sources/[^/]+/documents/.+", "knowledge:read"),
    ("GET", r"/v1/knowledge/search", "knowledge:read"),
    ("GET", r"/v1/knowledge/index", "knowledge:read"),
    ("POST", r"/v1/knowledge/index/rebuild", "knowledge:write"),
    ("POST", r"/v1/knowledge/sources/[^/]+/crawl", "knowledge:write"),
    ("POST", r"/v1/knowledge/sources/[^/]+/import", "knowledge:write"),
    ("GET", r"/v1/knowledge/schedules", "knowledge:read"),
    ("POST", r"/v1/knowledge/sources/[^/]+/schedule", "knowledge:write"),
    ("DELETE", r"/v1/knowledge/schedules/[^/]+", "knowledge:write"),
    ("POST", r"/v1/knowledge/schedules/[^/]+/enabled", "knowledge:write"),
    ("GET", r"/v1/knowledge/crawls", "knowledge:read"),
    ("GET", r"/v1/knowledge/crawls/[^/]+", "knowledge:read"),
    ("POST", r"/v1/alerts/test", "keys:manage"),
    ("GET", r"/v1/monitor/findings", "monitor:read"),
    ("GET", r"/v1/monitor/summary", "monitor:read"),
    ("GET", r"/v1/reviews/queue", "traces:read"),
    ("GET", r"/v1/sessions/[^/]+/transcript", "traces:read"),
    ("PUT", r"/v1/sessions/[^/]+/review", "reviews:write"),
    ("GET", r"/v1/insights/review-quality", "insights:read"),
    ("GET", r"/v1/conversations/search", "traces:read"),
    ("GET", r"/v1/sessions/[^/]+/tags", "traces:read"),
    ("PUT", r"/v1/sessions/[^/]+/tags/[^/]+", "conversations:tag"),
    ("DELETE", r"/v1/sessions/[^/]+/tags/[^/]+", "conversations:tag"),
    ("GET", r"/v1/alerts", "insights:read"),
    ("GET", r"/v1/insights/overview", "insights:read"),
    ("POST", r"/v1/insights/ask", "insights:read"),
    ("GET", r"/v1/insights/timeseries", "insights:read"),
    ("GET", r"/v1/insights/failures", "insights:read"),
    ("GET", r"/v1/insights/gaps", "insights:read"),
    ("POST", r"/v1/sessions/[^/]+/feedback", "feedback:send"),
    ("GET", r"/v1/regression", "simulations:read"),
    ("GET", r"/v1/sessions/.+/scenario-draft", "simulations:run"),
    ("GET", r"/v1/voice/calls", "traces:read"),
    ("PUT", r"/v1/sessions/[^/]+/attachments", "chat:send"),
    ("GET", r"/v1/sessions/[^/]+/attachments", "traces:read"),
    ("GET", r"/v1/attachments/[^/]+", "traces:read"),
    ("POST", r"/v1/agents/[^/]+/journeys/draft", "versions:create"),
    ("POST", r"/v1/builder/draft", "versions:create"),
    ("POST", r"/v1/builder/scenarios", "versions:create"),
    ("POST", r"/v1/builder/refine", "versions:create"),
    ("POST", r"/v1/builder/transcribe", "versions:create"),
    ("GET", r"/v1/residency", "audit:read"),
    ("GET", r"/v1/events", "audit:read"),
    ("GET", r"/v1/events/types", "audit:read"),
    ("POST", r"/v1/events/test", "keys:manage"),
    ("POST", r"/v1/channels/whatsapp/templates/send", "channel:inbound"),
    ("POST", r"/v1/agents/[^/]+/journeys/scenarios", "simulations:run"),
    ("GET", r"/v1/trace-export", "traces:read"),
    ("GET", r"/v1/traces/[^/]+/exports", "traces:read"),
    ("GET", r"/v1/traces", "traces:read"),
    ("GET", r"/v1/traces/[^/]+", "traces:read"),
    ("GET", r"/v1/catalog", "agents:read"),
    ("POST", r"/v1/agents/[^/]+/versions/preview", "versions:create"),
    ("GET", r"/v1/templates", "agents:read"),
    ("GET", r"/v1/models/overview", "versions:read"),
    ("GET", r"/v1/usage", "insights:read"),
    ("PUT", r"/v1/budgets", "keys:manage"),
    ("DELETE", r"/v1/budgets", "keys:manage"),
    ("GET", r"/v1/policies", "agents:read"),
    ("GET", r"/v1/org-templates", "agents:read"),
    ("GET", r"/v1/org-templates/[^/]+", "agents:read"),
    ("POST", r"/v1/org-templates", "versions:create"),
    ("POST", r"/v1/org-templates/check", "versions:create"),
    ("PUT", r"/v1/org-templates/[^/]+", "versions:create"),
    ("POST", r"/v1/org-templates/[^/]+/propose", "versions:create"),
    ("POST", r"/v1/org-templates/[^/]+/(approve|reject|withdraw)", "releases:publish"),
    ("GET", r"/v1/org-policies", "agents:read"),
    ("POST", r"/v1/org-policies", "versions:create"),
    ("POST", r"/v1/org-policies/prove", "versions:create"),
    ("PUT", r"/v1/org-policies/[^/]+", "versions:create"),
    ("POST", r"/v1/org-policies/[^/]+/propose", "versions:create"),
    ("POST", r"/v1/org-policies/[^/]+/(approve|reject|retire)", "releases:publish"),
    ("POST", r"/v1/templates/[^/]+/requirements", "agents:read"),
    ("POST", r"/v1/templates/[^/]+/install", "versions:create"),
    ("POST", r"/v1/templates/[^/]+/update-preview", "versions:create"),
    ("POST", r"/v1/templates/[^/]+/update", "versions:create"),
    ("GET", r"/v1/hub/installs", "agents:read"),
    ("GET", r"/v1/templates/[^/]+", "agents:read"),
    ("POST", r"/v1/templates/[^/]+/render", "versions:create"),
    ("POST", r"/v1/templates/[^/]+/create-version", "versions:create"),
    ("GET", r"/v1/skills", "agents:read"),
    ("GET", r"/v1/agents", "agents:read"),
    ("GET", r"/v1/agents/[^/]+/live", "agents:read"),
    ("GET", r"/v1/agents/[^/]+/versions", "versions:read"),
    ("GET", r"/v1/agents/[^/]+/versions/[^/]+", "versions:read"),
    ("GET", r"/v1/agents/[^/]+/versions/[^/]+/diff/[^/]+", "versions:read"),
    ("GET", r"/v1/agents/[^/]+/versions/[^/]+/checklist", "versions:read"),
    ("GET", r"/v1/release-requests", "versions:read"),
    ("POST", r"/v1/release-requests/[^/]+/approve", "releases:publish"),
    ("POST", r"/v1/release-requests/[^/]+/reject", "releases:publish"),
    ("POST", r"/v1/release-requests/[^/]+/cancel", "versions:create"),
    ("GET", r"/v1/agents/[^/]+/rollouts", "versions:read"),
    ("GET", r"/v1/agents/[^/]+/rollouts/[^/]+/comparison", "insights:read"),
    ("POST", r"/v1/agents/[^/]+/rollouts", "versions:create"),  # production also needs releases:publish, checked in the handler
    ("PUT", r"/v1/agents/[^/]+/rollouts/[^/]+/percent", "versions:create"),
    ("POST", r"/v1/agents/[^/]+/rollouts/[^/]+/promote", "versions:create"),  # production also needs releases:publish
    ("POST", r"/v1/agents/[^/]+/rollouts/[^/]+/abort", "versions:create"),  # production also needs releases:rollback
    ("GET", r"/v1/agents/[^/]+/releases", "versions:read"),
    ("POST", r"/v1/agents/[^/]+/versions", "versions:create"),
    ("POST", r"/v1/agents/[^/]+/releases", "versions:create"),  # production also needs releases:publish, checked in the handler
    ("POST", r"/v1/agents/[^/]+/rollback", "versions:create"),  # production also needs releases:rollback
    ("POST", r"/v1/agents/[^/]+/promote", "versions:create"),
    ("GET", r"/v1/agents/[^/]+/environments", "versions:read"),
    ("GET", r"/v1/approvals", "approvals:read"),
    ("POST", r"/v1/approvals/expire", "approvals:decide"),
    ("POST", r"/v1/approvals/[^/]+/decision", "approvals:decide"),
    ("GET", r"/v1/routing", "handoffs:read"),
    ("GET", r"/v1/handoffs", "handoffs:read"),
    ("GET", r"/v1/handoffs/[^/]+/inbox", "handoffs:read"),
    ("GET", r"/v1/handoffs/[^/]+", "handoffs:read"),
    ("POST", r"/v1/handoffs/[^/]+/resolve", "handoffs:resolve"),
    ("POST", r"/v1/handoffs/[^/]+/reply", "handoffs:resolve"),
    ("POST", r"/v1/handoffs/[^/]+/assist", "handoffs:resolve"),
    ("GET", r"/v1/simulations/(scenarios|runs|gate)", "simulations:read"),
    ("GET", r"/v1/simulations/scenarios/[^/]+", "simulations:read"),
    ("POST", r"/v1/simulations/scenarios", "scenarios:write"),
    ("POST", r"/v1/simulations/scenarios/validate", "scenarios:write"),
    ("PUT", r"/v1/simulations/scenarios/[^/]+", "scenarios:write"),
    ("DELETE", r"/v1/simulations/scenarios/[^/]+", "scenarios:write"),
    ("GET", r"/v1/simulations/runs/[^/]+", "simulations:read"),
    ("GET", r"/v1/groups", "keys:manage"),
    ("POST", r"/v1/groups", "keys:manage"),
    ("PUT", r"/v1/groups/[^/]+", "keys:manage"),
    ("DELETE", r"/v1/groups/[^/]+", "keys:manage"),
    ("POST", r"/v1/groups/[^/]+/members", "keys:manage"),
    ("DELETE", r"/v1/groups/[^/]+/members/[^/]+", "keys:manage"),
    ("POST", r"/v1/workspace/chat", "workspace:use"),
    ("GET", r"/v1/workspace/outputs", "workspace:use"),
    ("POST", r"/v1/workspace/outputs", "workspace:use"),
    ("GET", r"/v1/workspace/outputs/[^/]+", "workspace:use"),
    ("PUT", r"/v1/workspace/outputs/[^/]+", "workspace:use"),
    ("DELETE", r"/v1/workspace/outputs/[^/]+", "workspace:use"),
    ("GET", r"/v1/workspace/outputs/[^/]+/export", "workspace:use"),
    ("GET", r"/v1/workspace/spaces", "workspace:use"),
    ("POST", r"/v1/workspace/spaces", "workspace:use"),
    ("GET", r"/v1/workspace/spaces/[^/]+", "workspace:use"),
    ("PUT", r"/v1/workspace/spaces/[^/]+", "workspace:use"),
    ("DELETE", r"/v1/workspace/spaces/[^/]+", "workspace:use"),
    ("GET", r"/v1/tenant/limits", "agents:read"),
    ("GET", r"/v1/automations", "agents:read"),
    ("POST", r"/v1/automations", "versions:create"),
    ("GET", r"/v1/automations/[^/]+", "agents:read"),
    ("PUT", r"/v1/automations/[^/]+", "versions:create"),
    ("POST", r"/v1/automations/[^/]+/propose", "versions:create"),
    ("POST", r"/v1/automations/[^/]+/(approve|reject|retire|pause|resume|secret)", "releases:publish"),
    ("POST", r"/v1/automations/[^/]+/(run|hook)", "automations:run"),
    ("GET", r"/v1/automations/[^/]+/runs", "agents:read"),
    ("GET", r"/v1/automation-runs/[^/]+", "agents:read"),
    ("GET", r"/v1/automation-settings", "agents:read"),
    ("PUT", r"/v1/automation-settings", "keys:manage"),
    ("GET", r"/v1/customers/settings", "customers:read"),
    ("PUT", r"/v1/customers/settings", "keys:manage"),
    ("POST", r"/v1/customers/lookup", "customers:read"),
    ("POST", r"/v1/customers/find", "customers:read"),
    ("POST", r"/v1/customers/reveal", "customers:read"),
    ("POST", r"/v1/customers/notes", "customers:write"),
    ("POST", r"/v1/customers/notes/[^/]+/delete", "customers:write"),
    ("POST", r"/v1/customers/facts/[^/]+/remove", "customers:write"),
    ("GET", r"/v1/quality/rubric", "traces:read"),
    ("PUT", r"/v1/quality/rubric", "releases:publish"),
    ("DELETE", r"/v1/quality/rubric", "releases:publish"),
    ("GET", r"/v1/quality/scorecards", "traces:read"),
    ("GET", r"/v1/quality/calibration", "traces:read"),
    ("POST", r"/v1/quality/judge", "reviews:write"),
    ("GET", r"/v1/quality/coaching", "reviews:write"),
    ("POST", r"/v1/quality/coaching", "reviews:write"),
    ("DELETE", r"/v1/quality/coaching/[^/]+", "reviews:write"),
    ("GET", r"/v1/workspace/assistants", "workspace:use"),
    ("GET", r"/v1/workspace/performance", "workspace:use"),
    ("POST", r"/v1/workspace/assistants/[^/]+/chat", "workspace:use"),
    ("POST", r"/v1/workspace/chat/stream", "workspace:use"),
    ("GET", r"/v1/workspace/search", "workspace:use"),
    ("GET", r"/v1/workspace/memory", "workspace:use"),
    ("POST", r"/v1/workspace/memory", "workspace:use"),
    ("DELETE", r"/v1/workspace/memory", "workspace:use"),
    ("PUT", r"/v1/workspace/memory/[^/]+", "workspace:use"),
    ("DELETE", r"/v1/workspace/memory/[^/]+", "workspace:use"),
    ("GET", r"/v1/workspace/tasks", "workspace:use"),
    ("POST", r"/v1/workspace/tasks", "workspace:use"),
    ("GET", r"/v1/workspace/tasks/[^/]+", "workspace:use"),
    ("DELETE", r"/v1/workspace/tasks/[^/]+", "workspace:use"),
    ("POST", r"/v1/workspace/tasks/[^/]+/(answers|approve|pause|stop)", "workspace:use"),
    ("PUT", r"/v1/workspace/tasks/[^/]+/plan", "workspace:use"),
    ("POST", r"/v1/simulations/runs", "simulations:run"),
    ("GET", r"/v1/agents/[^/]+/qualifications", "versions:read"),
    ("POST", r"/v1/agents/[^/]+/qualifications", "scenarios:require"),  # what may serve customers is a release decision
    ("GET", r"/v1/keys", "keys:manage"),
    ("POST", r"/v1/keys", "keys:manage"),
    ("POST", r"/v1/keys/[^/]+/revoke", "keys:manage"),
    ("GET", r"/v1/audit", "audit:read"),
    ("GET", r"/v1/audit/verify", "audit:read"),
]
PUBLIC_ROUTES = {("GET", "/"), ("GET", "/health"), ("GET", "/ready")}
_COMPILED = [(m, re.compile(p), perm) for m, p, perm in ROUTE_PERMISSIONS]
log = logging.getLogger("northcx.server")


_AGENT_PATH = re.compile(r"^/v1/agents/([^/]+)(?:/|$)")
_SCOPE_OK = {("GET", "/v1/me"), ("GET", "/v1/agents"), ("POST", "/v1/me/logout")}  # a limited key may always say who it is and list what it can reach


def scope_refusal(ident: Any, method: str, path: str, environment: str | None) -> str | None:
    """Why a key limited to some agents or environments may not make this request (None: it may). A limited key reaches only routes
    that name an agent in their path, and only its own agents; every other route is refused, because it could show or change another agent's data."""
    if environment is not None and not ident.allows_env(environment):
        return f"This key is limited to the {', '.join(ident.scope_envs)} environment(s)"
    if ident.scope_agents is None:
        return None
    if (method, path) in _SCOPE_OK:
        return None
    m = _AGENT_PATH.match(path)
    if m is None:
        return f"This key is limited to agents {', '.join(ident.scope_agents)}; this endpoint is not tied to one agent"
    if not ident.allows_agent(m.group(1)):
        return f"This key is limited to agents {', '.join(ident.scope_agents)}"
    return None


def permission_for(method: str, path: str) -> str | None:
    return next((perm for m, rx, perm in _COMPILED if m == method and rx.fullmatch(path)), None)


def create_app(runtime: Runtime, traces: TraceRepo, agents: dict[str, Agent], api_key: str | None = None,
               approval_ttl_seconds: float | None = None, simulations: SimulationService | None = None,
               releases: ReleaseService | None = None, access: AccessControl | None = None,
               audit: AuditRepo | None = None, email: EmailChannel | None = None,
               idempotency: IdempotencyStore | None = None, knowledge: KnowledgeStore | None = None,
               retention_days: float | None = None, sms: SmsChannel | None = None, regression: RegressionRunner | None = None, whatsapp: WhatsAppChannel | None = None, telegram: TelegramChannel | None = None, residency: dict | None = None, crawl_scheduler: CrawlScheduler | None = None, transcriber: HttpTranscriber | None = None, events: EventFeed | None = None,
               skills: list[Any] | None = None, templates: dict[str, Template] | None = None,
               insights: InsightsService | None = None, feedback: FeedbackRepo | None = None,
               alerts: AlertManager | None = None, tags: TagRepo | None = None, reviews: ReviewRepo | None = None, rollouts: RolloutService | None = None, sso: Sso | None = None,
               attachments: AttachmentRepo | None = None, attachment_scanner: Scanner | None = None, cors_origins: list[str] | None = None,
               voice: VoiceConfig | None = None, calls: CallRepo | None = None, crawler: Crawler | None = None,
               role: str = "all", leases: Any = None) -> FastAPI:
    if access is None:  # `api_key` is the single bootstrap admin key; with neither, the server is open (development)
        access = AccessControl(bootstrap_key=api_key)
    if access.signer is None:  # chat tokens need a signing secret: derive it from the bootstrap key, else use a random one
        secret = derive_secret(None, api_key) or secrets.token_bytes(32)
        access.signer = TokenSigner(secret)
    audit = audit or InMemoryAudit()
    if events is not None:
        runtime.events = events
        audit = EventingAudit(audit, events)  # staff actions become events as they are recorded
    idem = idempotency or InMemoryIdempotency()
    kb = knowledge or InMemoryKnowledge()
    if crawler is not None and crawler.on_change is None and regression is not None:
        crawler.on_change = regression.trigger  # a crawl that changed knowledge re-runs the knowledge-tagged scenarios, like any other change
    fb = feedback or InMemoryFeedback()
    tag_repo = tags or InMemoryTags()
    review_repo = reviews or InMemoryReviews()
    attachment_repo = attachments or InMemoryAttachments()
    runtime.privacy.attachments = attachment_repo
    if runtime.verification is not None:
        runtime.privacy.verification = runtime.verification.repo
    call_repo = calls or InMemoryCalls()
    runtime.privacy.calls = call_repo
    insight = insights or InsightsService(InMemoryInsightsSource(runtime, fb))
    privacy = PrivacyService(runtime.privacy)
    if isinstance(runtime.privacy, InMemoryPrivacy):
        runtime.privacy.feedback = fb
        runtime.privacy.tags = tag_repo
        runtime.privacy.reviews = review_repo
        if rollouts is not None:
            runtime.privacy.rollouts = rollouts.repo
    if isinstance(runtime.privacy, InMemoryPrivacy):  # the in-memory backend reaches the other in-memory stores through these
        runtime.privacy.idempotency = idem
        if email is not None:
            runtime.privacy.email = email.repo
        if sms is not None or whatsapp is not None or telegram is not None:
            runtime.privacy.sms = (sms or whatsapp or telegram).repo
    provider = as_provider(agents)
    if runtime.agent_resolver is None:
        runtime.agent_resolver = provider.get  # lets agents pass a conversation to a specialist
    agents = provider  # everything below resolves agents through the provider
    flow = ApprovalFlow(runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop = start_background(role, leases, tenants=access.tenants, runtime=runtime, traces=traces, flow=flow, agents=agents, approval_ttl_seconds=approval_ttl_seconds,
                                alerts=alerts, privacy=privacy, audit=audit, retention_days=retention_days, kb=kb, crawl_scheduler=crawl_scheduler, automations=getattr(runtime, "automations", None))
        yield
        await stop()

    # The interactive API docs are off: they would describe the API to anyone who can reach the server.
    app = FastAPI(title="NorthCX", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.rollouts = rollouts
    limits = access.limits
    record, need_rel, need_env = make_guards(audit, releases)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        method, path = request.method, request.url.path
        if (method, path) in PUBLIC_ROUTES or not path.startswith("/v1/"):
            return await call_next(request)
        perm = permission_for(method, path)
        if perm is None:  # an unlisted route is refused, never served
            return _err(404, "not_found", "No such endpoint")
        ip = request.client.host if request.client else "unknown"
        if await access.enabled():
            header = request.headers.get("authorization", "")
            ident, why = await access.authenticate_detail(header[7:] if header.startswith("Bearer ") else None)
            if ident is None:
                if limits and not (await access.limiter.hit(f"authfail:{ip}", limits.auth_failures_per_minute))[0]:
                    return too_many(60, "failed sign-in attempts")
                if (await access.limiter.hit(f"authlog:{ip}", 6))[0]:  # sampled, so guessing cannot flood the log
                    await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target=path,
                                                  outcome="denied", detail={"client": ip}))
                if why == "expired":
                    return _err(401, "token_expired", "This chat session has expired; ask the site for a new one")
                return _err(401, "unauthorized", "Missing or invalid API key")
        else:
            ident = OPEN_IDENTITY
        request.state.identity = ident
        TENANT.set(ident.tenant)  # everything this request writes (audit entries, keys) belongs to the key's tenant
        if limits:
            ok, retry = await access.limiter.hit(f"key:{ident.key_id or ip}", limits.channel_per_minute if ident.role == "channel" else limits.per_key_per_minute)
            if ok and getattr(runtime, "tenant_limits", None) is not None:
                ceiling = await runtime.tenant_limits.value(ident.tenant, "requestsPerMinute")      # all of one tenant's keys together
                if ceiling:
                    ok, retry = await access.limiter.hit(f"tenant:{ident.tenant}", ceiling)
            if not ok:
                return too_many(retry, "requests")
        if ident.scope_agents is not None or ident.scope_envs is not None:
            if (limit := scope_refusal(ident, method, path, request.query_params.get("environment"))) is not None:
                await record(request, "auth.denied", f"{method} {path}", "denied", scope=limit)
                return _err(403, "forbidden", limit)
        if perm != "authenticated" and not ident.can(perm):
            await record(request, "auth.denied", f"{method} {path}", "denied", permission=perm)
            return _err(403, "forbidden", f"The '{ident.role}' role cannot do this (needs {perm})")
        return await call_next(request)

    app.add_middleware(SecurityHeaders)
    app.add_middleware(BodyLimit)  # outside the key check, so an oversized body is refused before anything reads it
    if cors_origins:  # websites allowed to call the chat API from a browser (the SDK); added last so it answers preflight requests before the key check
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_credentials=False, max_age=600,
                           allow_headers=["authorization", "content-type", "idempotency-key"], expose_headers=["retry-after", "idempotent-replay"])

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return _err(400, "bad_request", str(exc.errors()))


    MAX_EMAIL_BYTES = 1_000_000


    SSO_COOKIE = "northcx_sso"
    secure_cookie = bool(sso and sso.cfg.redirect_uri.startswith("https://"))


    # [routers] generated by the WP0.1 split; one module per area of routes under northcx/api/routers
    deps = AppDeps(MAX_EMAIL_BYTES=MAX_EMAIL_BYTES, SSO_COOKIE=SSO_COOKIE, access=access, actor=actor, agents=agents, alerts=alerts, attachment_repo=attachment_repo, attachment_scanner=attachment_scanner, audit=audit, call_repo=call_repo, crawl_scheduler=crawl_scheduler, crawler=crawler, email=email, events=events, fb=fb, flow=flow, idem=idem, insight=insight, kb=kb, limits=limits, need_env=need_env, need_rel=need_rel, privacy=privacy, provider=provider, record=record, regression=regression, rel_error=rel_error, releases=releases, residency=residency, review_repo=review_repo, rollouts=rollouts, runtime=runtime, secure_cookie=secure_cookie, simulations=simulations, skills=skills, sms=sms, sso=sso, tag_repo=tag_repo, telegram=telegram, templates=templates, too_many=too_many, traces=traces, transcriber=transcriber, version_json=version_json, voice=voice, whatsapp=whatsapp)
    _templates_router.register(app, deps)
    _memory_router.register(app, deps)
    _privacy_router.register(app, deps)
    _tokens_router.register(app, deps)
    _sso_router.register(app, deps)
    _email_router.register(app, deps)
    _sms_router.register(app, deps)
    _whatsapp_router.register(app, deps)
    _telegram_router.register(app, deps)
    _identity_router.register(app, deps)
    _insights_router.register(app, deps)
    _observability_router.register(app, deps)
    _builder_router.register(app, deps)
    _simulations_router.register(app, deps)
    _knowledge_router.register(app, deps)
    _approvals_router.register(app, deps)
    _handoffs_router.register(app, deps)
    _rollouts_router.register(app, deps)
    _groups_router.register(app, deps)
    _scim_router.register(app, deps)
    _workspace_router.register(app, deps)
    _hub_router.register(app, deps)
    _org_policies_router.register(app, deps)
    _org_templates_router.register(app, deps)
    _quality_router.register(app, deps)
    _customers_router.register(app, deps)
    _automations_router.register(app, deps)
    _workspace_content_router.register(app, deps)
    _admin_overview_router.register(app, deps)
    _voice_router.register(app, deps)
    _public_router.register(app, deps)
    _chat_router.register(app, deps)
    _releases_router.register(app, deps)
    # [/routers]
    return app
