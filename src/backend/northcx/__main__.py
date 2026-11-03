import os
import sys
from pathlib import Path

import uvicorn

from .access import AccessControl, InMemoryKeys, LimitConfig
from .tokens import TokenSigner, derive_secret
from .inbox import ChatwootInbox, InboxDispatcher, InMemoryInbox, WebhookInbox
from .trace_export import ExportService, InMemoryExports, LangfuseExporter, OtlpExporter, Redactor
from .regression import RegressionRunner
from .connectors import ConnectorError, allowed_hosts_from, load_connectors
from .templates import LIBRARY, TemplateError, load_templates
from .skills import SkillError, load_skills
from .routing import RoutingError, load_router
from .config import load_context_provider, load_registry
from .context import CachedContext, HttpContextProvider
from .audit import InMemoryAudit
from .channels.sms import InMemorySmsRepo, SmsChannel, SmsConfig, SmsNotifier, TwilioProvider, valid_number
from .channels.email import EmailChannel, EmailConfig, EmailNotifier, InMemoryEmailRepo, SmtpSender
from .summarize import Compactor
from .reliability import ReliableLLM, UsageLedger
from .llm import DEFAULT_MODEL
from .memory import InMemoryMemories, memory_tools
from .knowledge import InMemoryKnowledge, knowledge_tool
from .idempotency import InMemoryIdempotency
from .monitor import InMemoryMonitor, Monitor
from .db import (PgApprovalStore, PgAudit, PgEmailRepo, PgExports, PgHandoffs, PgIdempotency, PgInbox, PgKeys, PgKnowledge, PgMemories, PgMemoryStore, PgMonitor, PgPrivacy, PgOutbox, PgSmsRepo, PgReleases, PgSimRuns, PgTraceStore,
                 PgVersions, create_engine, database_url_from_env, migrate)
from .llm import AnthropicLLM
from .outbox import Outbox
from .runtime import Runtime
from .secrets import ConfigError, SecretStore, env_or_file
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

    simulations = None
    if scenarios:
        def factory(agent_id, sim_llm):
            return reg.build(specs[agent_id], BuildContext(llm=sim_llm))

        simulations = SimulationService(scenarios, factory, sim_runs, {i: s.digest() for i, s in specs.items()},
                                        live_llm=None if demo else llm, judge_llm=None if demo else llm,
                                        spec_builder=lambda spec, sim_llm: reg.build(spec, BuildContext(llm=sim_llm)))
    release_service = ReleaseService(versions_repo, releases_repo, reg, specs, simulations, strict_promotion=os.environ.get("NORTHCX_STRICT_PROMOTION") == "1")

    def build_live(spec):
        agent = reg.build(spec, BuildContext(llm=llm))
        agent.digest = spec.digest()
        return agent

    agents = LiveAgents(baseline, release_service, build_live)

    regression = None
    rerun = os.environ.get("NORTHCX_RERUN_ON_KNOWLEDGE", "off")
    if rerun != "off":
        if rerun not in ("scripted", "live") or simulations is None:
            sys.exit("NORTHCX_RERUN_ON_KNOWLEDGE must be off, scripted or live, and needs scenarios (NORTHCX_SCENARIOS_DIR)")
        if rerun == "live" and demo:
            sys.exit("NORTHCX_RERUN_ON_KNOWLEDGE=live needs a real model (not the demo)")
        regression = RegressionRunner(simulations, monitor_repo, rerun, debounce=float(os.environ.get("NORTHCX_RERUN_DEBOUNCE_SECONDS", 60)))
    limits = None
    if os.environ.get("NORTHCX_RATE_LIMITS", "on") != "off":
        env = os.environ
        limits = LimitConfig(float(env.get("NORTHCX_RATE_LIMIT_PER_MINUTE", 600)),
                             float(env.get("NORTHCX_CHAT_PER_SESSION_PER_MINUTE", 30)),
                             float(env.get("NORTHCX_AUTH_FAILURES_PER_MINUTE", 20)))
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

    ttl = os.environ.get("NORTHCX_APPROVAL_TTL_SECONDS")
    app = create_app(runtime, traces, agents, os.environ.get("NORTHCX_API_KEY"), float(ttl) if ttl else None, simulations, release_service,
                      access=access, audit=audit_repo, idempotency=idem_repo, knowledge=knowledge_repo,
                      regression=regression, skills=reg.skill_info(),
                      templates=load_templates(LIBRARY, *([os.environ["NORTHCX_TEMPLATES_DIR"]] if os.environ.get("NORTHCX_TEMPLATES_DIR") else [])),
                      sms=SmsChannel(runtime, agents, sms_repo, sms_provider, sms_config) if sms_notifier else None,
                      retention_days=float(os.environ["NORTHCX_RETENTION_DAYS"]) if os.environ.get("NORTHCX_RETENTION_DAYS") else None,
                      email=EmailChannel(runtime, agents, email_repo, email_config) if email_config else None)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
