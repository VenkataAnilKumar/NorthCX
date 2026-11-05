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


    # ---- insights ----
    def window(from_: float | None, to: float | None) -> tuple[float, float] | JSONResponse:
        now = time.time()
        end = now if to is None else to
        start = end - 7 * 86400 if from_ is None else from_
        if start >= end or end - start > 366 * 86400:
            return _err(400, "bad_request", "'from' must be before 'to', and the period at most 366 days")
        return start, end

    @app.get("/v1/insights/overview")
    async def insights_overview(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        return w if isinstance(w, JSONResponse) else await insight.overview(w[0], w[1], agent, environment)

    @app.post("/v1/insights/ask")
    async def insights_ask(body: AskBody, request: Request) -> Any:
        """A question about performance in plain words. The model only plans the query (one known figure, a period, maybe an agent); the numbers
        and the sentence come from the same code as the Insights pages, and the plan is returned so the reading can be checked."""
        who: Identity = request.state.identity
        if not access.limiter.allow(f"insights-ask:{who.key_id or 'open'}", 15)[0]:
            return too_many(60, "questions")
        try:
            out = await ask_insights(runtime.llm, insight, body.question, [a.id for a in await provider.all()], body.environment, tags=tag_repo, can_list=who.can("traces:read"))
        except Exception:
            log.exception("insights question failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "insights.ask", "insights", answerable=out["answerable"], metric=(out.get("plan") or {}).get("metric"))
        return out

    @app.get("/v1/insights/timeseries")
    async def insights_series(from_: float | None = Query(None, alias="from"), to: float | None = None, bucket: str = "day", agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        if isinstance(w, JSONResponse):
            return w
        if bucket not in ("hour", "day"):
            return _err(400, "bad_request", "bucket must be hour or day")
        return {"bucket": bucket, "points": await insight.series(w[0], w[1], bucket, agent, environment)}

    @app.get("/v1/insights/failures")
    async def insights_failures(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        return w if isinstance(w, JSONResponse) else {"causes": await insight.failure_analysis(w[0], w[1], agent, environment)}

    @app.get("/v1/insights/gaps")
    async def insights_gaps(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production") -> Any:
        w = window(from_, to)
        return w if isinstance(w, JSONResponse) else await insight.intent_gaps(w[0], w[1], agent, environment)

    @app.post("/v1/sessions/{session_id}/feedback", status_code=201)
    async def post_feedback(session_id: str, body: FeedbackBody, request: Request) -> Any:
        """A customer's rating of a conversation (1 to 5). A chat token can rate only its own conversation; a second rating replaces the first."""
        who: Identity = request.state.identity
        if who.session_id is not None and session_id != who.session_id:
            await record(request, "auth.denied", f"POST /v1/sessions/{session_id}/feedback", "denied", reason="outside the token's scope")
            return _err(403, "forbidden", "This chat token cannot rate another conversation")
        if not await traces.summaries(session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        new = await fb.add(session_id, body.rating, body.comment.strip())
        if events is not None:
            await events.emit("conversation.rated", {"rating": body.rating, "replaced": not new}, session_id)
        return JSONResponse({"saved": True, "replaced": not new}, status_code=201)

    @app.get("/v1/reviews/queue")
    async def review_queue(from_: float | None = Query(None, alias="from"), to: float | None = None, agent: str | None = None, environment: str = "production",
                           includeReviewed: bool = False, sample: float = 0.05, limit: int = 50) -> Any:
        """Conversations most worth a human look: hand-offs, low ratings, failed or blocked turns, plus a small random sample."""
        end = time.time() if to is None else to
        start = end - 14 * 86400 if from_ is None else from_
        if start >= end or end - start > 366 * 86400 or not 0 <= sample <= 1:
            return _err(400, "bad_request", "'from' must be before 'to', the period at most 366 days, and sample between 0 and 1")
        turns, handoffs, feedback = await insight._load(start, end, agent, environment)
        reviewed = await review_repo.for_sessions(list({t.session_id for t in turns}))
        return {"queue": review_queue_rows(turns, handoffs, feedback, reviewed, includeReviewed, sample, max(1, min(limit, 200)))}

    @app.get("/v1/sessions/{session_id}/transcript")
    async def session_transcript(session_id: str) -> Any:
        """Everything a reviewer needs to judge one conversation."""
        summaries = await traces.summaries(session_id, 200)
        if not summaries:
            return _err(404, "not_found", "Unknown conversation")
        msgs = await runtime.store.load_messages(session_id)
        hs = await runtime.handoffs.list(None, session_id, 20)
        rev = await review_repo.get(session_id)
        fbk = await fb.for_session(session_id)
        return {"sessionId": session_id, "transcript": transcript(msgs), "tags": await tag_repo.all_for(session_id),
                "traces": [{"id": t.id, "status": t.status, "tools": t.tools, "startedAt": t.started_at, "agentVersion": t.agent_version, "environment": t.environment}
                           for t in sorted(summaries, key=lambda t: t.started_at or 0)],
                "handoffs": [{"id": h.id, "trigger": h.trigger, "state": h.state, "queue": h.queue, "reason": h.reason} for h in hs],
                "rating": fbk.rating if fbk else None, "review": review_json(rev) if rev else None}

    @app.put("/v1/sessions/{session_id}/review")
    async def put_review(session_id: str, body: ReviewBody, request: Request) -> Any:
        if not await traces.summaries(session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        handed = bool(await runtime.handoffs.list(None, session_id, 1))
        try:
            verdict, handoff, failures, note = review_validate(body.verdict, body.handoff, body.failures, body.note, handed)
        except ReviewError as e:
            return _err(400, "bad_request", str(e))
        who = actor(request, None)
        new = await review_repo.put(Review(session_id, verdict, handoff, failures, note, who))
        await record(request, "conversation.review", customer_ref(session_id), verdict=verdict, handoff=handoff, failures=failures)
        return {"saved": True, "replaced": not new}

    @app.get("/v1/insights/review-quality")
    async def review_quality(from_: float | None = Query(None, alias="from"), to: float | None = None) -> Any:
        w = window(from_, to)
        if isinstance(w, JSONResponse):
            return w
        return {"period": {"from": w[0], "to": w[1]}, **quality(await review_repo.between(w[0], w[1]))}

    @app.get("/v1/conversations/search")
    async def conversation_search(q: str = "", status: str | None = None, tag: str | None = None, handedOff: bool | None = None, agent: str | None = None,
                                  environment: str = "production", from_: float | None = Query(None, alias="from"), to: float | None = None, limit: int = 50,
                                  language: str | None = None) -> Any:
        """Find conversations by what was said, outcome, hand-off, rating and tag. Text shown is masked."""
        end = time.time() if to is None else to
        start = end - 30 * 86400 if from_ is None else from_
        if start >= end or end - start > 366 * 86400 or len(q) > 200:
            return _err(400, "bad_request", "'from' must be before 'to', the period at most 366 days, and the search at most 200 characters")
        return {"conversations": await insight.search(start, end, tag_repo, q, status, tag, handedOff, agent, environment, max(1, min(limit, 200)), language)}

    @app.get("/v1/sessions/{session_id}/tags")
    async def get_tags(session_id: str) -> Any:
        return {"sessionId": session_id, "tags": await tag_repo.all_for(session_id)}

    @app.put("/v1/sessions/{session_id}/tags/{tag}")
    async def add_tag(session_id: str, tag: str, request: Request) -> Any:
        if not TAG.match(tag):
            return _err(400, "bad_request", "A tag is 1-40 lowercase letters, digits, - or _")
        if not await traces.summaries(session_id, 1):
            return _err(404, "not_found", "Unknown conversation")
        try:
            new = await tag_repo.add(session_id, tag, actor(request, None))
        except ValueError as e:
            return _err(409, "conflict", str(e))
        if new:
            await record(request, "conversation.tag", customer_ref(session_id), tag=tag)
        return {"sessionId": session_id, "tag": tag, "added": new, "tags": await tag_repo.all_for(session_id)}

    @app.delete("/v1/sessions/{session_id}/tags/{tag}")
    async def remove_tag(session_id: str, tag: str, request: Request) -> Any:
        if not await tag_repo.remove(session_id, tag):
            return _err(404, "not_found", "That conversation does not have that tag")
        await record(request, "conversation.untag", customer_ref(session_id), tag=tag)
        return {"removed": True, "tags": await tag_repo.all_for(session_id)}

    @app.get("/v1/alerts")
    async def alert_status() -> Any:
        """The alert rules, which are firing now, and recent alert events."""
        return alerts.status() if alerts is not None else {"enabled": False}

    @app.get("/v1/regression")
    async def regression_status() -> Any:
        """Whether simulations re-run when the knowledge changes, and how the last re-run went."""
        return regression.status() if regression is not None else {"enabled": False}

    @app.get("/v1/events/types")
    async def event_types() -> Any:
        return {"enabled": events is not None, "types": [{"type": k, "description": v, "subscribed": events is not None and k in events.types} for k, v in EVENTS.items()]}

    @app.get("/v1/events")
    async def event_feed(after: int = 0, limit: int = 100) -> Any:
        """The same events the webhook sends, for receivers that would rather poll. `after` is the id of the last event already seen."""
        if events is None:
            return _err(501, "not_configured", "Status events are not configured: set NORTHCX_EVENTS_WEBHOOK_URL (and NORTHCX_EVENTS_WEBHOOK_SECRET)")
        return {"events": await events.listing(max(0, after), limit)}

    @app.get("/v1/residency")
    async def residency_report() -> Any:
        """Where this deployment keeps data and where it sends it, checked against the residency file (evidence for a data-processing agreement)."""
        return residency or {"configured": False, "flows": [], "compliant": False, "problems": [], "note": "Residency is not reported by this server."}

    @app.post("/v1/builder/draft")
    async def builder_draft(body: BuilderBody, request: Request) -> Any:
        """A first draft of an agent from procedures and conversation transcripts. Names are checked against what this deployment has;
        personal details are masked before the model sees anything; nothing is saved."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        if not access.limiter.allow(f"builder:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "agent drafts")
        try:
            out = await draft_agent(runtime.llm, svc.registry, body.agent_id, body.goal, [s.model_dump() for s in body.sources])
        except BuildError as e:
            return _err(422, "unusable_draft", str(e))
        except Exception:
            log.exception("agent draft failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "builder.draft", body.agent_id, sources=len(body.sources), warnings=len(out["warnings"]))
        return out

    @app.post("/v1/builder/scenarios")
    async def builder_scenarios(body: ScenarioDraftBody, request: Request) -> Any:
        """Test scenarios for a drafted agent: platform-guarantee tests that are run against the draft, and question tests that need a live model. Saves nothing."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        if not access.limiter.allow(f"builder:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "agent drafts")
        try:
            spec = parse_spec(body.spec)
        except SpecError as e:
            return _err(400, "bad_request", str(e)[:400])
        try:
            out = await draft_scenarios(runtime.llm, svc.registry, spec, body.examples)
        except ValueError as e:
            return _err(422, "unusable_draft", str(e))
        except Exception:
            log.exception("scenario draft failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "builder.scenarios", spec.id, checked=len(out["checked"]), needLiveModel=len(out["needLiveModel"]))
        return out

    @app.post("/v1/builder/refine")
    async def builder_refine(body: RefineBody, request: Request) -> Any:
        """Revise a draft after an instruction ("never promise delivery dates"). Same limits as a first draft; settings the model may not set are carried over untouched."""
        svc = need_rel()
        if isinstance(svc, JSONResponse):
            return svc
        who: Identity = request.state.identity
        if not access.limiter.allow(f"builder:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "agent drafts")
        try:
            out = await refine_agent(runtime.llm, svc.registry, body.current, body.instruction)
        except BuildError as e:
            return _err(422, "unusable_draft", str(e))
        except Exception:
            log.exception("agent refine failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await record(request, "builder.refine", out["spec"]["id"], changes=len(out["changes"]), warnings=len(out["warnings"]))
        return out

    @app.post("/v1/builder/transcribe")
    async def builder_transcribe(request: Request, language: str | None = None) -> Any:
        """Turn a recording (the request body is the audio file) into transcript text with the operator's transcription service. Nothing is stored."""
        if transcriber is None:
            return _err(501, "not_configured", "Transcription is not configured: set NORTHCX_TRANSCRIBE_URL and NORTHCX_TRANSCRIBE_MODEL")
        who: Identity = request.state.identity
        if not access.limiter.allow(f"transcribe:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "transcriptions")
        if language is not None and not re.fullmatch(r"[a-z]{2,3}", language):
            return _err(400, "bad_request", "language must be a short code such as en")
        cap = 25 * 1024 * 1024
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            return _err(413, "too_large", "The recording is too large")
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > cap:
                return _err(413, "too_large", "The recording is too large")
        try:
            text_ = await transcriber.transcribe(data, language)
        except TranscribeError as e:
            return _err(422, "unusable_recording", str(e))
        await record(request, "builder.transcribe", "recording", size=len(data))
        return {"text": text_, "characters": len(text_), "note": "Read it before using it: transcripts can contain mistakes. Personal details are masked when it is used to draft an agent."}

    @app.post("/v1/agents/{agent_id}/journeys/draft")
    async def journey_draft(agent_id: str, body: JourneyDraftBody, request: Request) -> Any:
        """A journey drafted from a plain-language description by the model. Checked against the agent's real tools; never saved by itself."""
        who: Identity = request.state.identity
        if not access.limiter.allow(f"journey-draft:{who.key_id or 'open'}", 10)[0]:
            return too_many(60, "journey drafts")
        try:
            agent = await provider.get(agent_id)
        except AgentUnavailable as e:
            return _err(503, "agent_unavailable", str(e))
        if agent is None:
            return _err(404, "not_found", "Unknown agent")
        tools = [(t.name, t.description) for t in agent.tools]
        try:
            res = await runtime.llm.complete(LLMRequest(system=JOURNEY_SYSTEM, messages=[{"role": "user", "content": draft_prompt(body.description, tools)}], max_tokens=1500))
        except Exception:
            log.exception("journey draft failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        try:
            journey, warnings = parse_draft(text_of(res.content), {n for n, _ in tools})
        except DraftError as e:
            return _err(422, "unusable_draft", str(e))
        await record(request, "journey.draft", agent_id, steps=len(journey.steps), warnings=len(warnings))
        data = journey.model_dump(mode="json")
        return {"journey": data, "yaml": yaml.safe_dump(data, sort_keys=False, allow_unicode=True), "warnings": warnings,
                "note": "A draft for a person to review. Nothing is saved until it is added to the agent and a version is created."}

    @app.post("/v1/agents/{agent_id}/journeys/scenarios")
    async def journey_scenarios(agent_id: str, body: JourneyScenariosBody) -> Any:
        """Test scenario drafts for a journey, one per sample opening message (not required until someone relies on them)."""
        try:
            j = JourneySpec.model_validate(body.journey)
        except ValueError as e:
            return _err(400, "bad_request", "; ".join(f"{'.'.join(str(p) for p in x['loc'])}: {x['msg']}" for x in getattr(e, "errors", lambda: [])()[:5]) or str(e))
        return {"scenarios": journey_scenarios_list(j, agent_id), "yaml": journey_scenarios_yaml(j, agent_id)}

    @app.get("/v1/sessions/{session_id}/scenario-draft")
    async def scenario_draft(session_id: str, request: Request) -> Any:
        """A scenario drafted from a real conversation (personal data masked), for a person to review and add to the scenario files."""
        found = [t for t in [await traces.get(s.id) for s in await traces.summaries(session_id, 200)] if t is not None]
        try:
            d = scenario_from_traces(found, session_id)
        except ScenarioError as e:
            return _err(404 if not found else 400, "not_found" if not found else "bad_request", str(e))
        await record(request, "scenario.draft", customer_ref(session_id), turns=len(d.scenario["turns"]))
        return {"yaml": d.yaml, "scenario": d.scenario, "warnings": d.warnings}

    @app.get("/v1/trace-export")
    async def trace_export_status() -> Any:
        """Whether export is on, where traces go, what content is sent, and how deliveries are doing."""
        x = runtime.exports
        if x is None:
            return {"configured": False}
        return {"configured": True, "exporters": sorted(x.exporters), "content": x.redactor.mode, "sample": x.sample, "environment": x.environment,
                **await x.repo.counts()}

    @app.get("/v1/traces/{trace_id}/exports")
    async def trace_exports(trace_id: str) -> Any:
        if await traces.get(trace_id) is None:
            return _err(404, "not_found", "Unknown trace")
        jobs = await runtime.exports.repo.for_trace(trace_id) if runtime.exports is not None else []
        return {"configured": runtime.exports is not None, "deliveries": [j.to_dict() for j in jobs]}

    @app.get("/v1/traces/{trace_id}")
    async def get_trace(trace_id: str) -> Any:
        t = await traces.get(trace_id)
        return t.to_dict() if t else _err(404, "not_found", "Unknown trace")


    # ---- knowledge ----
    @app.get("/v1/knowledge/sources")
    async def kb_sources() -> Any:
        return {"sources": [{"id": s.id, "name": s.name, "staleAfterDays": s.stale_after_days, "createdAt": s.created_at} for s in await kb.list_sources()]}

    @app.post("/v1/knowledge/sources", status_code=201)
    async def kb_create_source(body: SourceBody, request: Request) -> Any:
        try:
            s = await kb.create_source(Source(body.id, body.name, body.stale_after_days))
        except KnowledgeError as e:
            return _err(400 if "already exists" not in str(e) else 409, "bad_request" if "already exists" not in str(e) else "conflict", str(e))
        await record(request, "knowledge.source.create", s.id, name=s.name)
        return {"id": s.id, "name": s.name, "staleAfterDays": s.stale_after_days}

    @app.delete("/v1/knowledge/sources/{source_id}")
    async def kb_delete_source(source_id: str, request: Request) -> Any:
        if await kb.get_source(source_id) is None:
            return _err(404, "not_found", "Unknown source")
        n = await kb.delete_source(source_id)
        await record(request, "knowledge.source.delete", source_id, documents=n)
        if regression is not None:
            regression.trigger(f"source {source_id} deleted")
        return {"deleted": True, "documents": n}

    @app.post("/v1/knowledge/sources/{source_id}/import", status_code=201)
    async def kb_import(source_id: str, request: Request, filename: str = "upload", externalId: str | None = None, url: str | None = None) -> Any:
        """Add a PDF, HTML, Markdown or text file to a source (the request body is the file)."""
        if await kb.get_source(source_id) is None:
            return _err(404, "not_found", "Unknown source")
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > 11 * 1024 * 1024:
                return _err(413, "too_large", "The file is too large")
        try:
            ex = await extract_file(data, filename, request.headers.get("x-file-type", ""))
        except IngestError as e:
            return _err(400, "bad_request", str(e))
        ext = externalId or "file:" + (re.sub(r"[^A-Za-z0-9._-]", "_", filename.rsplit("/", 1)[-1])[:120] or "upload")
        try:
            r = await kb.upsert(source_id, ext, ex.title, url, ex.text, None)
        except KnowledgeError as e:
            return _err(400, "bad_request", str(e))
        if r.status != "unchanged":
            await record(request, "knowledge.import", f"{source_id}/{ext}", kind=ex.kind, size=len(data), status=r.status, chunks=r.document.chunks)
            if regression is not None:
                regression.trigger(f"document {source_id}/{ext} {r.status}")
        return {"status": r.status, "kind": ex.kind, "document": r.document.to_dict()}

    @app.post("/v1/knowledge/sources/{source_id}/crawl", status_code=202)
    async def kb_crawl(source_id: str, body: CrawlBody, request: Request) -> Any:
        """Read a site's public pages into this source in the background. Only hosts the operator allowed can be crawled."""
        if crawler is None:
            return _err(501, "not_configured", "Crawling is switched off: the operator must list the sites that may be crawled in NORTHCX_CRAWL_HOSTS")
        who: Identity = request.state.identity
        if not access.limiter.allow(f"crawl:{who.key_id or 'open'}", 5)[0]:
            return too_many(60, "crawl requests")
        cfg = CrawlConfig(body.url, body.max_pages, body.max_depth, body.delay_seconds, body.include_paths, body.exclude_paths, body.use_sitemap, body.prune)
        try:
            job = await crawler.start(source_id, cfg)
        except CrawlRefused as e:
            code = 404 if str(e) == "Unknown source" else 409 if "already running" in str(e) else 400
            return _err(code, "not_found" if code == 404 else "conflict" if code == 409 else "bad_request", str(e))
        await record(request, "knowledge.crawl.start", f"{source_id}", host=job.host, maxPages=cfg.max_pages, prune=cfg.prune)
        return job.to_dict()

    @app.post("/v1/knowledge/sources/{source_id}/schedule", status_code=201)
    async def kb_schedule(source_id: str, body: ScheduleBody, request: Request) -> Any:
        """Repeat a crawl every so many hours (at least one). It is checked exactly like a crawl started now, and again on every run."""
        if crawl_scheduler is None:
            return _err(501, "not_configured", "Crawling is switched off: the operator must list the sites that may be crawled in NORTHCX_CRAWL_HOSTS")
        who: Identity = request.state.identity
        cfg = CrawlConfig(body.url, body.max_pages, body.max_depth, body.delay_seconds, body.include_paths, body.exclude_paths, body.use_sitemap, body.prune)
        try:
            s = await crawl_scheduler.create(source_id, cfg, body.every_hours, who.name if hasattr(who, "name") else "unknown")
        except CrawlRefused as e:
            code = 404 if str(e) == "Unknown source" else 409 if "already has" in str(e) else 400
            return _err(code, "not_found" if code == 404 else "conflict" if code == 409 else "bad_request", str(e))
        await record(request, "knowledge.schedule.create", source_id, host=urlsplit(body.url).netloc.lower(), everyHours=body.every_hours)
        return s.to_dict()

    @app.get("/v1/knowledge/schedules")
    async def kb_schedules() -> Any:
        return {"enabled": crawl_scheduler is not None, "schedules": [s.to_dict() for s in await crawl_scheduler.repo.list()] if crawl_scheduler is not None else []}

    @app.delete("/v1/knowledge/schedules/{schedule_id}")
    async def kb_schedule_delete(schedule_id: str, request: Request) -> Any:
        if crawl_scheduler is None or not await crawl_scheduler.repo.delete(schedule_id):
            return _err(404, "not_found", "Unknown schedule")
        await record(request, "knowledge.schedule.delete", schedule_id)
        return {"deleted": True}

    @app.post("/v1/knowledge/schedules/{schedule_id}/enabled")
    async def kb_schedule_enabled(schedule_id: str, body: EnabledBody, request: Request) -> Any:
        if crawl_scheduler is None or not await crawl_scheduler.repo.set_enabled(schedule_id, body.enabled, time.time()):
            return _err(404, "not_found", "Unknown schedule")
        await record(request, "knowledge.schedule.enable" if body.enabled else "knowledge.schedule.pause", schedule_id)
        return {"enabled": body.enabled}

    @app.get("/v1/knowledge/crawls")
    async def kb_crawls() -> Any:
        return {"enabled": crawler is not None, "crawls": crawler.jobs_list() if crawler is not None else []}

    @app.get("/v1/knowledge/crawls/{job_id}")
    async def kb_crawl_status(job_id: str) -> Any:
        job = crawler.jobs.get(job_id) if crawler is not None else None
        return job.to_dict() if job is not None else _err(404, "not_found", "Unknown crawl")

    @app.get("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_get_document(source_id: str, external_id: str) -> Any:
        found = await kb.get_document(source_id, external_id)
        if found is None:
            return _err(404, "not_found", "Unknown document")
        doc, body, rebuilt = found
        src = await kb.get_source(source_id)
        return {**doc.to_dict(src.stale_after_days if src else None), "text": body, "textRebuilt": rebuilt}

    @app.put("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_put_document(source_id: str, external_id: str, body: DocumentBody, request: Request) -> Any:
        try:
            r = await kb.upsert(source_id, external_id, body.title, body.url, body.text, body.source_updated_at)
        except KnowledgeError as e:
            return _err(404 if str(e).startswith("Unknown source") else 400, "not_found" if str(e).startswith("Unknown source") else "bad_request", str(e))
        if r.status != "unchanged":
            await record(request, "knowledge.document.put", f"{source_id}/{external_id}", status=r.status, chunks=r.document.chunks)
            if regression is not None:
                regression.trigger(f"document {source_id}/{external_id} {r.status}")
        return {"status": r.status, "document": r.document.to_dict()}

    @app.delete("/v1/knowledge/sources/{source_id}/documents/{external_id:path}")
    async def kb_delete_document(source_id: str, external_id: str, request: Request) -> Any:
        if not await kb.delete(source_id, external_id):
            return _err(404, "not_found", "Unknown document")
        await record(request, "knowledge.document.delete", f"{source_id}/{external_id}")
        if regression is not None:
            regression.trigger(f"document {source_id}/{external_id} deleted")
        return {"deleted": True}

    @app.get("/v1/knowledge/documents")
    async def kb_documents(source: str | None = None, stale: bool = False, limit: int = 200) -> Any:
        rows = await kb.documents(source, stale, max(1, min(limit, 1000)))
        return {"documents": [d.to_dict(days) for d, days in rows]}

    @app.get("/v1/knowledge/search")
    async def kb_search(q: str, source: str | None = None, limit: int = 5) -> Any:
        found = await kb.search(q, max(1, min(limit, 20)), source)
        return {"passages": [{"documentId": p.document_id, "sourceId": p.source_id, "title": p.title, "url": p.url, "section": p.heading,
                              "text": p.text, "score": p.score, "updatedAt": p.updated_at, "stale": p.stale, "via": p.via} for p in found]}

    @app.get("/v1/knowledge/index")
    async def kb_index() -> Any:
        idx = getattr(kb, "indexer", None)
        return await idx.status() if idx is not None else {"enabled": False}

    @app.post("/v1/knowledge/index/rebuild", status_code=202)
    async def kb_index_rebuild(request: Request) -> Any:
        """Throws away every stored embedding and re-embeds all passages in the background (use after changing the embedding model)."""
        idx = getattr(kb, "indexer", None)
        if idx is None:
            return _err(501, "not_configured", "Meaning-based search is not configured: set NORTHCX_EMBEDDINGS_URL and NORTHCX_EMBEDDINGS_MODEL")
        n = await idx.rebuild()
        await record(request, "knowledge.index.rebuild", "knowledge", cleared=n)
        return {"cleared": n}

    @app.post("/v1/alerts/test")
    async def alert_test(request: Request) -> Any:
        """Sends a test alert through the real delivery path and reports whether the receiver accepted it."""
        if alerts is None:
            return _err(501, "not_configured", "Alerts are not configured on this server")
        e = await alerts.send_test()
        await record(request, "alert.test", "alerts", delivery=e["delivery"]["status"])
        return e

    @app.get("/v1/monitor/findings")
    async def monitor_findings(rule: str | None = None, severity: str | None = None, agentId: str | None = None,
                               sessionId: str | None = None, since: float | None = None, limit: int = 100) -> Any:
        items = await runtime.monitor.repo.list(rule=rule, severity=severity, agent_id=agentId, session_id=sessionId,
                                                since=since, limit=max(1, min(limit, 500)))
        return {"findings": [f.to_dict() for f in items]}

    @app.get("/v1/monitor/summary")
    async def monitor_summary(since: float | None = None) -> Any:
        counts = await runtime.monitor.repo.counts(since)
        return {"rules": sorted(runtime.monitor.rules), "counts": counts,
                "total": sum(n for by in counts.values() for n in by.values())}

    @app.get("/v1/traces")
    async def list_traces(sessionId: str | None = None, limit: int = 200) -> Any:
        items = await traces.summaries(sessionId, max(1, min(limit, 1000)))
        return {"traces": [{"id": t.id, "agentId": t.agent_id, "sessionId": t.session_id, "events": t.events,
                            "status": t.status, "startedAt": t.started_at, "tools": t.tools,
                            "agentVersion": t.agent_version, "environment": t.environment} for t in items]}

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

    @app.get("/v1/approvals")
    async def list_approvals(state: str | None = None) -> Any:
        return {"approvals": [a.__dict__ for a in await runtime.approvals.list(state)]}

    @app.post("/v1/approvals/{approval_id}/decision")
    async def decide(approval_id: str, body: DecisionBody, request: Request) -> Any:
        """Record the decision, run the action if approved, and continue the conversation. The customer receives the
        outcome through the outbox (and the webhook, if configured)."""
        try:
            res = await flow.resolve(agents, approval_id, body.approved, actor(request, body.by), body.note)
        except KeyError:
            return _err(404, "not_found", "Unknown approval")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        await record(request, "approval.decide", approval_id, tool=res.approval.tool, approved=body.approved,
                     state=res.approval.state, note=bool(body.note), follow_up=res.run.status if res.run else "none")
        out = dict(res.approval.__dict__)
        out["resume"] = ({"reply": res.run.reply, "status": res.run.status, "traceId": res.run.trace_id}
                         if res.run else {"error": res.error})
        if res.run and res.error:
            out["resume"]["error"] = res.error
        return out

    @app.post("/v1/approvals/expire")
    async def expire(body: ExpireBody, request: Request) -> Any:
        done = await flow.expire_stale(agents, body.older_than_seconds)
        await record(request, "approval.expire", "", older_than_seconds=body.older_than_seconds, approvals=[a.id for a in done])
        return {"expired": [a.id for a in done]}

    def handoff_json(h: Any, full: bool = False) -> dict[str, Any]:
        out = {"id": h.id, "sessionId": h.session_id, "traceId": h.trace_id, "agentId": h.agent_id, "customerId": h.customer_id,
               "trigger": h.trigger, "reason": h.reason, "topics": h.topics, "state": h.state, "createdAt": h.created_at,
               "resolvedBy": h.resolved_by, "resolvedAt": h.resolved_at, "note": h.note, "summary": h.package.get("summary"),
               "queue": h.queue, "afterHours": h.after_hours}
        if full:
            out["package"] = h.package
        return out

    @app.get("/v1/routing")
    async def routing_status() -> Any:
        """Queues, their hours and whether each is open right now."""
        return runtime.router.describe()

    @app.get("/v1/handoffs")
    async def list_handoffs(state: str | None = None, sessionId: str | None = None, limit: int = 200, queue: str | None = None) -> Any:
        items = await runtime.handoffs.list(state, sessionId, max(1, min(limit, 1000)), queue)
        return {"handoffs": [handoff_json(h) for h in items]}

    @app.get("/v1/handoffs/{handoff_id}/inbox")
    async def handoff_inbox(handoff_id: str) -> Any:
        """Where this hand-off has been sent (helpdesk reference, attempts, last error)."""
        if await runtime.handoffs.get(handoff_id) is None:
            return _err(404, "not_found", "Unknown handoff")
        events = await runtime.inbox.repo.for_handoff(handoff_id) if runtime.inbox is not None else []
        return {"configured": runtime.inbox is not None, "deliveries": [e.to_dict() for e in events]}

    @app.get("/v1/handoffs/{handoff_id}")
    async def get_handoff(handoff_id: str) -> Any:
        h = await runtime.handoffs.get(handoff_id)
        return handoff_json(h, full=True) if h else _err(404, "not_found", "Unknown handoff")

    @app.post("/v1/handoffs/{handoff_id}/resolve")
    async def resolve_handoff(handoff_id: str, body: ResolveBody, request: Request) -> Any:
        try:
            who = actor(request, body.by)
            done = await runtime.handoffs.resolve(handoff_id, who, body.note)
            if body.returnToAgent:  # the agent is told what happened, so it can carry on from where the person left off
                msgs = await runtime.store.load_messages(done.session_id)
                msgs.append({"role": "user", "content": return_note(who, runtime.secrets.redact_text(body.note or ""))})
                await runtime.store.save_messages(done.session_id, msgs)
            if runtime.inbox is not None:
                try:
                    await runtime.inbox.enqueue(done, "resolved")
                except Exception:
                    log.exception("could not queue the resolution for the inbox")
            await record(request, "handoff.resolve", handoff_id, trigger=done.trigger, note=bool(body.note), returned=body.returnToAgent)
            return handoff_json(done)
        except KeyError:
            return _err(404, "not_found", "Unknown handoff")
        except ValueError as e:
            return _err(409, "conflict", str(e))

    @app.post("/v1/handoffs/{handoff_id}/reply")
    async def handoff_reply(handoff_id: str, body: ReplyBody, request: Request) -> Any:
        """A person's message to the customer. It joins the conversation and reaches the customer through the outbox (web chat and apps poll or are
        pushed it); conversations on email and text are answered from the helpdesk instead."""
        h = await runtime.handoffs.get(handoff_id)
        if h is None:
            return _err(404, "not_found", "Unknown handoff")
        if h.state != "open":
            return _err(409, "conflict", "This hand-off is already resolved")
        who = actor(request, body.by)
        text = runtime.secrets.redact_text(body.text.strip())
        msgs = await runtime.store.load_messages(h.session_id)
        msgs.append({"role": "assistant", "content": f"{PERSON_PREFIX} {text}"})
        await runtime.store.save_messages(h.session_id, msgs)
        m = await runtime.outbox.publish(h.session_id, "person_reply", {"reply": text, "by": who, "handoffId": h.id})
        await record(request, "handoff.reply", handoff_id, length=len(text))
        return {"sent": True, "messageId": m.id}

    @app.post("/v1/handoffs/{handoff_id}/assist")
    async def handoff_assist(handoff_id: str, request: Request) -> Any:
        """Draft suggestions (reply, next steps, key facts, cautions) for the person handling this hand-off. Suggestions only: nothing is sent."""
        if runtime.assist is None:
            return _err(501, "not_configured", "Agent assist is switched off on this server")
        h = await runtime.handoffs.get(handoff_id)
        if h is None:
            return _err(404, "not_found", "Unknown handoff")
        who: Identity = request.state.identity
        if not access.limiter.allow(f"assist:{who.key_id or 'open'}", 20)[0]:
            return too_many(60, "assist requests")
        try:
            out = runtime.secrets.redact(await runtime.assist.suggest(runtime.secrets.redact(h.package)))
        except AssistError as e:
            return _err(422, "unusable_suggestions", str(e))
        except Exception:
            log.exception("assist failed")
            return _err(502, "model_unavailable", "The model could not be reached; try again")
        await runtime.handoffs.set_package_field(h.id, "assist", out)
        await record(request, "handoff.assist", handoff_id)
        return {"assist": out}

    def need_sim() -> SimulationService | JSONResponse:
        return simulations or _err(501, "not_configured", "Simulations are not configured on this server")

    def run_json(r: Any, full: bool = False) -> dict[str, Any]:
        out = {"id": r.id, "createdAt": r.created_at, "mode": r.mode, "source": r.source, "passed": r.passed,
               "counts": r.counts, "seconds": r.seconds, "meta": r.meta, "agentDigests": r.agent_digests}
        if full:
            out["results"] = r.results
        return out

    @app.get("/v1/simulations/scenarios")
    async def sim_scenarios() -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        files = {s.name for s in sim.scenarios}
        return {"modes": sim.modes, "managedAvailable": sim.managed is not None, "scenarios": [
            {"name": s.name, "agent": s.agent, "required": s.required, "description": s.description, "steps": len(s.turns), "tags": s.tags,
             "judge": s.judge is not None, "digest": s.digest(), "source": "file" if s.name in files else "managed", "editable": s.name not in files and sim.managed is not None}
            for s in await sim.all_scenarios()]}

    def scenario_input(body: ScenarioBody) -> tuple[dict[str, Any], Any] | JSONResponse:
        if (body.yaml is None) == (body.scenario is None):
            return _err(400, "bad_request", "Give exactly one of 'yaml' or 'scenario'")
        try:
            return parse_definition(body.yaml if body.yaml is not None else body.scenario)
        except ScenarioError as e:
            return _err(400, "invalid_scenario", str(e))

    async def need_require(request: Request, what: str) -> JSONResponse | None:
        """Required scenarios decide what may be released, so changing which ones are required needs the release permission."""
        who: Identity = request.state.identity
        if not who.can("scenarios:require"):
            await record(request, "auth.denied", f"{request.method} {request.url.path}", "denied", permission="scenarios:require")
            return _err(403, "forbidden", f"The '{who.role}' role cannot {what} a required scenario (needs scenarios:require)")
        return None

    @app.post("/v1/simulations/scenarios/validate")
    async def validate_scenario(body: ScenarioBody) -> Any:
        """Check a scenario without saving it."""
        parsed = scenario_input(body)
        if isinstance(parsed, JSONResponse):
            return {"valid": False, "problems": [json.loads(parsed.body)["error"]["message"]]}
        definition, sc = parsed
        return {"valid": True, "problems": [], "name": sc.name, "agent": sc.agent, "required": sc.required, "digest": sc.digest(), "steps": len(sc.turns)}

    @app.get("/v1/simulations/scenarios/{name}")
    async def get_scenario(name: str) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        sc = next((s for s in await sim.all_scenarios() if s.name == name), None)
        if sc is None:
            return _err(404, "not_found", "Unknown scenario")
        is_file = any(s.name == name for s in sim.scenarios)
        m = None if is_file or sim.managed is None else await sim.managed.get(name)
        definition = m.definition if m else json.loads(sc.model_dump_json(exclude={"source"}, exclude_defaults=True))
        return {"name": name, "source": "file" if is_file else "managed", "editable": m is not None, "required": sc.required, "digest": sc.digest(),
                "definition": definition, "yaml": yaml.safe_dump(definition, sort_keys=False, allow_unicode=True, width=100),
                "revision": m.revision if m else None, "updatedBy": m.updated_by if m else None, "updatedAt": m.updated_at if m else None}

    @app.post("/v1/simulations/scenarios", status_code=201)
    async def create_scenario(body: ScenarioBody, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        if sim.managed is None:
            return _err(501, "not_configured", "Saving scenarios is not configured on this server")
        parsed = scenario_input(body)
        if isinstance(parsed, JSONResponse):
            return parsed
        definition, sc = parsed
        if any(s.name == sc.name for s in await sim.all_scenarios()):
            return _err(409, "conflict", f"A scenario named '{sc.name}' already exists")
        if sc.required and (denied := await need_require(request, "create")) is not None:
            return denied
        m, _ = await sim.managed.put(sc, definition, actor(request, None))
        await record(request, "scenario.create", sc.name, agent=sc.agent, required=sc.required, digest=sc.digest()[:12])
        return JSONResponse({"name": m.name, "revision": m.revision, "digest": sc.digest(), "required": sc.required}, status_code=201)

    @app.put("/v1/simulations/scenarios/{name}")
    async def update_scenario(name: str, body: ScenarioBody, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        if sim.managed is None:
            return _err(501, "not_configured", "Saving scenarios is not configured on this server")
        if any(s.name == name for s in sim.scenarios):
            return _err(409, "conflict", "This scenario comes from a file and is changed there")
        old = await sim.managed.get(name)
        if old is None:
            return _err(404, "not_found", "Unknown scenario")
        parsed = scenario_input(body)
        if isinstance(parsed, JSONResponse):
            return parsed
        definition, sc = parsed
        if sc.name != name:
            return _err(400, "bad_request", "A scenario cannot be renamed; save it under the new name and delete the old one")
        if (old.required or sc.required) and (denied := await need_require(request, "change")) is not None:
            return denied
        m, _ = await sim.managed.put(sc, definition, actor(request, None))
        await record(request, "scenario.update", name, agent=sc.agent, required=sc.required, was_required=old.required, digest=sc.digest()[:12], revision=m.revision)
        return {"name": m.name, "revision": m.revision, "digest": sc.digest(), "required": sc.required}

    @app.delete("/v1/simulations/scenarios/{name}")
    async def delete_scenario(name: str, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        if sim.managed is None:
            return _err(501, "not_configured", "Saving scenarios is not configured on this server")
        if any(s.name == name for s in sim.scenarios):
            return _err(409, "conflict", "This scenario comes from a file and is removed there")
        old = await sim.managed.get(name)
        if old is None:
            return _err(404, "not_found", "Unknown scenario")
        if old.required and (denied := await need_require(request, "delete")) is not None:
            return denied
        await sim.managed.delete(name)
        await record(request, "scenario.delete", name, agent=old.agent, was_required=old.required)
        return {"deleted": True}

    @app.post("/v1/simulations/runs")
    async def sim_run(body: SimRunBody, request: Request) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        spec = None
        if body.version is not None:
            if releases is None or not body.agent:
                return _err(400, "bad_request", "Running a saved version needs 'agent' and a configured version store")
            v = await releases.versions.get_number(body.agent, body.version)
            if v is None:
                return _err(404, "not_found", f"Agent '{body.agent}' has no version {body.version}")
            spec = AgentSpec.model_validate(v.spec)
        try:
            run = await sim.run(body.mode, body.only, body.skip_judge, source="api",
                                meta={"version": body.version} if body.version else None, spec=spec)
        except Busy as e:
            return _err(409, "busy", str(e))
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "simulation.run", run.id, mode=run.mode, passed=run.passed, counts=run.counts,
                     agent=body.agent, version=body.version)
        return run_json(run)

    @app.get("/v1/simulations/runs")
    async def sim_runs(limit: int = 50) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        return {"runs": [run_json(r) for r in await sim.runs.list(max(1, min(limit, 200)))]}

    @app.get("/v1/simulations/runs/{run_id}")
    async def sim_run_detail(run_id: str) -> Any:
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        r = await sim.runs.get(run_id)
        return run_json(r, full=True) if r else _err(404, "not_found", "Unknown run")

    @app.get("/v1/simulations/gate")
    async def sim_gate(agent: str | None = None, version: int | None = None) -> Any:
        """Has each agent's current version passed every required scenario? (Used to gate releases.)"""
        sim = need_sim()
        if isinstance(sim, JSONResponse):
            return sim
        ids = [agent] if agent else sorted(sim.agent_digests)
        out = []
        for a in ids:
            if version is not None:
                v = await releases.versions.get_number(a, version) if releases else None
                if v is None:
                    return _err(404, "not_found", f"Agent '{a}' has no version {version}")
                g = await sim.gate_for(a, v.digest)
            else:
                g = await sim.gate(a)
            out.append({"agent": g.agent_id, "agentDigest": g.agent_digest, "satisfied": g.satisfied, "required": g.required,
                        "covered": g.covered, "reasons": g.reasons, "runIds": g.run_ids})
        return {"gates": out}

    # ---------------- email channel ----------------
    MAX_EMAIL_BYTES = 1_000_000

    @app.post("/v1/channels/email/inbound")
    async def email_inbound(request: Request) -> Any:
        """The company's mail system forwards each raw message here (Content-Type message/rfc822)."""
        if email is None:
            return _err(501, "not_configured", "The email channel is not configured (set NORTHCX_EMAIL_FROM and NORTHCX_SMTP_URL)")
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_EMAIL_BYTES:
            return _err(413, "too_large", "Message is too large")
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_EMAIL_BYTES:
                return _err(413, "too_large", "Message is too large")
        try:
            res = await email.receive(raw)
        except EmailParseError as e:
            return _err(400, "bad_message", str(e))
        except Exception:
            log.exception("email inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return {"status": res.status, "sessionId": res.session_id, "reason": res.reason, "traceId": res.trace_id,
                "handoffId": res.handoff_id}

    # ---------------- SMS ----------------
    @app.post("/channels/sms/twilio")
    async def sms_inbound(request: Request) -> Any:
        """Public webhook for the SMS provider. It is not behind an API key: every request must carry the provider's signature."""
        if sms is None:
            return _err(501, "not_configured", "The SMS channel is not configured")
        ip = request.client.host if request.client else "unknown"
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 65536:
                return _err(413, "too_large", "Request is too large")
        try:
            params = parse_form(raw)
        except ValueError:
            return _err(400, "bad_request", "Unreadable request")
        if not sms.authentic(params, request.headers.get("x-twilio-signature", "")):
            if limits and not access.limiter.allow(f"smsfail:{ip}", limits.auth_failures_per_minute)[0]:
                return too_many(60, "unsigned requests")  # only failures count, so real traffic is never throttled by this
            if access.limiter.allow(f"smslog:{ip}", 6)[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/channels/sms/twilio", outcome="denied", detail={"client": ip}))
            return _err(403, "forbidden", "Invalid signature")
        try:
            await sms.receive(params)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        except Exception:
            log.exception("sms inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return Response(content="<Response></Response>", media_type="text/xml")  # replies go out through the outbox

    # ---------------- WhatsApp ----------------
    @app.get("/channels/whatsapp/meta")
    async def whatsapp_verify(request: Request) -> Any:
        """One-time webhook check by Meta: echoes the challenge only when the shared verify token matches."""
        q = request.query_params
        if whatsapp is None:
            return _err(501, "not_configured", "The WhatsApp channel is not configured")
        challenge = q.get("hub.challenge", "")
        if q.get("hub.mode") != "subscribe" or not whatsapp.provider.valid_verify_token(q.get("hub.verify_token", "")) or not re.fullmatch(r"[0-9A-Za-z_.~-]{1,200}", challenge):
            return _err(403, "forbidden", "Verification failed")
        return Response(content=challenge, media_type="text/plain")

    @app.post("/channels/whatsapp/meta")
    async def whatsapp_inbound(request: Request) -> Any:
        """Public webhook for WhatsApp. Authenticated by the body signature, never by an API key."""
        if whatsapp is None:
            return _err(501, "not_configured", "The WhatsApp channel is not configured")
        ip = request.client.host if request.client else "unknown"
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 262144:
                return _err(413, "too_large", "Request is too large")
        if not whatsapp.authentic(raw, request.headers.get("x-hub-signature-256", "")):
            if limits and not access.limiter.allow(f"smsfail:{ip}", limits.auth_failures_per_minute)[0]:
                return too_many(60, "unsigned requests")
            if access.limiter.allow(f"smslog:{ip}", 6)[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/channels/whatsapp/meta", outcome="denied", detail={"client": ip}))
            return _err(403, "forbidden", "Invalid signature")
        try:
            await whatsapp.receive_body(raw)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        except Exception:
            log.exception("whatsapp inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return {"status": "ok"}

    # ---------------- Telegram ----------------
    @app.post("/v1/channels/whatsapp/templates/send")
    async def whatsapp_template(body: TemplateSendBody, request: Request) -> Any:
        """Send an approved WhatsApp template (for example to reach someone after the 24-hour window). Only to people who already messaged that number or are on the opt-in list."""
        if whatsapp is None:
            return _err(501, "not_configured", "The WhatsApp channel is not configured")
        who: Identity = request.state.identity
        if not access.limiter.allow(f"watemplate:{who.key_id or 'open'}", 60)[0]:
            return too_many(60, "template messages")
        try:
            mid = await whatsapp.send_template(body.phone_id, body.to, body.template, body.params)
        except TemplateRefused as e:
            return _err(403, "not_allowed", str(e))
        except Exception as e:
            from .channels.sms import PermanentSendError
            if isinstance(e, PermanentSendError):
                return _err(422, "refused_by_provider", str(e))
            log.exception("whatsapp template failed")
            return _err(502, "provider_unavailable", "WhatsApp could not be reached; try again")
        await record(request, "whatsapp.template", body.template, to=phone_hash(body.to)[:12])
        return {"sent": True, "messageId": mid}

    @app.post("/channels/telegram/webhook")
    async def telegram_inbound(request: Request) -> Any:
        """Public webhook for the Telegram bot. Authenticated by the secret token registered with setWebhook, never by an API key."""
        if telegram is None:
            return _err(501, "not_configured", "The Telegram channel is not configured")
        ip = request.client.host if request.client else "unknown"
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 262144:
                return _err(413, "too_large", "Request is too large")
        if not telegram.authentic(request.headers.get("x-telegram-bot-api-secret-token", "")):
            if limits and not access.limiter.allow(f"smsfail:{ip}", limits.auth_failures_per_minute)[0]:
                return too_many(60, "unsigned requests")
            if access.limiter.allow(f"smslog:{ip}", 6)[0]:
                await audit.append(AuditEntry(actor="unknown", role="none", action="auth.failed", target="/channels/telegram/webhook", outcome="denied", detail={"client": ip}))
            return _err(403, "forbidden", "Invalid secret")
        try:
            await telegram.receive_body(raw)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        except Exception:
            log.exception("telegram inbound failed")
            return _err(500, "internal", "Could not process the message; it can be delivered again")
        return {"status": "ok"}

    # ---------------- chat tokens ----------------
    @app.post("/v1/chat-tokens", status_code=201)
    async def mint_chat_token(body: TokenBody, request: Request) -> Any:
        """Called by the company's server (holding a channel key), never by the customer's browser. Returns a token that
        lets one browser talk in one conversation as one customer until it expires."""
        who: Identity = request.state.identity
        if access.signer is None:
            return _err(501, "not_configured", "Chat tokens are not configured: set NORTHCX_TOKEN_SECRET or NORTHCX_API_KEY")
        if not MIN_TTL <= body.ttl_seconds <= MAX_TTL:
            return _err(400, "bad_request", f"ttlSeconds must be between {MIN_TTL} and {MAX_TTL}")
        sid = body.session_id or f"web-{uuid.uuid4().hex}"
        token, claims = access.signer.mint(sid=sid, kid=who.key_id or "open", cid=body.customer_id, agent=body.agent, ttl=body.ttl_seconds)
        return JSONResponse({"token": token, "sessionId": sid, "customerId": body.customer_id, "agent": body.agent,
                             "expiresAt": claims.exp, "ttlSeconds": body.ttl_seconds}, status_code=201)

    # ---------------- identity, keys and audit ----------------
    @app.get("/v1/me")
    async def me(request: Request) -> Any:
        who: Identity = request.state.identity
        return {"name": who.name, "role": who.role, "openMode": who.open_mode, "keyId": who.key_id,
                "permissions": sorted(who.permissions), "serverVersion": __version__}

    @app.post("/v1/me/logout")
    async def logout(request: Request) -> Any:
        """End a single-sign-on session now. Other kinds of key are left alone (revoke those on the Access page)."""
        who: Identity = request.state.identity
        key = await access.keys.get(who.key_id) if who.key_id else None
        if key is None or key.created_by != SSO_CREATOR or not key.active():
            return {"revoked": False}
        await access.revoke(key.key_id, who.name)
        await record(request, "sso.logout", who.name)
        return {"revoked": True}

    # ---------------- single sign-on (outside /v1: the identity provider, not a key, vouches for the person) ----------------
    SSO_COOKIE = "northcx_sso"
    secure_cookie = bool(sso and sso.cfg.redirect_uri.startswith("https://"))

    @app.get("/auth/sso/config")
    async def sso_config() -> Any:
        return {"enabled": sso is not None, "loginUrl": "/auth/sso/login" if sso else None}

    async def sso_failed(request: Request, e: SsoError) -> RedirectResponse:
        ip = request.client.host if request.client else "unknown"
        await audit.append(AuditEntry(actor="unknown", role="none", action="sso.denied", target="login", outcome="denied", detail={"client": ip, "reason": e.detail[:200]}))
        resp = RedirectResponse(f"{sso.cfg.landing}?{urlencode({'error': str(e)})}", status_code=303)
        resp.delete_cookie(SSO_COOKIE, path="/")
        return resp

    @app.get("/auth/sso/login")
    async def sso_login(request: Request) -> Any:
        if sso is None:
            return _err(404, "not_found", "Single sign-on is not configured")
        ip = request.client.host if request.client else "unknown"
        if not access.limiter.allow(f"sso:{ip}", 20)[0]:
            return too_many(60, "sign-in attempts")
        try:
            url, cookie = await sso.begin()
        except SsoError as e:
            return await sso_failed(request, e)
        resp = RedirectResponse(url, status_code=303)
        resp.set_cookie(SSO_COOKIE, cookie, max_age=600, httponly=True, samesite="lax", secure=secure_cookie, path="/")
        return resp

    @app.get("/auth/sso/callback")
    async def sso_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> Any:
        if sso is None:
            return _err(404, "not_found", "Single sign-on is not configured")
        ip = request.client.host if request.client else "unknown"
        if not access.limiter.allow(f"sso:{ip}", 20)[0]:
            return too_many(60, "sign-in attempts")
        if error:
            return await sso_failed(request, SsoError("The identity provider did not complete the sign-in", f"provider error: {error[:60]}"))
        try:
            login = await sso.finish(code, state, request.cookies.get(SSO_COOKIE))
            key, token = await access.issue_session(login.email, login.role, sso.cfg.session_hours)
        except SsoError as e:
            return await sso_failed(request, e)
        await audit.append(AuditEntry(actor=login.email, role=login.role, action="sso.login", target=f"ncx_{key.key_id}", outcome="ok",
                                      detail={"subject": login.subject, "client": ip, "expiresAt": key.expires_at}))
        resp = RedirectResponse(f"{sso.cfg.landing}#token={token}", status_code=303)  # in the fragment, so it is never sent to a server or logged
        resp.delete_cookie(SSO_COOKIE, path="/")
        resp.headers["cache-control"] = "no-store"
        return resp

    def key_json(k: Any) -> dict[str, Any]:
        return {"id": k.key_id, "prefix": k.prefix, "name": k.name, "role": k.role, "createdBy": k.created_by,
                "createdAt": k.created_at, "expiresAt": k.expires_at, "revokedAt": k.revoked_at, "revokedBy": k.revoked_by,
                "lastUsedAt": k.last_used_at, "active": k.active()}

    @app.get("/v1/keys")
    async def list_keys() -> Any:
        return {"roles": {r: sorted(p) for r, p in ROLES.items()}, "keys": [key_json(k) for k in await access.keys.list()]}

    @app.post("/v1/keys", status_code=201)
    async def create_key(body: KeyBody, request: Request) -> Any:
        try:
            key, secret = await access.issue(body.name, body.role, actor(request, None), body.expires_in_days)
        except ValueError as e:
            return _err(400, "bad_request", str(e))
        await record(request, "key.create", key.prefix, name=key.name, role=key.role, expires=key.expires_at)
        return JSONResponse({**key_json(key), "key": secret}, status_code=201)  # the only time the secret is shown

    @app.post("/v1/keys/{key_id}/revoke")
    async def revoke_key(key_id: str, request: Request) -> Any:
        try:
            key = await access.revoke(key_id, actor(request, None))
        except KeyError:
            return _err(404, "not_found", "Unknown key")
        except ValueError as e:
            return _err(409, "conflict", str(e))
        await record(request, "key.revoke", key.prefix, name=key.name, role=key.role)
        return key_json(key)

    @app.get("/v1/audit")
    async def audit_log(limit: int = 100, before: int | None = None, actor_name: str | None = None, action: str | None = None) -> Any:
        rows = await audit.list(max(1, min(limit, 500)), before, actor_name, action)
        return {"entries": [{"id": e.id, "at": e.at, "actor": e.actor, "role": e.role, "keyId": e.key_id, "action": e.action,
                             "target": e.target, "outcome": e.outcome, "detail": e.detail} for e in rows]}

    @app.get("/v1/audit/verify")
    async def audit_verify() -> Any:
        v = await audit.verify()
        return {"ok": v.ok, "checked": v.checked, "brokenAt": v.broken_at, "reason": v.reason, "head": v.head}

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

    def need_rollouts() -> RolloutService | JSONResponse:
        return rollouts or _err(501, "not_configured", "Staged rollouts are not configured on this server")

    def rollout_error(e: Exception) -> JSONResponse:
        if isinstance(e, ValueError) and not isinstance(e, (Conflict, GateBlocked)):
            return _err(400, "bad_request", str(e))
        return rel_error(e)

    @app.post("/v1/agents/{agent_id}/rollouts", status_code=201)
    async def start_rollout(agent_id: str, body: RolloutBody, request: Request) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        if (denied := await need_env(request, body.environment, "releases:publish")) is not None:
            return denied
        try:
            r = await svc.start(agent_id, body.version, body.percent, actor(request, body.by), body.environment, body.note)
        except GateBlocked as e:
            await record(request, "rollout.start", f"{agent_id}@{body.version}", "blocked", reasons=e.reasons[:10], environment=body.environment)
            return rel_error(e)
        except (NotFound, Conflict, ValueError) as e:
            return rollout_error(e)
        await record(request, "rollout.start", f"{agent_id}@{r.candidate_number}", percent=r.percent, environment=r.environment, control=r.control_number)
        return rollout_json(r)

    @app.get("/v1/agents/{agent_id}/rollouts")
    async def list_rollouts(agent_id: str) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        return {"rollouts": [rollout_json(r) for r in await svc.repo.history(agent_id)]}

    async def rollout_for(svc: RolloutService, agent_id: str, rollout_id: str) -> Any:
        r = await svc.repo.get(rollout_id)
        return r if r is not None and r.agent_id == agent_id else None

    @app.put("/v1/agents/{agent_id}/rollouts/{rollout_id}/percent")
    async def rollout_percent(agent_id: str, rollout_id: str, body: PercentBody, request: Request) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        cur = await rollout_for(svc, agent_id, rollout_id)
        if cur is None:
            return _err(404, "not_found", "Unknown rollout")
        if (denied := await need_env(request, cur.environment, "releases:publish")) is not None:
            return denied
        try:
            r = await svc.set_percent(agent_id, rollout_id, body.percent)
        except (NotFound, Conflict, ValueError) as e:
            return rollout_error(e)
        await record(request, "rollout.percent", f"{agent_id}@{r.candidate_number}", percent=r.percent, environment=r.environment)
        return rollout_json(r)

    @app.post("/v1/agents/{agent_id}/rollouts/{rollout_id}/promote")
    async def rollout_promote(agent_id: str, rollout_id: str, request: Request, body: PromoteBody | None = None) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        cur = await rollout_for(svc, agent_id, rollout_id)
        if cur is None:
            return _err(404, "not_found", "Unknown rollout")
        if (denied := await need_env(request, cur.environment, "releases:publish")) is not None:
            return denied
        try:
            r = await svc.promote(agent_id, rollout_id, actor(request, body.by if body else None), body.note if body else None)
        except GateBlocked as e:
            await record(request, "rollout.promote", f"{agent_id}@{cur.candidate_number}", "blocked", reasons=e.reasons[:10], environment=cur.environment)
            return rel_error(e)
        except (NotFound, Conflict, ValueError) as e:
            return rollout_error(e)
        await record(request, "rollout.promote", f"{agent_id}@{r.candidate_number}", environment=r.environment, percent=r.percent)
        return rollout_json(r)

    @app.post("/v1/agents/{agent_id}/rollouts/{rollout_id}/abort")
    async def rollout_abort(agent_id: str, rollout_id: str, request: Request) -> Any:
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        cur = await rollout_for(svc, agent_id, rollout_id)
        if cur is None:
            return _err(404, "not_found", "Unknown rollout")
        if (denied := await need_env(request, cur.environment, "releases:rollback")) is not None:
            return denied
        try:
            r = await svc.abort(agent_id, rollout_id, actor(request, None))
        except (NotFound, Conflict) as e:
            return rel_error(e)
        await record(request, "rollout.abort", f"{agent_id}@{r.candidate_number}", environment=r.environment)
        return rollout_json(r)

    @app.get("/v1/agents/{agent_id}/rollouts/{rollout_id}/comparison")
    async def rollout_comparison(agent_id: str, rollout_id: str) -> Any:
        """Control and candidate measured the same way, over the conversations assigned to each."""
        svc = need_rollouts()
        if isinstance(svc, JSONResponse):
            return svc
        r = await rollout_for(svc, agent_id, rollout_id)
        if r is None:
            return _err(404, "not_found", "Unknown rollout")
        arms = await svc.repo.arm_sessions(r.id)
        end = r.ended_at or time.time()
        turns, handoffs, feedback = await insight._load(r.started_at, end + 1, agent_id, r.environment)
        revs = await review_repo.for_sessions(arms[CONTROL] + arms[CANDIDATE])
        return {"rollout": rollout_json(r), **compare_arms(arms, turns, handoffs, feedback, revs, r.started_at, end),
                "versions": {CONTROL: r.control_number, CANDIDATE: r.candidate_number}}

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
    deps = AppDeps(actor=actor, need_rel=need_rel, privacy=privacy, record=record, rel_error=rel_error, releases=releases, runtime=runtime, simulations=simulations, skills=skills, templates=templates, version_json=version_json)
    _templates_router.register(app, deps)
    _memory_router.register(app, deps)
    _privacy_router.register(app, deps)
    # [/routers]
    return app
