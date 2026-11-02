"""Command line: python -m northcx.simulation SCENARIOS --registry module:function --specs DIR [--model scripted|demo|live]

Exits 1 if any required scenario fails, 2 on a usage or loading error, so it can gate a CI build."""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys

from ..spec import BuildContext, SpecError, load_specs
from .report import format_report
from .runner import SimConfig, SimulationRunner
from .scenario import ScenarioError, load_scenarios


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="northcx.simulation", description="Run scenario simulations.")
    p.add_argument("scenarios", help="a scenario file or a directory of them")
    p.add_argument("--specs", required=True, help="directory of agent spec files")
    p.add_argument("--registry", required=True, help="module:function returning the tool registry")
    p.add_argument("--model", choices=["scripted", "demo", "live"], default="scripted")
    p.add_argument("--judge-model", choices=["live"], help="grade judge checks with the live model")
    p.add_argument("--skip-judge", action="store_true", help="skip judge checks instead of failing them")
    p.add_argument("--only", help="run scenarios whose name contains this text")
    p.add_argument("--allow-side-effects", action="store_true",
                   help="DANGEROUS: execute write tools for real (only against sandboxes). By default they are simulated.")
    p.add_argument("--json", dest="json_out", help="write the full report as JSON to this path")
    p.add_argument("--record", action="store_true", help="store the run in the database (NORTHCX_DATABASE_URL)")
    p.add_argument("--source", default="cli", choices=["cli", "ci"], help="label stored with a recorded run")
    p.add_argument("--meta", action="append", default=[], metavar="KEY=VALUE", help="extra details to store (repeatable)")
    a = p.parse_args(argv)

    try:
        scenarios = load_scenarios(a.scenarios)
        mod, _, fn = a.registry.partition(":")
        registry = getattr(importlib.import_module(mod), fn)()
        specs = {s.id: s for s in load_specs(a.specs)}
    except (ScenarioError, SpecError, ImportError, AttributeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    meta = {}
    for item in a.meta:
        k, sep, v = item.partition("=")
        if not sep or not k:
            print(f"error: --meta needs KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        meta[k] = v
    db_url = None
    if a.record:
        from ..db import database_url_from_env, migrate

        db_url = database_url_from_env()
        if not db_url:
            print("error: --record needs NORTHCX_DATABASE_URL", file=sys.stderr)
            return 2
        migrate(db_url)
    if a.only:
        scenarios = [s for s in scenarios if a.only in s.name]
        if not scenarios:
            print(f"error: no scenario name contains {a.only!r}", file=sys.stderr)
            return 2

    def agent_factory(agent_id, llm):
        if agent_id not in specs:
            raise KeyError(f"no spec with id '{agent_id}' (have: {', '.join(sorted(specs))})")
        return registry.build(specs[agent_id], BuildContext(llm=llm))

    live = judge = None
    if a.model == "live" or a.judge_model == "live":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("error: live mode needs ANTHROPIC_API_KEY", file=sys.stderr)
            return 2
        from ..llm import AnthropicLLM

        live = AnthropicLLM()
        judge = live if a.judge_model == "live" else None
    digests = {i: s.digest() for i, s in specs.items()}
    suite = asyncio.run(SimulationRunner(agent_factory, SimConfig(a.model, live, judge, a.skip_judge, not a.allow_side_effects), digests).run_suite(scenarios))
    print(format_report(suite))
    if a.record:
        from ..db import PgSimRuns, create_engine
        from .store import run_from_suite

        async def record() -> str:
            engine = create_engine(db_url)
            try:
                return (await PgSimRuns(engine).add(run_from_suite(suite, a.source, meta))).id
            finally:
                await engine.dispose()

        print(f"recorded run {asyncio.run(record())}")
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump(suite.to_dict(), f, indent=2, default=str)
    return 0 if suite.passed else 1


if __name__ == "__main__":
    sys.exit(main())
