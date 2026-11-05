import os
import re
import sys
from northcx.channels.telegram import TelegramNotifier, TelegramProvider
from northcx.channels.whatsapp import WhatsAppNotifier, WhatsAppProvider
from northcx.channels.sms import SmsConfig, SmsNotifier, TwilioProvider, valid_number
from northcx.channels.email import EmailConfig, EmailNotifier, SmtpSender
from northcx.events import EVENTS, EventWebhook
from northcx.secrets import env_or_file
from types import SimpleNamespace


def build_notifiers(c: SimpleNamespace) -> None:
    """Outbound notification chain: webhook, email, SMS, status events, WhatsApp, Telegram."""
    email_repo = c.email_repo
    sms_repo = c.sms_repo
    sms_provider = sms_config = None
    notifier = None
    if os.environ.get("NORTHCX_WEBHOOK_URL"):
        secret = env_or_file("NORTHCX_WEBHOOK_SECRET")
        if not secret:
            sys.exit("NORTHCX_WEBHOOK_URL needs NORTHCX_WEBHOOK_SECRET (or NORTHCX_WEBHOOK_SECRET_FILE)")
        from northcx.notify import WebhookNotifier

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
        from northcx.notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, email_notifier) if n])
    sms_notifier = None
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
        from northcx.notify import CompositeNotifier

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
        from northcx.notify import CompositeNotifier

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
        from northcx.notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, WhatsAppNotifier(sms_repo, wa_provider, wa_config)) if n])
    tg_provider = tg_config = None
    if os.environ.get("NORTHCX_TELEGRAM_TOKEN") or os.environ.get("NORTHCX_TELEGRAM_TOKEN_FILE"):
        try:
            tg_provider = TelegramProvider(env_or_file("NORTHCX_TELEGRAM_TOKEN") or "", env_or_file("NORTHCX_TELEGRAM_SECRET") or "", base_url=os.environ.get("NORTHCX_TELEGRAM_API_URL") or "https://api.telegram.org")
        except ValueError as e:
            sys.exit(f"Configuration error: {e}")
        tg_config = SmsConfig(tg_provider.bot_id, os.environ.get("NORTHCX_TELEGRAM_AGENT", "support"), max_replies_per_number_per_hour=int(os.environ.get("NORTHCX_TELEGRAM_MAX_REPLIES_PER_HOUR", 20)),
                              max_chars=2000, help_text="Send your question and our assistant will help. Send /stop to unsubscribe.")
        from northcx.notify import CompositeNotifier

        notifier = CompositeNotifier(*[n for n in (notifier, TelegramNotifier(sms_repo, tg_provider, tg_config)) if n])
    c.email_config = email_config
    c.event_types = event_types
    c.notifier = notifier
    c.sms_config = sms_config
    c.sms_notifier = sms_notifier
    c.sms_provider = sms_provider
    c.tg_config = tg_config
    c.tg_provider = tg_provider
    c.wa_config = wa_config
    c.wa_optin = wa_optin
    c.wa_provider = wa_provider
    c.wa_templates = wa_templates
