import os
import sys

import uvicorn

from .db import PgApprovalStore, PgHandoffs, PgMemoryStore, PgOutbox, PgTraceStore, create_engine, database_url_from_env, migrate
from .llm import AnthropicLLM
from .outbox import Outbox
from .runtime import Runtime
from .server import create_app
from .store import InMemoryStore
from .trace import TraceStore


def main() -> None:
    demo = os.environ.get("NORTHCX_DEMO") == "1"
    if not demo and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY to run the server (or NORTHCX_DEMO=1 for the offline demo model).")
    from examples.support_agent import support_agent

    db_url = database_url_from_env()
    if db_url:
        migrate(db_url)  # apply pending migrations before serving
        engine = create_engine(db_url)
        store, traces, approvals = PgMemoryStore(engine), PgTraceStore(engine), PgApprovalStore(engine)
        outbox_repo, handoffs = PgOutbox(engine), PgHandoffs(engine)
        print("Using Postgres storage.")
    else:
        store, traces, approvals = InMemoryStore(), TraceStore(os.environ.get("NORTHCX_TRACE_DIR")), None
        outbox_repo, handoffs = None, None
        print("Using in-memory storage: state is lost on restart. Set NORTHCX_DATABASE_URL for Postgres.")
    if demo:
        from .demo import DemoLLM

        llm = DemoLLM()
    else:
        llm = AnthropicLLM()
    notifier = None
    if os.environ.get("NORTHCX_WEBHOOK_URL"):
        secret = os.environ.get("NORTHCX_WEBHOOK_SECRET")
        if not secret:
            sys.exit("NORTHCX_WEBHOOK_URL needs NORTHCX_WEBHOOK_SECRET")
        from .notify import WebhookNotifier

        notifier = WebhookNotifier(os.environ["NORTHCX_WEBHOOK_URL"], secret)
    runtime = Runtime(llm, store, traces, approvals, Outbox(outbox_repo, notifier), handoffs)
    agents = {"support": support_agent()}
    specs_dir = os.environ.get("NORTHCX_AGENTS_DIR")
    if specs_dir:  # extra agents defined as specs, using the example tool registry
        from examples.support_agent import registry
        from .spec import BuildContext, SpecError, load_specs

        try:
            reg = registry()
            agents = {s.id: reg.build(s, BuildContext(llm=llm)) for s in load_specs(specs_dir)}
        except SpecError as e:
            sys.exit(f"Invalid agent spec in {specs_dir}: {e}")
    ttl = os.environ.get("NORTHCX_APPROVAL_TTL_SECONDS")
    app = create_app(runtime, traces, agents, os.environ.get("NORTHCX_API_KEY"), float(ttl) if ttl else None)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
