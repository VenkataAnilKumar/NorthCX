import os
import re
import sys
from pathlib import Path

import uvicorn

from .access import AccessControl, InMemoryKeys, LimitConfig
from . import __version__
from .assist import AssistService
from .crawler import Crawler, hosts_from as crawl_hosts_from
from .voice import InMemoryCalls, VoiceConfig
from .attachments import HttpScanner, InMemoryAttachments
from .sso import Sso, config_from_env as sso_config_from_env
from .tokens import TokenSigner, derive_secret
from .inbox import ChatwootInbox, InboxDispatcher, InMemoryInbox, WebhookInbox
from .trace_export import ExportService, InMemoryExports, LangfuseExporter, OtlpExporter, Redactor
from .alerts import AlertConfigError, AlertManager, WebhookAlerts, load_rules
from .reviews import InMemoryReviews
from .rollout import InMemoryRollouts, RolloutService
from .simulation.managed import InMemoryScenarios
from .insights import InMemoryTags, InMemoryFeedback, InMemoryInsightsSource, InsightsService
from .regression import RegressionRunner
from .connectors import ConnectorError, allowed_hosts_from, load_connectors
from .templates import LIBRARY, TemplateError, load_templates
from .skills import SkillError, load_skills
from .routing import RoutingError, load_router
from .config import load_context_provider, load_registry
from .context import CachedContext, HttpContextProvider
from .audit import InMemoryAudit
from .channels.telegram import TelegramChannel, TelegramNotifier, TelegramProvider
from .channels.whatsapp import WhatsAppChannel, WhatsAppNotifier, WhatsAppProvider
from .channels.sms import InMemorySmsRepo, SmsChannel, SmsConfig, SmsNotifier, TwilioProvider, valid_number
from .channels.email import EmailChannel, EmailConfig, EmailNotifier, InMemoryEmailRepo, SmtpSender
from .summarize import Compactor
from .reliability import ReliableLLM, UsageLedger
from .llm import DEFAULT_MODEL
from .memory import InMemoryMemories, memory_tools
from .residency import ResidencyError, build_report, parse_policy
from .crawl_schedule import CrawlScheduler, InMemorySchedules
from .transcribe import HttpTranscriber
from .events import EVENTS, EventFeed, EventWebhook
from .verification import InMemoryVerify, OtpService, VerifyConfig, verification_tools
from .embeddings import EmbeddingIndexer, HttpEmbedder, HybridKnowledge, parse_source_models
from .knowledge import InMemoryKnowledge, knowledge_tool
from .idempotency import InMemoryIdempotency
from .monitor import InMemoryMonitor, Monitor
from .db import (PgApprovalStore, PgAudit, PgEmailRepo, PgExports, PgFeedback, PgInsightsSource, PgAttachments, PgCalls, PgReviews, PgRollouts, PgScenarios, PgSessionRoutes, PgTags, PgHandoffs, PgIdempotency, PgInbox, PgKeys, PgKnowledge, PgSchedules, PgVerify, PgMemories, PgMemoryStore, PgMonitor, PgPrivacy, PgOutbox, PgSmsRepo, PgReleases, PgSimRuns, PgTraceStore,
                 PgVersions, create_engine, database_url_from_env, migrate)
from .llm import AnthropicLLM
from .outbox import Outbox
from .runtime import Runtime
from .secrets import ConfigError, SecretStore, env_or_file, normalise_environment
from .server import create_app
from .simulation import InMemorySimRuns, ScenarioError, SimulationService, load_scenarios
from .spec import BuildContext, SpecError, load_specs
from .store import InMemoryStore
from .trace import TraceStore
from .versions import InMemoryReleases, InMemoryVersions, LiveAgents, ReleaseService


def _has_keys(db_url: str, access: AccessControl) -> bool:
    """Check for keys with a short-lived connection, before the server's event loop starts."""
    import asyncio

    from sqlalchemy.pool import NullPool

    async def check() -> bool:
        engine = create_engine(db_url, poolclass=NullPool)
        try:
            return await AccessControl(PgKeys(engine), env_or_file("NORTHCX_API_KEY")).enabled()
        finally:
            await engine.dispose()

    return asyncio.run(check())


def main() -> None:
    normalise_environment()  # blank settings (as Docker Compose passes them) mean "not set"
    try:
        run()
    except ConfigError as e:
        sys.exit(f"Configuration error: {e}")


def run() -> None:
    demo = os.environ.get("NORTHCX_DEMO") == "1"
    anthropic_key = env_or_file("ANTHROPIC_API_KEY")
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key  # the SDK reads it from the environment
    if not demo and not anthropic_key:
        sys.exit("Set ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY_FILE) to run the server, or NORTHCX_DEMO=1 for the offline demo model.")
    import examples

    registry = lambda: load_registry(os.environ.get("NORTHCX_REGISTRY", "examples.support_agent:registry"))  # noqa: E731
    secrets = SecretStore.from_env()
    api_key = env_or_file("NORTHCX_API_KEY")

    examples_dir = Path(examples.__file__).parent
    if demo:
        from .demo import DemoLLM

        llm = DemoLLM()
    else:
        llm = AnthropicLLM()
        fallbacks = [m.strip() for m in os.environ.get("NORTHCX_MODEL_FALLBACKS", "").split(",") if m.strip()]
        llm = ReliableLLM(llm, ([DEFAULT_MODEL] + fallbacks) if fallbacks else [],
                          retries=int(os.environ.get("NORTHCX_MODEL_RETRIES", 2)),
                          timeout=float(os.environ.get("NORTHCX_MODEL_TIMEOUT", 60)) or None)

    db_url = database_url_from_env(env_or_file("NORTHCX_DATABASE_URL"))
    if db_url:
        migrate(db_url)  # apply pending migrations before serving
        engine = create_engine(db_url)
        store, traces, approvals = PgMemoryStore(engine), PgTraceStore(engine), PgApprovalStore(engine)
        outbox_repo, handoffs, sim_runs = PgOutbox(engine), PgHandoffs(engine), PgSimRuns(engine)
        versions_repo, releases_repo = PgVersions(engine), PgReleases(engine)
        keys_repo, audit_repo = PgKeys(engine), PgAudit(engine)
        email_repo = PgEmailRepo(engine)
        sms_repo = PgSmsRepo(engine)
        monitor_repo, idem_repo = PgMonitor(engine), PgIdempotency(engine)
        knowledge_repo = PgKnowledge(engine)
        privacy_backend = PgPrivacy(engine)
        export_repo = PgExports(engine)
        feedback_repo = PgFeedback(engine)
        tag_repo = PgTags(engine)
        review_repo = PgReviews(engine)
        rollout_repo = PgRollouts(engine)
        attachment_repo = PgAttachments(engine)
        call_repo = PgCalls(engine)
        scenario_repo = PgScenarios(engine)
        insights_source = PgInsightsSource(engine)
        inbox_repo = PgInbox(engine)
        memory_repo = PgMemories(engine)
        print("Using Postgres storage.")
    else:
        store, traces, approvals = InMemoryStore(), TraceStore(os.environ.get("NORTHCX_TRACE_DIR")), None
        outbox_repo, handoffs, sim_runs = None, None, InMemorySimRuns()
        versions_repo, releases_repo = InMemoryVersions(), InMemoryReleases()
        keys_repo, audit_repo = InMemoryKeys(), InMemoryAudit()
        email_repo = InMemoryEmailRepo()
        sms_repo = InMemorySmsRepo()
        monitor_repo, idem_repo = InMemoryMonitor(), InMemoryIdempotency()
        knowledge_repo = InMemoryKnowledge()
        privacy_backend = None  # the runtime builds the in-memory one
        export_repo = InMemoryExports()
        feedback_repo = InMemoryFeedback()
        tag_repo = InMemoryTags()
        review_repo = InMemoryReviews()
        rollout_repo = InMemoryRollouts()
        attachment_repo = InMemoryAttachments()
        call_repo = InMemoryCalls()
        scenario_repo = InMemoryScenarios()
        insights_source = None  # built over the runtime below
        inbox_repo = InMemoryInbox()
        memory_repo = InMemoryMemories()
        print("Using in-memory storage: state is lost on restart. Set NORTHCX_DATABASE_URL for Postgres.")

    notifier = None
    if os.environ.get("NORTHCX_WEBHOOK_URL"):
        secret = env_or_file("NORTHCX_WEBHOOK_SECRET")
        if not secret:
            sys.exit("NORTHCX_WEBHOOK_URL needs NORTHCX_WEBHOOK_SECRET (or NORTHCX_WEBHOOK_SECRET_FILE)")
        from .notify import WebhookNotifier

        notifier = WebhookNotifier(os.environ["NORTHCX_WEBHOOK_URL"], secret)
    email_config = email_notifier = None
    if os.environ.get("NORTHCX_EMAIL_FROM"):
        smtp_url = env_or_file("NORTHCX_SMTP_URL")
        if not smtp_url:
            sys.exit("NORTHCX_EMAIL_FROM needs NORTHCX_SMTP_URL (or NORTHCX_SMTP_URL_FILE)")
        email_config = EmailConfig(os.environ["NORTHCX_EMAIL_FROM"].strip(), os.environ.get("NORTHCX_EMAIL_AGENT", "support"),
                                   os.environ.get("NORTHCX_EMAIL_TRUST_AUTH_RESULTS") == "1",
                                   int(os.environ.get("NORTHCX_EMAIL_MAX_REPLIES_PER_HOUR", 6)),
                                   from_name=os.environ.get("NORTHCX_EMAIL_FROM_NAME", ""))
        try:
            email_notifier = EmailNotifier(email_repo, SmtpSender(smtp_url), email_config)
        except ValueError as e:
            sys.exit(f"Configuration error: {e}")
        from .notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, email_notifier) if n])
    sms_channel = sms_notifier = None
    if os.environ.get("NORTHCX_SMS_NUMBER"):
        token = env_or_file("NORTHCX_SMS_AUTH_TOKEN")
        sid_ = os.environ.get("NORTHCX_SMS_ACCOUNT_SID", "")
        url_ = os.environ.get("NORTHCX_SMS_WEBHOOK_URL", "")
        if not (token and sid_ and url_):
            sys.exit("NORTHCX_SMS_NUMBER needs NORTHCX_SMS_ACCOUNT_SID, NORTHCX_SMS_AUTH_TOKEN (or _FILE) and NORTHCX_SMS_WEBHOOK_URL")
        if not valid_number(os.environ["NORTHCX_SMS_NUMBER"]):
            sys.exit("NORTHCX_SMS_NUMBER must be in international format, for example +14155550100")
        sms_config = SmsConfig(os.environ["NORTHCX_SMS_NUMBER"], os.environ.get("NORTHCX_SMS_AGENT", "support"), webhook_url=url_,
                               max_replies_per_number_per_hour=int(os.environ.get("NORTHCX_SMS_MAX_REPLIES_PER_HOUR", 20)))
        sms_provider = TwilioProvider(sid_, token)
        sms_notifier = SmsNotifier(sms_repo, sms_provider, sms_config)
        from .notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, sms_notifier) if n])
    event_types = None
    if os.environ.get("NORTHCX_EVENTS_WEBHOOK_URL"):
        ev_secret = env_or_file("NORTHCX_EVENTS_WEBHOOK_SECRET")
        if not ev_secret or len(ev_secret) < 16:
            sys.exit("NORTHCX_EVENTS_WEBHOOK_URL needs NORTHCX_EVENTS_WEBHOOK_SECRET (or _FILE) of at least 16 characters; receivers use it to verify each call")
        wanted = [x.strip() for x in os.environ.get("NORTHCX_EVENTS", "").split(",") if x.strip()]
        if wanted and (set(wanted) - set(EVENTS)):
            sys.exit("NORTHCX_EVENTS names unknown event type(s): " + ", ".join(sorted(set(wanted) - set(EVENTS))) + ". Known: " + ", ".join(EVENTS))
        event_types = set(wanted) or set(EVENTS)
        try:
            ev_hook = EventWebhook(os.environ["NORTHCX_EVENTS_WEBHOOK_URL"], ev_secret, types=event_types)
        except Exception as e:
            sys.exit(f"Events: {e}")
        from .notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, ev_hook) if n])
        print(f"Status events are ON ({len(event_types)} types) and are sent to the events webhook.")
    wa_provider = wa_config = None
    wa_templates: dict[str, str] = {}
    wa_optin: set[str] = set()
    if os.environ.get("NORTHCX_WHATSAPP_PHONE_ID"):
        try:
            wa_provider = WhatsAppProvider(env_or_file("NORTHCX_WHATSAPP_TOKEN") or "", env_or_file("NORTHCX_WHATSAPP_APP_SECRET") or "",
                                           env_or_file("NORTHCX_WHATSAPP_VERIFY_TOKEN") or "", base_url=os.environ.get("NORTHCX_WHATSAPP_API_URL") or "https://graph.facebook.com/v21.0")
            ids = [x.strip() for x in os.environ["NORTHCX_WHATSAPP_PHONE_ID"].split(",") if x.strip()]
            if not ids or len(ids) > 10 or len(set(ids)) != len(ids) or not all(i.isdigit() for i in ids):
                raise ValueError("NORTHCX_WHATSAPP_PHONE_ID is the numeric phone number id from the WhatsApp business dashboard (several, comma separated, are allowed)")
            agents_by_id = dict(p_.split("=", 1) for p_ in os.environ.get("NORTHCX_WHATSAPP_AGENTS", "").replace(" ", "").split(",") if p_)
            if set(agents_by_id) - set(ids):
                raise ValueError("NORTHCX_WHATSAPP_AGENTS names a phone number id that is not in NORTHCX_WHATSAPP_PHONE_ID")
            wa_templates = dict(p_.split("=", 1) for p_ in os.environ.get("NORTHCX_WHATSAPP_TEMPLATES", "").replace(" ", "").split(",") if p_)
            if not all(re.fullmatch(r"[a-z0-9_]{1,100}", k) and re.fullmatch(r"[a-z]{2}(_[A-Z]{2})?", v) for k, v in wa_templates.items()):
                raise ValueError("NORTHCX_WHATSAPP_TEMPLATES must look like order_update=en_US,shipping_delay=de (approved template name = language code)")
            if os.environ.get("NORTHCX_WHATSAPP_OPTIN_FILE"):
                wa_optin = {ln.strip() for ln in open(os.environ["NORTHCX_WHATSAPP_OPTIN_FILE"], encoding="utf-8").read().splitlines() if ln.strip() and not ln.startswith("#")}
                if not all(valid_number(n) for n in wa_optin):
                    raise ValueError("NORTHCX_WHATSAPP_OPTIN_FILE must list one phone number per line in international format")
        except (ValueError, OSError) as e:
            sys.exit(f"Configuration error: {e}")
        wa_config = {i: SmsConfig(i, agents_by_id.get(i, os.environ.get("NORTHCX_WHATSAPP_AGENT", "support")),
                                  max_replies_per_number_per_hour=int(os.environ.get("NORTHCX_WHATSAPP_MAX_REPLIES_PER_HOUR", 20)), max_chars=2000,
                                  help_text="Send your question and our assistant will help. Reply STOP to unsubscribe.") for i in ids}
        from .notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, WhatsAppNotifier(sms_repo, wa_provider, wa_config)) if n])
    tg_provider = tg_config = None
    if os.environ.get("NORTHCX_TELEGRAM_TOKEN") or os.environ.get("NORTHCX_TELEGRAM_TOKEN_FILE"):
        try:
            tg_provider = TelegramProvider(env_or_file("NORTHCX_TELEGRAM_TOKEN") or "", env_or_file("NORTHCX_TELEGRAM_SECRET") or "", base_url=os.environ.get("NORTHCX_TELEGRAM_API_URL") or "https://api.telegram.org")
        except ValueError as e:
            sys.exit(f"Configuration error: {e}")
        tg_config = SmsConfig(tg_provider.bot_id, os.environ.get("NORTHCX_TELEGRAM_AGENT", "support"), max_replies_per_number_per_hour=int(os.environ.get("NORTHCX_TELEGRAM_MAX_REPLIES_PER_HOUR", 20)),
                              max_chars=2000, help_text="Send your question and our assistant will help. Send /stop to unsubscribe.")
        from .notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, TelegramNotifier(sms_repo, tg_provider, tg_config)) if n])
    context_source = None
    try:
        provider = None
        if os.environ.get("NORTHCX_CONTEXT_PROVIDER"):
            provider = load_context_provider(os.environ["NORTHCX_CONTEXT_PROVIDER"])
        elif os.environ.get("NORTHCX_CONTEXT_URL"):
            provider = HttpContextProvider(os.environ["NORTHCX_CONTEXT_URL"], env_or_file("NORTHCX_CONTEXT_SECRET") or "")
        if provider is not None:
            context_source = CachedContext(provider, float(os.environ.get("NORTHCX_CONTEXT_TTL_SECONDS", 300)),
                                           float(os.environ.get("NORTHCX_CONTEXT_TIMEOUT", 3)))
    except (ValueError, ConfigError) as e:
        sys.exit(f"Configuration error: {e}")
    inbox = None
    connectors = []
    try:
        if os.environ.get("NORTHCX_INBOX_WEBHOOK_URL"):
            connectors.append(WebhookInbox(os.environ["NORTHCX_INBOX_WEBHOOK_URL"], env_or_file("NORTHCX_INBOX_WEBHOOK_SECRET") or "",
                                           os.environ.get("NORTHCX_PUBLIC_CONSOLE_URL")))
        if os.environ.get("NORTHCX_CHATWOOT_URL"):
            connectors.append(ChatwootInbox(os.environ["NORTHCX_CHATWOOT_URL"], os.environ.get("NORTHCX_CHATWOOT_ACCOUNT_ID", ""),
                                            os.environ.get("NORTHCX_CHATWOOT_INBOX_ID", ""), env_or_file("NORTHCX_CHATWOOT_TOKEN") or ""))
    except ValueError as e:
        sys.exit(f"Configuration error: {e}")
    if connectors:
        inbox = InboxDispatcher(inbox_repo, connectors)
    exports = None
    exporters = []
    try:
        if os.environ.get("NORTHCX_LANGFUSE_URL"):
            exporters.append(LangfuseExporter(os.environ["NORTHCX_LANGFUSE_URL"], os.environ.get("NORTHCX_LANGFUSE_PUBLIC_KEY", ""),
                                              env_or_file("NORTHCX_LANGFUSE_SECRET_KEY") or ""))
        if os.environ.get("NORTHCX_OTLP_ENDPOINT"):
            exporters.append(OtlpExporter(os.environ["NORTHCX_OTLP_ENDPOINT"], OtlpExporter.parse_headers(env_or_file("NORTHCX_OTLP_HEADERS") or "")))
        if exporters:
            exports = ExportService(export_repo, exporters, Redactor(os.environ.get("NORTHCX_TRACE_EXPORT_CONTENT", "masked")),
                                    float(os.environ.get("NORTHCX_TRACE_EXPORT_SAMPLE", 1)), os.environ.get("NORTHCX_ENVIRONMENT", "production"))
    except ValueError as e:
        sys.exit(f"Configuration error: {e}")
    router = None
    if os.environ.get("NORTHCX_ROUTING_FILE"):
        try:
            router = load_router(os.environ["NORTHCX_ROUTING_FILE"])
        except RoutingError as e:
            sys.exit(f"Invalid routing file: {e}")
    runtime = Runtime(llm, store, traces, approvals, Outbox(outbox_repo, notifier), handoffs, secrets, monitor=Monitor(monitor_repo), privacy=privacy_backend, router=router, inbox=inbox, exports=exports, context=context_source,
                      memories=memory_repo if os.environ.get("NORTHCX_MEMORY", "1") != "0" else None,
                      compactor=(Compactor(llm, int(os.environ["NORTHCX_SUMMARIZE_AFTER_TOKENS"]), model=os.environ.get("NORTHCX_SUMMARY_MODEL") or None)
                                 if os.environ.get("NORTHCX_SUMMARIZE_AFTER_TOKENS") else None),
                      ledger=UsageLedger(int(os.environ["NORTHCX_DAILY_TOKEN_BUDGET"]) if os.environ.get("NORTHCX_DAILY_TOKEN_BUDGET") else None))
    if db_url:
        runtime.routes = PgSessionRoutes(engine)
    verify_service = None
    if os.environ.get("NORTHCX_VERIFY") == "1":
        vsecret = derive_secret(env_or_file("NORTHCX_TOKEN_SECRET"), api_key)
        if vsecret is None:
            sys.exit("NORTHCX_VERIFY=1 needs NORTHCX_API_KEY or NORTHCX_TOKEN_SECRET: codes are stored as keyed hashes, and the key must be the same on every server process")
        senders: dict[str, Any] = {}
        if email_config is not None:
            from email.message import EmailMessage as _Msg
            _smtp = SmtpSender(env_or_file("NORTHCX_SMTP_URL") or "")

            async def _send_email(to: str, body: str, _from: str = email_config.from_address) -> None:
                msg = _Msg()
                msg["From"], msg["To"], msg["Subject"] = _from, to, "Your verification code"
                msg.set_content(body)
                await _smtp.send(msg)
            senders["email"] = _send_email
        if sms_notifier is not None:
            async def _send_sms(to: str, body: str) -> None:
                await sms_provider.send(to, sms_config.from_number, body)
            senders["sms"] = _send_sms
        if not senders:
            sys.exit("NORTHCX_VERIFY=1 needs email (NORTHCX_EMAIL_FROM and NORTHCX_SMTP_URL) or SMS (NORTHCX_SMS_NUMBER ...) so a code can be delivered")
        verify_service = OtpService(PgVerify(engine) if db_url else InMemoryVerify(), senders, vsecret,
                                    VerifyConfig(verified_for=float(os.environ.get("NORTHCX_VERIFY_VALID_MINUTES", 30)) * 60))
        runtime.verification = verify_service
        print(f"One-time-code identity checks are ON (by {', '.join(sorted(senders))}); verified conversations carry the fact identity_verified=yes for {os.environ.get('NORTHCX_VERIFY_VALID_MINUTES', 30)} minutes.")
    assist_mode = os.environ.get("NORTHCX_ASSIST", "").strip() or "on-demand"
    if assist_mode not in ("off", "on-demand", "auto"):
        sys.exit("NORTHCX_ASSIST must be off, on-demand or auto")
    if assist_mode != "off":
        runtime.assist = AssistService(llm, os.environ.get("NORTHCX_ASSIST_MODEL") or None)
        runtime.assist_auto = assist_mode == "auto"

    # Agents and scenarios are files; the registry maps their tool names to code (the example registry for now).
    specs_dir = os.environ.get("NORTHCX_AGENTS_DIR") or str(examples_dir)
    scenarios_dir = os.environ.get("NORTHCX_SCENARIOS_DIR") or str(examples_dir / "scenarios")
    try:
        reg = registry()
        if os.environ.get("NORTHCX_CONNECTORS_DIR"):
            for tool in load_connectors(os.environ["NORTHCX_CONNECTORS_DIR"], allowed_hosts_from(os.environ.get("NORTHCX_CONNECTOR_HOSTS"))):
                reg.tool(tool)  # a tool name that already exists is refused
        if os.environ.get("NORTHCX_SKILLS_DIR"):
            for sk in load_skills(os.environ["NORTHCX_SKILLS_DIR"]):
                reg.skill(sk)
        if verify_service is not None:
            for t_ in verification_tools(verify_service):
                if t_.name not in reg.tool_names():
                    reg.tool(t_)
        if "search_knowledge" not in reg.tool_names():
            reg.tool(knowledge_tool(knowledge_repo))
        if runtime.memories is not None:
            for t in memory_tools(runtime.memories):
                if t.name not in reg.tool_names():
                    reg.tool(t)
        print(f"Tool secrets available: {', '.join(secrets.names()) or 'none'}")
        specs = {s.id: reg.pin_skills(s, overwrite=True) for s in load_specs(specs_dir)}  # spec files follow the skill files; the digest includes them
        baseline = {}
        for i, s in specs.items():  # agents defined by spec files; they serve until a version is released
            baseline[i] = reg.build(s, BuildContext(llm=llm))
            baseline[i].digest = s.digest()
        scenarios = load_scenarios(scenarios_dir) if Path(scenarios_dir).exists() else []
    except (SpecError, ScenarioError, SkillError, ConnectorError, TemplateError) as e:
        sys.exit(f"Invalid configuration: {e}")

    def factory(agent_id, sim_llm):
        return reg.build(specs[agent_id], BuildContext(llm=sim_llm))

    # Always available: scenarios can live in files, in the database (the Studio editor), or both.
    simulations = SimulationService(scenarios, factory, sim_runs, {i: s.digest() for i, s in specs.items()},
                                    live_llm=None if demo else llm, judge_llm=None if demo else llm,
                                    spec_builder=lambda spec, sim_llm: reg.build(spec, BuildContext(llm=sim_llm)), managed=scenario_repo)
    release_service = ReleaseService(versions_repo, releases_repo, reg, specs, simulations, strict_promotion=os.environ.get("NORTHCX_STRICT_PROMOTION") == "1")

    def build_live(spec):
        agent = reg.build(spec, BuildContext(llm=llm))
        agent.digest = spec.digest()
        return agent

    rollout_service = RolloutService(rollout_repo, release_service)
    agents = LiveAgents(baseline, release_service, build_live)

    regression = None
    rerun = os.environ.get("NORTHCX_RERUN_ON_KNOWLEDGE", "off")
    if rerun != "off":
        if rerun not in ("scripted", "live") or simulations is None:
            sys.exit("NORTHCX_RERUN_ON_KNOWLEDGE must be off, scripted or live, and needs scenarios (NORTHCX_SCENARIOS_DIR)")
        if rerun == "live" and demo:
            sys.exit("NORTHCX_RERUN_ON_KNOWLEDGE=live needs a real model (not the demo)")
        regression = RegressionRunner(simulations, monitor_repo, rerun, debounce=float(os.environ.get("NORTHCX_RERUN_DEBOUNCE_SECONDS", 60)))
    insights_service = InsightsService(insights_source or InMemoryInsightsSource(runtime, feedback_repo),
                                       float(os.environ["NORTHCX_PRICE_PER_MILLION_TOKENS"]) if os.environ.get("NORTHCX_PRICE_PER_MILLION_TOKENS") else None)
    alert_manager = None
    if os.environ.get("NORTHCX_ALERTS", "on") != "off":
        try:
            alert_hook = None
            if os.environ.get("NORTHCX_ALERT_WEBHOOK_URL"):
                alert_hook = WebhookAlerts(os.environ["NORTHCX_ALERT_WEBHOOK_URL"], env_or_file("NORTHCX_ALERT_WEBHOOK_SECRET") or "")
            alert_manager = AlertManager(insights_service, monitor_repo, load_rules(os.environ["NORTHCX_ALERT_RULES"]) if os.environ.get("NORTHCX_ALERT_RULES") else None, alert_hook)
        except (AlertConfigError, ValueError) as e:
            sys.exit(f"Configuration error: {e}")
    limits = None
    if os.environ.get("NORTHCX_RATE_LIMITS", "on") != "off":
        env = os.environ
        limits = LimitConfig(float(env.get("NORTHCX_RATE_LIMIT_PER_MINUTE", 600)),
                             float(env.get("NORTHCX_CHAT_PER_SESSION_PER_MINUTE", 30)),
                             float(env.get("NORTHCX_AUTH_FAILURES_PER_MINUTE", 20)),
                             float(env.get("NORTHCX_CHANNEL_RATE_LIMIT_PER_MINUTE", 6000)))
    token_secret = derive_secret(env_or_file("NORTHCX_TOKEN_SECRET"), api_key)
    if token_secret is None:
        import secrets as _secrets

        token_secret = _secrets.token_bytes(32)
        print("NOTE: chat tokens use a random signing secret (set NORTHCX_TOKEN_SECRET or NORTHCX_API_KEY): tokens stop "
              "working when the server restarts and are not valid across several servers.")
    access = AccessControl(keys_repo, api_key, limits, signer=TokenSigner(token_secret))
    import asyncio

    if asyncio.run(access.enabled()) if db_url is None else _has_keys(db_url, access):
        print("Authentication is ON (API keys required).")
    elif os.environ.get("NORTHCX_REQUIRE_AUTH") == "1":
        sys.exit("NORTHCX_REQUIRE_AUTH=1 but no API key exists. Set NORTHCX_API_KEY, or create one with "
                 "`python -m northcx.keys create --name <name> --role admin`.")
    else:
        print("WARNING: authentication is OFF. Anyone who can reach this server has admin access. "
              "Set NORTHCX_API_KEY (and NORTHCX_REQUIRE_AUTH=1) before exposing it.")

    sso = None
    try:
        sso_cfg = sso_config_from_env(os.environ, env_or_file("NORTHCX_SSO_CLIENT_SECRET") or "")
    except (ValueError, ConfigError) as e:
        sys.exit(f"Single sign-on: {e}")
    if sso_cfg is not None:
        if not (os.environ.get("NORTHCX_API_KEY") or db_url):
            sys.exit("Single sign-on needs API-key authentication: set NORTHCX_API_KEY (people sign in for a session key with a role)")
        sso = Sso(sso_cfg, token_secret)
        print(f"Single sign-on is ON ({sso_cfg.issuer}); sessions last {sso_cfg.session_hours:g} hours.")

    cors_origins = [o.strip().rstrip("/") for o in os.environ.get("NORTHCX_CORS_ORIGINS", "").split(",") if o.strip()]
    for o in cors_origins:
        if o == "*" or not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?|http://(localhost|127\.0\.0\.1)(:\d+)?", o):
            sys.exit(f"NORTHCX_CORS_ORIGINS: '{o}' must be an https origin such as https://www.example.com (no wildcards, no paths)")
    if os.environ.get("NORTHCX_EMBEDDINGS_URL"):
        try:
            embedder = HttpEmbedder(os.environ["NORTHCX_EMBEDDINGS_URL"], os.environ.get("NORTHCX_EMBEDDINGS_MODEL", ""), os.environ.get("NORTHCX_EMBEDDINGS_API_KEY") or None,
                                    int(os.environ["NORTHCX_EMBEDDINGS_DIMENSIONS"]) if os.environ.get("NORTHCX_EMBEDDINGS_DIMENSIONS") else None)
        except ValueError as e:
            sys.exit(str(e))
        try:
            src_models = parse_source_models(os.environ.get("NORTHCX_EMBEDDINGS_SOURCE_MODELS", ""))
            knowledge_repo = HybridKnowledge(knowledge_repo, embedder, source_models=src_models)
        except ValueError as e:
            sys.exit(str(e))
        knowledge_repo.indexer = EmbeddingIndexer(knowledge_repo.store, embedder, source_models=src_models)
        if hasattr(knowledge_repo.store, "ann_threshold") and os.environ.get("NORTHCX_ANN_THRESHOLD"):
            knowledge_repo.store.ann_threshold = int(os.environ["NORTHCX_ANN_THRESHOLD"])
        print(f"Meaning-based knowledge search is ON (model {embedder.model}); passages are sent to the embeddings endpoint you configured.")
    transcriber = None
    if os.environ.get("NORTHCX_TRANSCRIBE_URL"):
        try:
            transcriber = HttpTranscriber(os.environ["NORTHCX_TRANSCRIBE_URL"], os.environ.get("NORTHCX_TRANSCRIBE_MODEL", ""), env_or_file("NORTHCX_TRANSCRIBE_API_KEY") or None)
        except ValueError as e:
            sys.exit(str(e))
        print("Recording transcription is ON; uploaded recordings are sent to the transcription service you configured.")
    crawler = crawl_scheduler = None
    if os.environ.get("NORTHCX_CRAWL_HOSTS"):
        try:
            crawler = Crawler(knowledge_repo, crawl_hosts_from(os.environ["NORTHCX_CRAWL_HOSTS"]), os.environ.get("NORTHCX_CRAWL_ALLOW_PRIVATE") == "1")
        except ValueError as e:
            sys.exit(str(e))
        print(f"Knowledge crawling is ON for: {', '.join(sorted(crawler.allowed))}.")
        schedule_repo = PgSchedules(engine) if db_url else InMemorySchedules()
        crawl_scheduler = CrawlScheduler(crawler, schedule_repo)
    voice_cfg = None
    if os.environ.get("NORTHCX_VOICE_AGENT"):
        try:
            transfers = dict(p.split("=", 1) for p in os.environ.get("NORTHCX_VOICE_TRANSFER", "").replace(" ", "").split(",") if p)
            voice_cfg = VoiceConfig(os.environ["NORTHCX_VOICE_AGENT"], os.environ.get("NORTHCX_VOICE_BRAND") or "our support line", os.environ.get("NORTHCX_VOICE_LANGUAGE") or "en",
                                    os.environ.get("NORTHCX_VOICE_RECORDING") or "off", transfers, os.environ.get("NORTHCX_VOICE_TRUST_CALLER_ID") == "1")
        except ValueError as e:
            sys.exit(f"Voice: {e}")
        print(f"Voice calls are ON for agent '{voice_cfg.agent_id}' (recording: {voice_cfg.recording}).")
    attachment_scanner = None
    if os.environ.get("NORTHCX_ATTACHMENT_SCAN_URL"):
        try:
            attachment_scanner = HttpScanner(os.environ["NORTHCX_ATTACHMENT_SCAN_URL"])
        except ValueError as e:
            sys.exit(str(e))

    residency_policy = None
    if os.environ.get("NORTHCX_RESIDENCY_FILE"):
        try:
            residency_policy = parse_policy(open(os.environ["NORTHCX_RESIDENCY_FILE"], encoding="utf-8").read())
        except (OSError, ResidencyError) as e:
            sys.exit(f"Residency: {e}")
    residency = build_report(os.environ, residency_policy)
    if residency_policy is not None:
        for p_ in residency["problems"]:
            print(f"Residency {'ERROR' if residency_policy.strict else 'warning'}: {p_}")
        if residency["problems"] and residency_policy.strict:
            sys.exit("Residency is strict and some destinations are not in an allowed region; fix the residency file or the configuration above.")
        print(f"Data residency: deployment region '{residency_policy.region}', data may go to: {', '.join(residency_policy.allowed)}.")

    event_feed = EventFeed(runtime.outbox, event_types) if event_types is not None else None
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
                      email=EmailChannel(runtime, agents, email_repo, email_config) if email_config else None)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
