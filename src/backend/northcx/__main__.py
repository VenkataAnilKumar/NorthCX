import os
import sys
from pathlib import Path

import uvicorn

from .db import (PgApprovalStore, PgHandoffs, PgMemoryStore, PgOutbox, PgReleases, PgSimRuns, PgTraceStore, PgVersions,
                 create_engine, database_url_from_env, migrate)
from .llm import AnthropicLLM
from .outbox import Outbox
from .runtime import Runtime
from .server import create_app
from .simulation import InMemorySimRuns, ScenarioError, SimulationService, load_scenarios
from .spec import BuildContext, SpecError, load_specs
from .store import InMemoryStore
from .trace import TraceStore
from .versions import InMemoryReleases, InMemoryVersions, LiveAgents, ReleaseService


def main() -> None:
    demo = os.environ.get("NORTHCX_DEMO") == "1"
    if not demo and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY to run the server (or NORTHCX_DEMO=1 for the offline demo model).")
    import examples
    from examples.support_agent import registry

    examples_dir = Path(examples.__file__).parent
    if demo:
        from .demo import DemoLLM

        llm = DemoLLM()
    else:
        llm = AnthropicLLM()

    db_url = database_url_from_env()
    if db_url:
        migrate(db_url)  # apply pending migrations before serving
        engine = create_engine(db_url)
        store, traces, approvals = PgMemoryStore(engine), PgTraceStore(engine), PgApprovalStore(engine)
        outbox_repo, handoffs, sim_runs = PgOutbox(engine), PgHandoffs(engine), PgSimRuns(engine)
        versions_repo, releases_repo = PgVersions(engine), PgReleases(engine)
        print("Using Postgres storage.")
    else:
        store, traces, approvals = InMemoryStore(), TraceStore(os.environ.get("NORTHCX_TRACE_DIR")), None
        outbox_repo, handoffs, sim_runs = None, None, InMemorySimRuns()
        versions_repo, releases_repo = InMemoryVersions(), InMemoryReleases()
        print("Using in-memory storage: state is lost on restart. Set NORTHCX_DATABASE_URL for Postgres.")

    notifier = None
    if os.environ.get("NORTHCX_WEBHOOK_URL"):
        secret = os.environ.get("NORTHCX_WEBHOOK_SECRET")
        if not secret:
            sys.exit("NORTHCX_WEBHOOK_URL needs NORTHCX_WEBHOOK_SECRET")
        from .notify import WebhookNotifier

        notifier = WebhookNotifier(os.environ["NORTHCX_WEBHOOK_URL"], secret)
    runtime = Runtime(llm, store, traces, approvals, Outbox(outbox_repo, notifier), handoffs)

    # Agents and scenarios are files; the registry maps their tool names to code (the example registry for now).
    specs_dir = os.environ.get("NORTHCX_AGENTS_DIR") or str(examples_dir)
    scenarios_dir = os.environ.get("NORTHCX_SCENARIOS_DIR") or str(examples_dir / "scenarios")
    try:
        reg = registry()
        specs = {s.id: s for s in load_specs(specs_dir)}
        baseline = {}
        for i, s in specs.items():  # agents defined by spec files; they serve until a version is released
            baseline[i] = reg.build(s, BuildContext(llm=llm))
            baseline[i].digest = s.digest()
        scenarios = load_scenarios(scenarios_dir) if Path(scenarios_dir).exists() else []
    except (SpecError, ScenarioError) as e:
        sys.exit(f"Invalid configuration: {e}")

    simulations = None
    if scenarios:
        def factory(agent_id, sim_llm):
            return reg.build(specs[agent_id], BuildContext(llm=sim_llm))

        simulations = SimulationService(scenarios, factory, sim_runs, {i: s.digest() for i, s in specs.items()},
                                        live_llm=None if demo else llm, judge_llm=None if demo else llm,
                                        spec_builder=lambda spec, sim_llm: reg.build(spec, BuildContext(llm=sim_llm)))
    release_service = ReleaseService(versions_repo, releases_repo, reg, specs, simulations)

    def build_live(spec):
        agent = reg.build(spec, BuildContext(llm=llm))
        agent.digest = spec.digest()
        return agent

    agents = LiveAgents(baseline, release_service, build_live)

    ttl = os.environ.get("NORTHCX_APPROVAL_TTL_SECONDS")
    app = create_app(runtime, traces, agents, os.environ.get("NORTHCX_API_KEY"), float(ttl) if ttl else None, simulations, release_service)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
