"""Everything the routers share. `create_app` builds one of these after its setup and hands it to every router.

The fields are the objects and helper functions the handlers close over, each with its real type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:  # types only: importing them for real would make this module depend on all of them
    from northcx.access import AccessControl, LimitConfig
    from northcx.alerts import AlertManager
    from northcx.approval_flow import ApprovalFlow
    from northcx.attachments import AttachmentRepo, Scanner
    from northcx.audit import AuditRepo
    from northcx.catalog import AgentProvider
    from northcx.channels.email import EmailChannel
    from northcx.channels.sms import SmsChannel
    from northcx.channels.telegram import TelegramChannel
    from northcx.channels.whatsapp import WhatsAppChannel
    from northcx.crawl_schedule import CrawlScheduler
    from northcx.crawler import Crawler
    from northcx.events import EventFeed
    from northcx.idempotency import IdempotencyStore
    from northcx.insights import FeedbackRepo, InsightsService, TagRepo
    from northcx.knowledge import KnowledgeStore
    from northcx.privacy import PrivacyService
    from northcx.regression import RegressionRunner
    from northcx.reviews import ReviewRepo
    from northcx.rollout import RolloutService
    from northcx.runtime import Runtime
    from northcx.simulation import SimulationService
    from northcx.sso import Sso
    from northcx.templates import Template
    from northcx.trace import TraceRepo
    from northcx.transcribe import HttpTranscriber
    from northcx.versions import ReleaseService
    from northcx.voice import CallRepo, VoiceConfig


@dataclass
class AppDeps:
    MAX_EMAIL_BYTES: int
    SSO_COOKIE: str
    access: AccessControl
    actor: Callable[[Request, str | None], str]
    agents: AgentProvider | dict[str, Any]
    alerts: AlertManager | None
    attachment_repo: AttachmentRepo
    attachment_scanner: Scanner | None
    audit: AuditRepo
    call_repo: CallRepo
    crawl_scheduler: CrawlScheduler | None
    crawler: Crawler | None
    email: EmailChannel | None
    events: EventFeed | None
    fb: FeedbackRepo
    flow: ApprovalFlow
    idem: IdempotencyStore
    insight: InsightsService
    kb: KnowledgeStore
    limits: LimitConfig | None
    need_env: Callable[[Request, str, str], Awaitable[JSONResponse | None]]
    need_rel: Callable[[], ReleaseService | JSONResponse]
    privacy: PrivacyService
    provider: AgentProvider
    record: Callable[..., Awaitable[None]]
    regression: RegressionRunner | None
    rel_error: Callable[[Exception], JSONResponse]
    releases: ReleaseService | None
    residency: dict | None
    review_repo: ReviewRepo
    rollouts: RolloutService | None
    runtime: Runtime
    secure_cookie: bool
    simulations: SimulationService | None
    skills: list[Any] | None
    sms: SmsChannel | None
    sso: Sso | None
    tag_repo: TagRepo
    telegram: TelegramChannel | None
    templates: dict[str, Template] | None
    too_many: Callable[[float, str], JSONResponse]
    traces: TraceRepo
    transcriber: HttpTranscriber | None
    version_json: Callable[..., dict[str, Any]]
    voice: VoiceConfig | None
    whatsapp: WhatsAppChannel | None
