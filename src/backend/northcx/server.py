from __future__ import annotations

from typing import Any

import asyncio
import json
import logging
import re
import secrets
import time
import uuid

import yaml
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import WebSocket, WebSocketDisconnect, Query, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from urllib.parse import urlencode, urlsplit

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .access import ROLES, SSO_CREATOR, AccessControl, Identity, LimitConfig, OPEN_IDENTITY
from .channels.email import EmailChannel, EmailParseError
from .tokens import DEFAULT_TTL, MAX_TTL, MIN_TTL, TokenSigner, derive_secret
from .approval_flow import ApprovalFlow
from .channels.sms import SmsChannel, parse_form, phone_hash
from .channels.telegram import TelegramChannel
from .channels.whatsapp import TemplateRefused, WhatsAppChannel
from .templates import Template, TemplateError, render
from .alerts import AlertManager
from .journeys import SYSTEM as JOURNEY_SYSTEM, DraftError, JourneySpec, draft_prompt, parse_draft, scenarios as journey_scenarios_list, scenarios_yaml as journey_scenarios_yaml
from .sso import Sso, SsoError
from .rollout import CANDIDATE, CONTROL, RolloutService, compare as compare_arms, rollout_json
from .reviews import FAILURES, HANDOFF_JUDGEMENTS, VERDICTS, InMemoryReviews, Review, ReviewError, ReviewRepo, queue as review_queue_rows, quality, review_json, validate as review_validate
from .assist import AssistError
from . import __version__
from .events import EVENTS, EventFeed, EventingAudit
from .crawler import Crawler, CrawlConfig, CrawlRefused
from .crawl_schedule import CrawlScheduler
from .ingest import IngestError, extract as extract_file
from .hardening import BodyLimit, SecurityHeaders
from .voice import CallRepo, CallSession, InMemoryCalls, VoiceConfig
from .attachments import MAX_BYTES, MAX_PER_MESSAGE, AttachmentError, AttachmentRepo, InMemoryAttachments, Scanner, accept as accept_attachment, check_accepted
from .handoffs import PERSON_PREFIX, return_note, transcript
from .analytics_qa import ask as ask_insights
from .builder import BuildError, draft_agent, refine_agent
from .scenario_draft import draft_scenarios
from .transcribe import HttpTranscriber, TranscribeError
from .insights import TAG, InMemoryTags, TagRepo, FeedbackRepo, InMemoryFeedback, InMemoryInsightsSource, InsightsService
from .simulation.managed import parse_definition
from .regression import RegressionRunner, scenario_from_traces
from .simulation.scenario import ScenarioError
from .privacy import InMemoryPrivacy, PrivacyService, customer_ref
from .knowledge import InMemoryKnowledge, KnowledgeError, KnowledgeStore, Source
from .idempotency import IdempotencyStore, InMemoryIdempotency, scope_hash, request_hash, valid_key
from .audit import AuditEntry, AuditRepo, InMemoryAudit
from .catalog import AgentUnavailable, as_provider
from .types import LLMRequest, text_of
from .runtime import Runtime
from .simulation import Busy, SimulationService
from .spec import AgentSpec, SpecError, parse_spec
from .versions import check_environment,  Conflict, GateBlocked, InvalidSpec, NotFound, ReleaseService, diff_specs, spec_yaml
from .trace import TraceRepo
from .widget import WIDGET_HTML
from .api.common import SDK_FILES, STATIC_DIR, _err, _pieces
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
from .api.routers import voice as _voice_router
from .api.routers import public as _public_router
from .api.routers import chat as _chat_router
from .api.routers import releases as _releases_router
from .api.models import AskBody, BuilderBody, BuilderSource, ChatBody, CrawlBody, DecisionBody, DocumentBody, EnabledBody, ExpireBody, FeedbackBody, JourneyDraftBody, JourneyScenariosBody, KeyBody, PercentBody, PromoteBody, PublishBody, RefineBody, ReplyBody, ResolveBody, RetentionBody, ReviewBody, RollbackBody, RolloutBody, ScenarioBody, ScenarioDraftBody, ScheduleBody, SimRunBody, SourceBody, TemplateBody, TemplateSendBody, TokenBody, VersionBody


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
    ("POST", r"/v1/channels/whatsapp/templates/send", "channel:inbound"),
    ("POST", r"/v1/agents/[^/]+/journeys/scenarios", "simulations:run"),
    ("GET", r"/v1/trace-export", "traces:read"),
    ("GET", r"/v1/traces/[^/]+/exports", "traces:read"),
    ("GET", r"/v1/traces", "traces:read"),
    ("GET", r"/v1/traces/[^/]+", "traces:read"),
    ("GET", r"/v1/catalog", "agents:read"),
    ("POST", r"/v1/agents/[^/]+/versions/preview", "versions:create"),
    ("GET", r"/v1/templates", "agents:read"),
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
    ("POST", r"/v1/simulations/runs", "simulations:run"),
    ("GET", r"/v1/keys", "keys:manage"),
    ("POST", r"/v1/keys", "keys:manage"),
    ("POST", r"/v1/keys/[^/]+/revoke", "keys:manage"),
    ("GET", r"/v1/audit", "audit:read"),
    ("GET", r"/v1/audit/verify", "audit:read"),
]
PUBLIC_ROUTES = {("GET", "/"), ("GET", "/health"), ("GET", "/ready")}
_COMPILED = [(m, re.compile(p), perm) for m, p, perm in ROUTE_PERMISSIONS]
log = logging.getLogger("northcx.server")


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
               voice: VoiceConfig | None = None, calls: CallRepo | None = None, crawler: Crawler | None = None) -> FastAPI:
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
        task = flusher = None
        if runtime.outbox.notifier is not None:  # retry deliveries that failed (email, webhooks) with back-off
            async def flush_loop() -> None:
                while True:
                    await asyncio.sleep(15)
                    try:
                        await runtime.outbox.flush()
                    except Exception:
                        log.exception("outbox flush failed")

            flusher = asyncio.create_task(flush_loop())
        if approval_ttl_seconds:  # periodically expire stale approvals and hand those conversations to a person
            async def sweep() -> None:
                while True:
                    await asyncio.sleep(max(1.0, min(60.0, approval_ttl_seconds / 2)))
                    try:
                        await flow.expire_stale(agents, approval_ttl_seconds)
                    except Exception:  # keep sweeping; a failed pass is retried on the next tick
                        log.exception("approval expiry pass failed")

            task = asyncio.create_task(sweep())
        export_task = None
        if runtime.exports is not None:
            async def export_loop() -> None:
                while True:
                    await asyncio.sleep(10)
                    try:
                        await runtime.exports.flush(traces)
                    except Exception:
                        log.exception("trace export pass failed")

            export_task = asyncio.create_task(export_loop())
        alert_task = None
        if alerts is not None:
            async def alert_loop() -> None:
                while True:
                    await asyncio.sleep(60)
                    try:
                        await alerts.evaluate()
                    except Exception:
                        log.exception("alert evaluation failed")

            alert_task = asyncio.create_task(alert_loop())
        inbox_task = None
        if runtime.inbox is not None:
            async def inbox_loop() -> None:
                while True:
                    await asyncio.sleep(10)
                    try:
                        await runtime.inbox.flush(runtime.handoffs)
                    except Exception:
                        log.exception("inbox delivery pass failed")

            inbox_task = asyncio.create_task(inbox_loop())
        retention = None
        if retention_days:  # age out old conversations once an hour
            async def retain() -> None:
                while True:
                    await asyncio.sleep(3600)
                    try:
                        r = await privacy.purge_idle(retention_days)
                        if r["sessions"]:
                            await audit.append(AuditEntry(actor="system", role="system", key_id=None, action="privacy.retention", target=f"older than {retention_days:g} days",
                                                          outcome="success", detail=r))
                    except Exception:
                        log.exception("retention sweep failed")

            retention = asyncio.create_task(retain())
        indexer = getattr(kb, "indexer", None)
        if indexer is not None:
            indexer.start()
        if crawl_scheduler is not None:
            crawl_scheduler.start()
        yield
        if indexer is not None:
            await indexer.stop()
        if crawl_scheduler is not None:
            await crawl_scheduler.stop()
        for t in (task, flusher, retention, inbox_task, export_task, alert_task):
            if t:
                t.cancel()

    # The interactive API docs are off: they would describe the API to anyone who can reach the server.
    app = FastAPI(title="NorthCX", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.rollouts = rollouts
    limits = access.limits

    def too_many(retry: float, what: str) -> JSONResponse:
        r = _err(429, "rate_limited", f"Too many {what}; retry in {max(1, round(retry))} s")
        r.headers["Retry-After"] = str(max(1, round(retry)))
        return r

    async def record(request: Request | None, action: str, target: str = "", outcome: str = "success", **detail: Any) -> None:
        """Write an audit entry for the caller. A failure to record is raised: a privileged action must not go unrecorded."""
        who: Identity = getattr(request.state, "identity", OPEN_IDENTITY) if request is not None else OPEN_IDENTITY
        try:
            await audit.append(AuditEntry(actor=who.name, role=who.role, key_id=who.key_id, action=action, target=target,
                                          outcome=outcome, detail=detail))
        except Exception:
            log.exception("AUDIT FAILURE: could not record %s on %s", action, target)
            raise

    def actor(request: Request, claimed: str | None) -> str:
        """Who is acting. With authentication it is the key's name; a name in the body is only trusted without it."""
        who: Identity = request.state.identity
        return (claimed.strip() if claimed and claimed.strip() else "anonymous") if who.open_mode else who.name

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
                if limits and not access.limiter.allow(f"authfail:{ip}", limits.auth_failures_per_minute)[0]:
                    return too_many(60, "failed sign-in attempts")
                if access.limiter.allow(f"authlog:{ip}", 6)[0]:  # sampled, so guessing cannot flood the log
                    await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target=path,
                                                  outcome="denied", detail={"client": ip}))
                if why == "expired":
                    return _err(401, "token_expired", "This chat session has expired; ask the site for a new one")
                return _err(401, "unauthorized", "Missing or invalid API key")
        else:
            ident = OPEN_IDENTITY
        request.state.identity = ident
        if limits:
            ok, retry = access.limiter.allow(f"key:{ident.key_id or ip}", limits.channel_per_minute if ident.role == "channel" else limits.per_key_per_minute)
            if not ok:
                return too_many(retry, "requests")
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


    def need_rel() -> ReleaseService | JSONResponse:
        return releases or _err(501, "not_configured", "Versions and releases are not configured on this server")

    def version_json(v: Any, live_number: int | None = None, released: set[int] | None = None, full: bool = False) -> dict[str, Any]:
        out = {"id": v.id, "agentId": v.agent_id, "number": v.number, "digest": v.digest, "author": v.author, "note": v.note,
               "createdAt": v.created_at, "live": live_number == v.number, "everReleased": v.number in (released or set())}
        if full:
            out["spec"] = v.spec
            out["specYaml"] = spec_yaml(v.spec)
        return out


    def rel_error(e: Exception) -> JSONResponse:
        if isinstance(e, NotFound):
            return _err(404, "not_found", str(e))
        if isinstance(e, GateBlocked):
            resp = _err(409, "gate_not_satisfied", str(e))
            resp.body = json.dumps({"error": {"code": "gate_not_satisfied", "message": str(e), "reasons": e.reasons}}).encode()
            resp.headers["content-length"] = str(len(resp.body))
            return resp
        if isinstance(e, Conflict):
            return _err(409, "conflict", str(e))
        return _err(400, "bad_request", str(e))


    async def need_env(request: Request, environment: str, perm: str) -> JSONResponse | None:
        """Dev and staging are for developers; production needs the release permission."""
        try:
            check_environment(environment)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        who: Identity = request.state.identity
        if environment == "production" and not who.can(perm):
            await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", permission=perm)
            return _err(403, "forbidden", f"The '{who.role}' role cannot do this (needs {perm})")
        return None


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
    _voice_router.register(app, deps)
    _public_router.register(app, deps)
    _chat_router.register(app, deps)
    _releases_router.register(app, deps)
    # [/routers]
    return app
