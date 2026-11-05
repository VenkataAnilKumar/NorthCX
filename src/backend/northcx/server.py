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
from .api.common import _err, _pieces
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
STATIC_DIR = Path(__file__).parent / "static"
SDK_FILES = {n: STATIC_DIR / n for n in ("northcx-widget.js", "northcx-client.js")}
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

    @app.get("/v1/voice/calls")
    async def voice_calls(limit: int = 50) -> Any:
        """Recent phone calls: outcome, consent, turns, barge-ins, languages and reply latency. No audio and no phone numbers."""
        return {"enabled": voice is not None, "calls": [c.summary() for c in await call_repo.recent(max(1, min(limit, 200)))]}

    @app.websocket("/v1/voice/stream")
    async def voice_stream(ws: WebSocket) -> None:
        """The telephony bridge's connection for one call (JSON messages both ways; see docs/05-technical/NorthCX_Voice.md). Authenticated with a
        channel key in the Authorization header, because the HTTP key check does not cover WebSockets."""
        if voice is None:
            await ws.close(code=4404)
            return
        ip = ws.client.host if ws.client else "unknown"
        if not access.limiter.allow(f"voice:{ip}", 60)[0]:
            await ws.close(code=4429)
            return
        if await access.enabled():
            header = ws.headers.get("authorization", "")
            ident, _ = await access.authenticate_detail(header[7:] if header.startswith("Bearer ") else None)
            if ident is None:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/v1/voice/stream", outcome="denied", detail={"client": ip}))
                await ws.close(code=4401)
                return
            if not ident.can("channel:inbound"):
                await audit.append(AuditEntry(actor=ident.name, role=ident.role, action="auth.denied", target="/v1/voice/stream", outcome="denied", detail={"permission": "channel:inbound"}))
                await ws.close(code=4403)
                return
        else:
            ident = OPEN_IDENTITY
        await ws.accept()

        async def send(msg: dict[str, Any]) -> None:
            try:
                await ws.send_json(msg)
            except Exception:  # the bridge went away; the call is ending anyway
                pass

        async def resolve(agent_id: str, session_id: str) -> Any:
            return await provider.get(agent_id, "production", session_id)
        call = CallSession(runtime, resolve, voice, call_repo, send)
        tokens, stamp = [300.0], [time.monotonic()]

        def bucket_allow() -> bool:
            now = time.monotonic()
            tokens[0] = min(300.0, tokens[0] + (now - stamp[0]) * 100)  # 100 messages a second sustained, bursts of 300
            stamp[0] = now
            tokens[0] -= 1
            return tokens[0] >= 0
        try:
            while True:
                raw = await ws.receive_text()
                if len(raw) > 65536:
                    await ws.close(code=1009)
                    break
                if not bucket_allow():
                    await ws.close(code=4429)  # a bridge that floods the stream is cut off
                    break
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "transcript" and msg.get("final", True) and not access.limiter.allow(f"voice-turns:{ident.key_id or ip}", 120)[0]:
                    continue  # at most 120 spoken turns a minute per key; the rest are ignored
                if msg.get("type") == "start" and call.rec is None:
                    await call.handle(msg)
                    await audit.append(AuditEntry(actor=ident.name, role=ident.role, action="voice.call", target=call.session_id, outcome="ok", detail={"callId": call.rec.call_id if call.rec else None}))
                else:
                    await call.handle(msg)
                if call.state == "ended":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            if call._turn is not None and not call._turn.done():
                try:
                    await asyncio.wait_for(asyncio.shield(call._turn), 20)  # an answer in progress is still saved to the conversation
                except Exception:
                    pass
            if call.state != "ended":
                await call.handle({"type": "end", "reason": "caller_hung_up"})
            try:
                await ws.close()
            except Exception:
                pass

    @app.get("/sdk/{name}")
    async def sdk_file(name: str) -> Any:
        """The browser SDK and the drop-in <northcx-chat> widget, so a site can load them from the same place it calls."""
        f = SDK_FILES.get(name)
        if f is None:
            return _err(404, "not_found", "No such file")
        return Response(f.read_bytes(), media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})

    @app.get("/", response_class=HTMLResponse)
    async def widget() -> str:
        return WIDGET_HTML

    @app.get("/health")
    async def health() -> dict[str, bool]:
        """Liveness: the process is up."""
        return {"ok": True}

    @app.get("/ready")
    async def ready() -> Any:
        """Readiness: the stores answer (for Postgres, the database is reachable). Used by load balancers and orchestrators."""
        try:
            await runtime.store.load_messages("__readiness_probe__")
            await traces.summaries(limit=1)
        except Exception:
            log.exception("readiness check failed")
            return JSONResponse({"ready": False}, status_code=503)
        return {"ready": True}

    async def chat_environment(request: Request, body: ChatBody) -> JSONResponse | None:
        """Only people with developer access may talk to dev or staging; customers and channels always get production."""
        if body.environment and body.environment != "production":
            who: Identity = request.state.identity
            if who.session_id is not None or not who.can("simulations:run"):
                await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", permission="simulations:run", environment=body.environment)
                return _err(403, "forbidden", f"The '{who.role}' role cannot use the {body.environment} environment (needs simulations:run)")
        return None

    async def load_attachments(body: ChatBody, agent: Any) -> list[Any] | JSONResponse:
        """The files a message refers to: they must belong to this conversation and be of a kind the agent accepts."""
        if not body.attachments:
            return []
        found = []
        for aid in dict.fromkeys(body.attachments):
            a = await attachment_repo.get(aid)
            if a is None or a.session_id != body.session_id:
                return _err(400, "bad_request", "Unknown attachment for this conversation")
            found.append(a)
        try:
            check_accepted(found, agent.attachments)
        except AttachmentError as e:
            return _err(400, "attachment_not_accepted", str(e))
        return found

    @app.put("/v1/sessions/{session_id}/attachments", status_code=201)
    async def upload_attachment(session_id: str, request: Request, filename: str | None = None) -> Any:
        """Upload one file (the request body is the file itself). It is identified by its content, size-limited, optionally scanned, and kept with the conversation."""
        who: Identity = request.state.identity
        if who.session_id is not None and who.session_id != session_id:
            await record(request, "auth.denied", f"PUT /v1/sessions/{session_id}/attachments", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot be used for that conversation")
        if not access.limiter.allow(f"upload:{session_id}", 20)[0]:
            return too_many(60, "uploads")
        cap = max(MAX_BYTES.values())
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            return _err(413, "too_large", "The file is too large")
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > cap:
                return _err(413, "too_large", "The file is too large")
        try:
            a = await accept_attachment(attachment_repo, session_id, filename, data, who.name, attachment_scanner)
        except AttachmentError as e:
            await record(request, "attachment.refused", customer_ref(session_id), "denied", reason=str(e)[:120])
            return _err(400, "attachment_refused", str(e))
        await record(request, "attachment.upload", customer_ref(session_id), kind=a.kind, size=a.size, sha256=a.sha256[:16])
        return a.meta()

    @app.get("/v1/sessions/{session_id}/attachments")
    async def list_attachments(session_id: str) -> Any:
        return {"attachments": [a.meta() for a in await attachment_repo.for_session(session_id)]}

    @app.get("/v1/attachments/{attachment_id}")
    async def download_attachment(attachment_id: str, request: Request) -> Any:
        """The file itself, for people reviewing a conversation. Served so a browser cannot run or render it."""
        a = await attachment_repo.get(attachment_id)
        if a is None:
            return _err(404, "not_found", "Unknown attachment")
        await record(request, "attachment.download", customer_ref(a.session_id), kind=a.kind)
        return Response(a.data, media_type=a.media_type, headers={
            "Content-Disposition": f'attachment; filename="{a.name}"', "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'", "Cache-Control": "no-store"})

    @app.post("/v1/agents/{agent_id}/chat/stream")
    async def chat_stream(agent_id: str, body: ChatBody, request: Request) -> Any:
        """Server-sent events: `progress` while tools run, then the reply in `delta` pieces, then `done`.

        The reply is released only after every supervisor has approved it, so the customer never sees text that a
        check could still reject; `delta` pieces are the approved reply, delivered progressively.
        """
        who: Identity = request.state.identity
        customer_id = body.customer_id
        if request.headers.get("idempotency-key"):
            return _err(400, "unsupported", "Idempotency-Key is not supported on the streaming endpoint; use /chat")
        if who.session_id is not None:
            if body.session_id != who.session_id or (who.agent and agent_id != who.agent):
                await record(request, "auth.denied", f"POST /v1/agents/{agent_id}/chat/stream", "denied", reason="outside the token's scope")
                return _err(403, "forbidden", "This chat token cannot be used for that conversation or agent")
            customer_id = who.customer_id
        if limits:
            ok, retry = access.limiter.allow(f"session:{body.session_id}", limits.chat_per_session_per_minute)
            if not ok:
                return too_many(retry, "messages in this conversation")
        try:
            agent = await provider.get(agent_id, "production", body.session_id)
            if agent is not None:
                agent = await runtime.active_agent(agent, body.session_id)
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            return _err(404, "not_found", "Unknown agent")
        queue: asyncio.Queue = asyncio.Queue()
        env_error = await chat_environment(request, body)
        if env_error is not None:
            return env_error
        environment = body.environment or "production"
        if environment != "production":
            try:
                agent = await provider.get(agent_id, environment, body.session_id)
                if agent is not None:
                    agent = await runtime.active_agent(agent, body.session_id, environment)
            except AgentUnavailable as e:
                return _err(503, "agent_unavailable", str(e))
            if agent is None:
                return _err(404, "not_found", "Unknown agent")

        files = await load_attachments(body, agent)
        if isinstance(files, JSONResponse):
            return files

        async def work() -> None:
            try:
                r = await runtime.run(agent, body.session_id, body.message, customer_id, attachments=files or None, progress=lambda e: queue.put_nowait(("progress", e)),
                                      channel=body.channel or ("web" if who.session_id else None))
                queue.put_nowait(("result", r))
            except Exception:
                queue.put_nowait(("error", {"code": "internal", "message": "Run failed"}))

        def sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        async def events() -> Any:
            task = asyncio.create_task(work())
            try:
                yield sse("started", {"agent": agent_id})
                while True:
                    kind, payload = await queue.get()
                    if kind == "progress":
                        yield sse("progress", payload)
                    elif kind == "error":
                        yield sse("error", payload)
                        return
                    else:
                        for piece in _pieces(payload.reply):
                            yield sse("delta", {"text": piece})
                        yield sse("done", {"reply": payload.reply, "status": payload.status, "traceId": payload.trace_id,
                                           "pendingApprovals": payload.pending_approvals, "handoffId": payload.handoff_id,
                                           "agentVersion": agent.version})
                        return
            finally:
                if not task.done():
                    await task  # the customer's message is always handled and saved, even if the client disconnects

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/v1/agents/{agent_id}/chat")
    async def chat(agent_id: str, body: ChatBody, request: Request) -> Any:
        who: Identity = request.state.identity
        customer_id = body.customer_id
        if who.session_id is not None:  # a chat token: one conversation, one customer, one agent
            if body.session_id != who.session_id or (who.agent and agent_id != who.agent):
                await record(request, "auth.denied", f"POST /v1/agents/{agent_id}/chat", "denied", reason="outside the token's scope")
                return _err(403, "forbidden", "This chat token cannot be used for that conversation or agent")
            customer_id = who.customer_id  # set by the company's server; the customer cannot choose it
        if limits:
            ok, retry = access.limiter.allow(f"session:{body.session_id}", limits.chat_per_session_per_minute)
            if not ok:
                return too_many(retry, "messages in this conversation")
        env_error = await chat_environment(request, body)
        if env_error is not None:
            return env_error
        environment = body.environment or "production"
        ikey = request.headers.get("idempotency-key")
        scope = None
        if ikey is not None:
            if not valid_key(ikey):
                return _err(400, "bad_idempotency_key", "Idempotency-Key must be 1-200 visible ASCII characters")
            scope = scope_hash(who.key_id or who.name, agent_id, body.session_id, ikey)
            out = await idem.begin(scope, request_hash([body.message, customer_id, environment, sorted(body.attachments)]), session_id=body.session_id)
            if out.state == "replay":
                return JSONResponse(out.response, headers={"Idempotent-Replay": "true"})
            if out.state == "conflict":
                return _err(422, "idempotency_key_reused", "This Idempotency-Key was used with a different request")
            if out.state == "in_progress":
                return _err(409, "request_in_progress", "A request with this Idempotency-Key is still being processed; retry shortly")
        try:
            agent = await provider.get(agent_id, environment, body.session_id)
            if agent is not None:
                agent = await runtime.active_agent(agent, body.session_id, environment)
        except AgentUnavailable as e:
            if scope:
                await idem.abandon(scope)
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            if scope:
                await idem.abandon(scope)
            return _err(404, "not_found", "Unknown agent")
        try:
            files = await load_attachments(body, agent)
            if isinstance(files, JSONResponse):
                if scope:
                    await idem.abandon(scope)
                return files
            r = await runtime.run(agent, body.session_id, body.message, customer_id, channel=body.channel or ("web" if who.session_id else None), environment=environment,
                                  attachments=files or None)
        except Exception:
            if scope:
                await idem.abandon(scope)
            return _err(500, "internal", "Run failed")
        result = {"reply": r.reply, "status": r.status, "traceId": r.trace_id, "pendingApprovals": r.pending_approvals,
                  "handoffId": r.handoff_id, "agentVersion": agent.version}
        if scope:
            await idem.complete(scope, result)
        return result


    @app.get("/v1/agents")
    async def list_agents() -> Any:
        try:
            live = await provider.all()
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        return {"agents": [{"id": a.id, "version": a.version, "digest": a.digest, "instructions": a.instructions, "model": a.model, "maxSteps": a.max_steps,
                            "tools": [{"name": t.name, "description": t.description, "approval": t.requires_approval is not None}
                                      for t in a.tools],
                            "guardrails": [g.name for g in a.guardrails],
                            "inputGuardrails": [g.name for g in a.input_guardrails],
                            "outputGuardrails": [g.name for g in a.output_guardrails],
                            "forcedTopics": [t.name for t in a.forced_handoffs]} for a in live]}


    MAX_EMAIL_BYTES = 1_000_000


    SSO_COOKIE = "northcx_sso"
    secure_cookie = bool(sso and sso.cfg.redirect_uri.startswith("https://"))


    # ---------------- versions and releases ----------------
    def need_rel() -> ReleaseService | JSONResponse:
        return releases or _err(501, "not_configured", "Versions and releases are not configured on this server")

    def version_json(v: Any, live_number: int | None = None, released: set[int] | None = None, full: bool = False) -> dict[str, Any]:
        out = {"id": v.id, "agentId": v.agent_id, "number": v.number, "digest": v.digest, "author": v.author, "note": v.note,
               "createdAt": v.created_at, "live": live_number == v.number, "everReleased": v.number in (released or set())}
        if full:
            out["spec"] = v.spec
            out["specYaml"] = spec_yaml(v.spec)
        return out

    def release_json(r: Any) -> dict[str, Any]:
        return {"id": r.id, "agentId": r.agent_id, "environment": r.environment, "action": r.action, "version": r.number,
                "versionId": r.version_id, "previousVersion": r.previous_number, "by": r.by, "note": r.note, "gate": r.gate,
                "createdAt": r.created_at, "toBaseline": r.version_id is None}

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

    @app.post("/v1/agents/{agent_id}/versions", status_code=201)
    async def create_version(agent_id: str, body: VersionBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        given = [x for x in (body.spec is not None, body.spec_yaml is not None, body.from_baseline) if x]
        if len(given) != 1:
            return _err(400, "bad_request", "Give exactly one of 'spec', 'specYaml' or 'fromBaseline'")
        try:
            if body.from_baseline:
                spec = svc.baseline(agent_id)
                if spec is None:
                    return _err(404, "not_found", f"Agent '{agent_id}' has no baseline spec file")
            elif body.spec_yaml is not None:
                spec = parse_spec(body.spec_yaml)
            else:
                spec = AgentSpec.model_validate(body.spec)
            v = await svc.create_version(agent_id, spec, actor(request, body.by), body.note)
        except (SpecError, InvalidSpec, Conflict, ValueError) as e:
            return rel_error(e if isinstance(e, (InvalidSpec, Conflict)) else InvalidSpec(str(e)))
        await record(request, "version.create", f"{agent_id}@{v.number}", digest=v.digest[:12])
        return JSONResponse(version_json(v, full=True), status_code=201)

    @app.get("/v1/catalog")
    async def catalog() -> Any:
        """The building blocks an editor can offer: tools, guardrails, policies, skills."""
        svc = need_rel()
        return svc if isinstance(svc, JSONResponse) else svc.registry.describe()

    @app.post("/v1/agents/{agent_id}/versions/preview")
    async def preview_version(agent_id: str, body: VersionBody) -> Any:
        """Check a spec without saving it (for editors): problems, digest, and what changed compared with production."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if body.spec is None:
            return _err(400, "bad_request", "Give the spec as 'spec'")
        return await svc.preview(agent_id, body.spec)

    @app.get("/v1/agents/{agent_id}/versions")
    async def list_versions(agent_id: str) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        live_v, _ = await svc.live(agent_id)
        history = await svc.releases.list(agent_id)
        released = {r.number for r in history if r.number is not None}
        return {"versions": [version_json(v, live_v.number if live_v else None, released) for v in await svc.versions.list(agent_id)]}

    @app.get("/v1/agents/{agent_id}/versions/{number}")
    async def get_version(agent_id: str, number: int) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        v = await svc.versions.get_number(agent_id, number)
        if v is None:
            return _err(404, "not_found", f"Agent '{agent_id}' has no version {number}")
        live_v, _ = await svc.live(agent_id)
        return version_json(v, live_v.number if live_v else None, {r.number for r in await svc.releases.list(agent_id) if r.number}, True)

    @app.get("/v1/agents/{agent_id}/versions/{number}/checklist")
    async def version_checklist(agent_id: str, number: int, request: Request, environment: str = "production") -> Any:
        """The publish checklist: required checks and notes for releasing this version to an environment."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        firing = [f"{a['rule']} ({a['severity']})" for a in (alerts.status()["active"] if alerts is not None else [])]
        try:
            return await svc.checklist(agent_id, number, environment, environment != "production" or who.can("releases:publish"), firing)
        except (NotFound, ValueError) as e:
            return rel_error(e) if isinstance(e, (NotFound, Conflict)) else _err(400, "bad_request", str(e))

    @app.get("/v1/agents/{agent_id}/versions/{a}/diff/{b}")
    async def version_diff(agent_id: str, a: int, b: int) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        va, vb = await svc.versions.get_number(agent_id, a), await svc.versions.get_number(agent_id, b)
        if va is None or vb is None:
            return _err(404, "not_found", f"Agent '{agent_id}' needs both versions {a} and {b}")
        return {"from": a, "to": b, **diff_specs(va.spec, vb.spec)}

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

    @app.post("/v1/agents/{agent_id}/releases")
    async def publish(agent_id: str, body: PublishBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.environment, "releases:publish")) is not None:
            return denied
        target = f"{agent_id}@{body.version}" + ("" if body.environment == "production" else f" ({body.environment})")
        try:
            rel = await svc.publish(agent_id, body.version, actor(request, body.by), body.note, body.environment)
        except GateBlocked as e:  # an attempt to release something unproven is itself worth recording
            await record(request, "release.publish", target, "blocked", reasons=e.reasons[:10], environment=body.environment)
            return rel_error(e)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.publish", target, previous=rel.previous_number, gate=rel.gate, note=bool(body.note), environment=body.environment)
        return release_json(rel)


    @app.post("/v1/agents/{agent_id}/promote")
    async def promote(agent_id: str, body: PromoteBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.to, "releases:publish")) is not None:
            return denied
        try:
            rel = await svc.promote(agent_id, body.to, actor(request, body.by), body.note)
        except GateBlocked as e:
            await record(request, "release.promote", f"{agent_id} -> {body.to}", "blocked", reasons=e.reasons[:10], environment=body.to)
            return rel_error(e)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.promote", f"{agent_id}@{rel.number} -> {body.to}", previous=rel.previous_number, gate=rel.gate, environment=body.to)
        return release_json(rel)

    @app.post("/v1/agents/{agent_id}/rollback")
    async def rollback(agent_id: str, body: RollbackBody, request: Request) -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.environment, "releases:rollback")) is not None:
            return denied
        try:
            rel = await svc.rollback(agent_id, actor(request, body.by), body.note, body.to_version, body.environment)
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "release.rollback", f"{agent_id}@{rel.number if rel.number else 'spec-file'}",
                     previous=rel.previous_number, note=bool(body.note), environment=body.environment)
        return release_json(rel)

    @app.get("/v1/agents/{agent_id}/releases")
    async def release_history(agent_id: str, environment: str = "production") -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            check_environment(environment)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        return {"releases": [release_json(r) for r in await svc.releases.list(agent_id, environment)]}

    @app.get("/v1/agents/{agent_id}/environments")
    async def agent_environments(agent_id: str) -> Any:
        """What is live in dev, staging and production, and what each actually serves."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        if svc.baseline(agent_id) is None and not await svc.versions.list(agent_id):
            return _err(404, "not_found", f"Unknown agent '{agent_id}'")
        out = {}
        for env, info in (await svc.environments(agent_id)).items():
            v, rel, served = await svc.resolve(agent_id, env)
            out[env] = {"version": info["version"], "release": release_json(info["release"]) if info["release"] else None,
                        "servedFrom": served, "servedVersion": v.number if v else None}
        return {"agentId": agent_id, "strictPromotion": svc.strict_promotion, "environments": out}

    @app.get("/v1/agents/{agent_id}/live")
    async def live(agent_id: str, environment: str = "production") -> Any:
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        try:
            v, rel, served = await svc.resolve(agent_id, environment)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        base = svc.baseline(agent_id)
        if v is None and base is None:
            return _err(404, "not_found", f"Unknown agent '{agent_id}'")
        spec = v.spec if v else json.loads(base.canonical())
        return {"agentId": agent_id, "environment": environment, "servedFrom": served, "source": "release" if v else "baseline", "version": v.number if v else None,
                "digest": v.digest if v else base.digest(), "release": release_json(rel) if rel else None,
                "spec": spec, "specYaml": spec_yaml(spec)}

    @app.get("/v1/sessions/{session_id}/outbox")
    async def outbox(session_id: str, request: Request, after: int = 0) -> Any:
        who: Identity = request.state.identity
        if who.session_id is not None and session_id != who.session_id:
            await record(request, "auth.denied", f"GET /v1/sessions/{session_id}/outbox", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot read another conversation")
        items = await runtime.outbox.list(session_id, after)
        return {"messages": [{"id": m.id, "kind": m.kind, "createdAt": m.created_at, **m.payload} for m in items]}

    # [routers] generated by the WP0.1 split; one module per area of routes under northcx/api/routers
    deps = AppDeps(MAX_EMAIL_BYTES=MAX_EMAIL_BYTES, SSO_COOKIE=SSO_COOKIE, access=access, actor=actor, agents=agents, alerts=alerts, audit=audit, crawl_scheduler=crawl_scheduler, crawler=crawler, email=email, events=events, fb=fb, flow=flow, insight=insight, kb=kb, limits=limits, need_env=need_env, need_rel=need_rel, privacy=privacy, provider=provider, record=record, regression=regression, rel_error=rel_error, releases=releases, residency=residency, review_repo=review_repo, rollouts=rollouts, runtime=runtime, secure_cookie=secure_cookie, simulations=simulations, skills=skills, sms=sms, sso=sso, tag_repo=tag_repo, telegram=telegram, templates=templates, too_many=too_many, traces=traces, transcriber=transcriber, version_json=version_json, whatsapp=whatsapp)
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
    # [/routers]
    return app
