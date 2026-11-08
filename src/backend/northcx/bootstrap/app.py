import os
from northcx import __version__
from northcx.templates import LIBRARY, load_templates
from northcx.channels.telegram import TelegramChannel
from northcx.channels.whatsapp import WhatsAppChannel
from northcx.channels.sms import SmsChannel
from northcx.channels.email import EmailChannel
from northcx.events import EventFeed
from northcx.server import create_app
from types import SimpleNamespace
from typing import Any


def build_app(c: SimpleNamespace) -> Any:
    """Assemble the web application."""
    access = c.access
    agents = c.agents
    alert_manager = c.alert_manager
    attachment_repo = c.attachment_repo
    attachment_scanner = c.attachment_scanner
    audit_repo = c.audit_repo
    call_repo = c.call_repo
    cors_origins = c.cors_origins
    crawl_scheduler = c.crawl_scheduler
    crawler = c.crawler
    email_config = c.email_config
    email_repo = c.email_repo
    event_types = c.event_types
    feedback_repo = c.feedback_repo
    idem_repo = c.idem_repo
    insights_service = c.insights_service
    knowledge_repo = c.knowledge_repo
    reg = c.reg
    regression = c.regression
    release_service = c.release_service
    residency = c.residency
    review_repo = c.review_repo
    rollout_service = c.rollout_service
    runtime = c.runtime
    simulations = c.simulations
    sms_config = c.sms_config
    sms_notifier = c.sms_notifier
    sms_provider = c.sms_provider
    sms_repo = c.sms_repo
    sso = c.sso
    tag_repo = c.tag_repo
    tg_config = c.tg_config
    tg_provider = c.tg_provider
    traces = c.traces
    transcriber = c.transcriber
    voice_cfg = c.voice_cfg
    wa_config = c.wa_config
    wa_optin = c.wa_optin
    wa_provider = c.wa_provider
    wa_templates = c.wa_templates
    event_feed = EventFeed(runtime.outbox, event_types) if event_types is not None else None
    if event_feed is not None:
        event_feed.webhook = c.events_webhook
    if event_feed is not None and alert_manager is not None:
        alert_manager.feed = event_feed
    print(f"NorthCX {__version__}")
    ttl = os.environ.get("NORTHCX_APPROVAL_TTL_SECONDS")
    app = create_app(runtime, traces, agents, os.environ.get("NORTHCX_API_KEY"), float(ttl) if ttl else None, simulations, release_service,
                      access=access, audit=audit_repo, idempotency=idem_repo, knowledge=knowledge_repo, crawler=crawler, crawl_scheduler=crawl_scheduler, transcriber=transcriber, events=event_feed,
                      regression=regression, residency=residency, telegram=TelegramChannel(runtime, agents, sms_repo, tg_provider, tg_config) if tg_provider else None, whatsapp=WhatsAppChannel(runtime, agents, sms_repo, wa_provider, wa_config, attachment_repo, attachment_scanner, wa_templates, wa_optin) if wa_provider else None, skills=reg.skill_info(), feedback=feedback_repo, tags=tag_repo, reviews=review_repo, rollouts=rollout_service, sso=sso, attachments=attachment_repo,
                      attachment_scanner=attachment_scanner, cors_origins=cors_origins, voice=voice_cfg, calls=call_repo,
                      insights=insights_service, alerts=alert_manager,
                      templates=load_templates(LIBRARY, *([os.environ["NORTHCX_TEMPLATES_DIR"]] if os.environ.get("NORTHCX_TEMPLATES_DIR") else [])),
                      sms=SmsChannel(runtime, agents, sms_repo, sms_provider, sms_config) if sms_notifier else None,
                      retention_days=float(os.environ["NORTHCX_RETENTION_DAYS"]) if os.environ.get("NORTHCX_RETENTION_DAYS") else None,
                      email=EmailChannel(runtime, agents, email_repo, email_config) if email_config else None,
                      role=c.role, leases=c.leases)
    return app
