import os
import sys
from northcx.assist import AssistService
from northcx.tokens import derive_secret
from northcx.channels.email import SmtpSender
from northcx.summarize import Compactor
from northcx.api.background import ROLES
from northcx.db import PgLeases, PgUsageLedger
from northcx.providers.budget import check_money_budget
from northcx.reliability import UsageLedger
from northcx.verification import InMemoryVerify, OtpService, VerifyConfig
from northcx.monitor import Monitor
from northcx.db import PgSessionRoutes, PgVerify
from northcx.outbox import Outbox
from northcx.runtime import Runtime
from northcx.secrets import env_or_file
from types import SimpleNamespace
from typing import Any


def build_runtime(c: SimpleNamespace) -> None:
    """The runtime, one-time-code verification and the assist service."""
    role = os.environ.get("NORTHCX_ROLE", "all").strip() or "all"
    if role not in ROLES:
        sys.exit("NORTHCX_ROLE must be all, api or worker")
    if role != "all" and not c.db_url:
        sys.exit(f"NORTHCX_ROLE={role} needs NORTHCX_DATABASE_URL: separate processes can only share work through the database")
    limits_backend = os.environ.get("NORTHCX_LIMITS_BACKEND", "memory").strip() or "memory"
    if limits_backend not in ("memory", "postgres"):
        sys.exit("NORTHCX_LIMITS_BACKEND must be memory or postgres")
    if limits_backend == "postgres" and not c.db_url:
        sys.exit("NORTHCX_LIMITS_BACKEND=postgres needs NORTHCX_DATABASE_URL: the counters live in the database")
    c.limits_backend = limits_backend
    if role != "all" and limits_backend != "postgres":
        print("NOTE: with separate API and worker processes also set NORTHCX_LIMITS_BACKEND=postgres, or each process keeps its own rate limits and token budget.")
    c.role = role
    c.leases = PgLeases(c.engine) if c.db_url else None
    if role != "all":
        print(f"Process role: {role} ({'serves requests only; background jobs run in the worker processes' if role == 'api' else 'runs the background jobs; do not send it customer traffic'}).")
    api_key = c.api_key
    approvals = c.approvals
    context_source = c.context_source
    db_url = c.db_url
    email_config = c.email_config
    engine = c.engine
    exports = c.exports
    handoffs = c.handoffs
    inbox = c.inbox
    llm = c.llm
    memory_repo = c.memory_repo
    monitor_repo = c.monitor_repo
    notifier = c.notifier
    outbox_repo = c.outbox_repo
    privacy_backend = c.privacy_backend
    router = c.router
    secrets = c.secrets
    sms_config = c.sms_config
    sms_notifier = c.sms_notifier
    sms_provider = c.sms_provider
    store = c.store
    traces = c.traces
    money_limit, currency = None, os.environ.get("NORTHCX_BUDGET_CURRENCY", "USD").strip().upper() or "USD"
    if os.environ.get("NORTHCX_DAILY_BUDGET", "").strip():
        try:
            money_limit = float(os.environ["NORTHCX_DAILY_BUDGET"])
            if money_limit <= 0:
                raise ValueError
        except ValueError:
            sys.exit("NORTHCX_DAILY_BUDGET must be a positive number (an amount in NORTHCX_BUDGET_CURRENCY per UTC day)")
        providers = getattr(c, "providers", None)
        if providers is None:
            sys.exit("NORTHCX_DAILY_BUDGET needs real model providers with prices; it cannot be used with the demo model")
        try:
            check_money_budget(providers, currency)
        except ValueError as e:
            sys.exit(f"NORTHCX_DAILY_BUDGET: {e}")
    runtime = Runtime(llm, store, traces, approvals, Outbox(outbox_repo, notifier), handoffs, secrets, monitor=Monitor(monitor_repo), privacy=privacy_backend, router=router, inbox=inbox, exports=exports, context=context_source,
                      memories=memory_repo if os.environ.get("NORTHCX_MEMORY", "1") != "0" else None,
                      compactor=(Compactor(llm, int(os.environ["NORTHCX_SUMMARIZE_AFTER_TOKENS"]), model=os.environ.get("NORTHCX_SUMMARY_MODEL") or None)
                                 if os.environ.get("NORTHCX_SUMMARIZE_AFTER_TOKENS") else None),
                      ledger=(PgUsageLedger if limits_backend == "postgres" else UsageLedger)(*(([engine] if limits_backend == "postgres" else [])
                              + [int(os.environ["NORTHCX_DAILY_TOKEN_BUDGET"]) if os.environ.get("NORTHCX_DAILY_TOKEN_BUDGET") else None,
                                 money_limit, currency])))
    from northcx.providers.qualification import Qualifications
    from northcx.db import PgQualifications
    runtime.qualifications = Qualifications(PgQualifications(c.engine) if c.db_url else None)
    if getattr(llm, "selector", None) is not None:
        llm.selector.qualifier = runtime.qualifications
    if money_limit is not None and c.providers is not None:
        runtime.pricing = c.providers.price_for
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
    c.runtime = runtime
    c.verify_service = verify_service
