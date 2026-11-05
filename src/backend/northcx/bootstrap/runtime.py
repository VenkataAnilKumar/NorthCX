import os
import sys
from northcx.assist import AssistService
from northcx.tokens import derive_secret
from northcx.channels.email import SmtpSender
from northcx.summarize import Compactor
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
    c.runtime = runtime
    c.verify_service = verify_service
