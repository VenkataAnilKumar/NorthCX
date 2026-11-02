import os
import sys

import uvicorn

from .db import PgApprovalStore, PgMemoryStore, PgTraceStore, create_engine, database_url_from_env, migrate
from .llm import AnthropicLLM
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
        print("Using Postgres storage.")
    else:
        store, traces, approvals = InMemoryStore(), TraceStore(os.environ.get("NORTHCX_TRACE_DIR")), None
        print("Using in-memory storage: state is lost on restart. Set NORTHCX_DATABASE_URL for Postgres.")
    if demo:
        from .demo import DemoLLM

        llm = DemoLLM()
    else:
        llm = AnthropicLLM()
    runtime = Runtime(llm, store, traces, approvals)
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
    app = create_app(runtime, traces, agents, os.environ.get("NORTHCX_API_KEY"))
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
