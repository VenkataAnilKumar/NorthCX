import os
import sys
from northcx.inbox import ChatwootInbox, InboxDispatcher, WebhookInbox
from northcx.trace_export import ExportService, LangfuseExporter, OtlpExporter, Redactor
from northcx.routing import RoutingError, load_router
from northcx.config import load_context_provider
from northcx.context import CachedContext, HttpContextProvider
from northcx.secrets import ConfigError, env_or_file
from types import SimpleNamespace


def build_integrations(c: SimpleNamespace) -> None:
    """Context provider, human-inbox connectors, trace exporters and the routing file."""
    export_repo = c.export_repo
    inbox_repo = c.inbox_repo
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
    c.context_source = context_source
    c.exports = exports
    c.inbox = inbox
    c.router = router
