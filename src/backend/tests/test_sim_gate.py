"""Stored simulation runs, the release gate, the service and its API."""
import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import registry
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import (Busy, InMemorySimRuns, SimConfig, SimRun, SimulationRunner, SimulationService, evaluate_gate,
                                load_scenarios, parse_scenario, run_from_suite)
from northcx.simulation.__main__ import main as cli
from northcx.spec import BuildContext, load_specs
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

ROOT = Path(__file__).resolve().parents[1]
SCEN = load_scenarios(ROOT / "examples" / "scenarios")
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}
DIGEST = SPECS["support"].digest()


def factory(agent_id, llm):
    return registry().build(SPECS[agent_id], BuildContext(llm=llm))


def required_names(agent="support"):
    return [s.name for s in SCEN if s.agent == agent and s.required]


def fake_run(mode="scripted", names=None, passed=True, digest=DIGEST, scenarios=SCEN, notes=None, created=1000.0):
    chosen = [s for s in scenarios if (names is None or s.name in names)]
    results = [{"name": s.name, "required": s.required, "passed": passed, "scenario_digest": s.digest(), "agent_digest": digest,
                "agent": s.agent, "notes": notes or []} for s in chosen]
    return SimRun(mode=mode, passed=passed, counts={"total": len(results)}, agent_digests={"support": digest}, results=results,
                  created_at=created)


# ---------------- digests ----------------
def test_scenario_digest_follows_content_not_location():
    a = parse_scenario({"name": "x", "agent": "a", "turns": [{"say": "hi"}]}, "one.yaml")
    b = parse_scenario({"name": "x", "agent": "a", "turns": [{"say": "hi"}]}, "two.yaml")
    c = parse_scenario({"name": "x", "agent": "a", "turns": [{"say": "hi!"}]}, "one.yaml")
    assert a.digest() == b.digest() != c.digest()


async def test_results_carry_the_digests_they_were_run_against():
    suite = await SimulationRunner(factory, SimConfig(skip_judge=True), {"support": DIGEST}).run_suite(SCEN[:2])
    assert suite.agent_digests == {"support": DIGEST}
    for r, s in zip(suite.results, SCEN[:2]):
        assert (r.agent, r.agent_digest, r.scenario_digest) == ("support", DIGEST, s.digest())
    run = run_from_suite(suite, "ci", {"commit": "abc"})
    assert run.passed and run.source == "ci" and run.meta == {"commit": "abc"} and run.results[0]["scenario_digest"]


# ---------------- gate rules ----------------
def test_gate_is_satisfied_when_every_required_scenario_passed_for_this_version():
    g = evaluate_gate("support", DIGEST, SCEN, [fake_run()])
    assert g.satisfied and g.covered == g.required == len(required_names()) and g.reasons == []


def test_gate_is_not_satisfied_for_a_different_agent_version_or_scenario_definition():
    assert not evaluate_gate("support", "other-digest", SCEN, [fake_run()]).satisfied
    changed = [s.model_copy(update={"turns": s.turns}) for s in SCEN]
    first = parse_scenario({**SCEN[0].model_dump(mode="json", exclude={"source"}), "description": "edited"}, "x")
    changed[0] = first
    g = evaluate_gate("support", DIGEST, changed, [fake_run()])
    assert g.covered == g.required - 1 and any("not run against this agent version" in r for r in g.reasons)


def test_newest_result_wins_in_both_directions():
    old_pass, new_fail = fake_run(created=1.0), fake_run(passed=False, created=2.0)
    assert not evaluate_gate("support", DIGEST, SCEN, [new_fail, old_pass]).satisfied  # newest first: a recent failure counts
    assert evaluate_gate("support", DIGEST, SCEN, [fake_run(created=3.0), new_fail]).satisfied
    g = evaluate_gate("support", DIGEST, SCEN, [new_fail])
    assert any("failed in run" in r for r in g.reasons)


def test_partial_runs_combine_and_unrelated_failures_do_not_matter():
    names = required_names()
    a, b = fake_run(names=names[:3]), fake_run(names=names[3:], created=2.0)
    assert evaluate_gate("support", DIGEST, SCEN, [b, a]).satisfied
    assert not evaluate_gate("support", DIGEST, SCEN, [a]).satisfied
    optional_failing = fake_run(names=["reply-is-polite-and-accurate"], passed=False, created=5.0)
    assert evaluate_gate("support", DIGEST, SCEN, [optional_failing, fake_run()]).satisfied


def test_demo_runs_prove_nothing_but_live_runs_count():
    assert not evaluate_gate("support", DIGEST, SCEN, [fake_run(mode="demo")]).satisfied
    assert evaluate_gate("support", DIGEST, SCEN, [fake_run(mode="live")]).satisfied


def test_a_skipped_check_does_not_count_as_covered():
    g = evaluate_gate("support", DIGEST, SCEN, [fake_run(notes=["judge check skipped"])])
    assert not g.satisfied and any("skipped" in r for r in g.reasons)


def test_gates_without_a_digest_or_required_scenarios_are_not_satisfied_by_default():
    assert not evaluate_gate("support", None, SCEN, [fake_run()]).satisfied
    g = evaluate_gate("ghost", "d", SCEN, [fake_run()])
    assert not g.satisfied and "no required scenarios" in g.reasons[0]
    assert evaluate_gate("ghost", "d", SCEN, [], allow_empty=True).satisfied


# ---------------- service ----------------
def service(runs=None, live=None, scenarios=SCEN):
    return SimulationService(scenarios, factory, runs or InMemorySimRuns(), {"support": DIGEST}, live_llm=live)


async def test_service_records_runs_and_the_gate_follows():
    svc = service()
    assert not (await svc.gate("support")).satisfied  # nothing run yet
    run = await svc.run("scripted", skip_judge=True)
    assert run.passed and run.counts["total"] == 18 and run.agent_digests == {"support": DIGEST}
    assert (await svc.runs.get(run.id)).id == run.id
    g = await svc.gate("support")
    assert g.satisfied and g.run_ids == [run.id]


async def test_service_validates_requests():
    svc = service()
    with pytest.raises(ValueError, match="not available"):
        await svc.run("live")
    with pytest.raises(ValueError, match="no scenario"):
        await svc.run("scripted", only="nothing-like-this")
    partial = await svc.run("scripted", only="legal-threat-always", skip_judge=True)
    assert partial.counts["total"] == 1
    assert not (await svc.gate("support")).satisfied  # one scenario is not enough


async def test_only_one_run_at_a_time():
    class Slow:
        async def complete(self, req):
            await asyncio.sleep(0.2)
            return text("hello")

    one = [s for s in SCEN if s.name == "prompt-injection-is-stopped-before-the-model"]  # no model call needed...
    live_scn = [parse_scenario({"name": "slow", "agent": "support", "turns": [{"say": "hello"}]})]
    svc = SimulationService(live_scn + one, factory, InMemorySimRuns(), {"support": DIGEST}, live_llm=Slow())
    first = asyncio.create_task(svc.run("live", only="slow"))
    await asyncio.sleep(0.05)
    with pytest.raises(Busy):
        await svc.run("live", only="slow")
    assert (await first).passed


# ---------------- API ----------------
def client(svc=None, api_key=None):
    traces = TraceStore()
    from examples.support_agent import support_agent
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), traces)
    return TestClient(create_app(rt, traces, {"support": support_agent()}, api_key, simulations=svc))


def test_simulation_api_end_to_end():
    c = client(service())
    scen = c.get("/v1/simulations/scenarios").json()
    assert len(scen["scenarios"]) == 18 and scen["modes"] == ["scripted", "demo"]
    assert any(s["name"] == "order-lookup" and s["required"] for s in scen["scenarios"])
    gate0 = c.get("/v1/simulations/gate").json()["gates"][0]
    assert gate0["satisfied"] is False and gate0["covered"] == 0 and gate0["agentDigest"] == DIGEST
    r = c.post("/v1/simulations/runs", json={"skipJudge": True})
    assert r.status_code == 200
    run = r.json()
    assert run["passed"] and run["counts"]["total"] == 18 and run["source"] == "api" and "results" not in run
    assert [x["id"] for x in c.get("/v1/simulations/runs").json()["runs"]] == [run["id"]]
    detail = c.get(f"/v1/simulations/runs/{run['id']}").json()
    assert len(detail["results"]) == 18 and all(x["passed"] for x in detail["results"])
    gate = c.get("/v1/simulations/gate?agent=support").json()["gates"][0]
    assert gate["satisfied"] and gate["covered"] == gate["required"] and gate["runIds"] == [run["id"]]


def test_simulation_api_errors():
    c = client(service())
    assert c.post("/v1/simulations/runs", json={"mode": "live"}).status_code == 400
    assert c.post("/v1/simulations/runs", json={"only": "zzz"}).status_code == 400
    assert c.get("/v1/simulations/runs/missing").status_code == 404
    assert c.post("/v1/simulations/runs", json={"mode": 5}).status_code == 400
    assert client(None).get("/v1/simulations/scenarios").status_code == 501
    assert client(None).post("/v1/simulations/runs", json={}).status_code == 501
    locked = client(service(), api_key="k")
    assert locked.get("/v1/simulations/gate").status_code == 401
    assert locked.get("/v1/simulations/gate", headers={"authorization": "Bearer k"}).status_code == 200


def test_a_failing_run_is_reported_and_blocks_the_gate():
    broken = [s.model_copy(update={"expect": s.expect.model_copy(update={"status": "escalated"})}) if s.name == "order-lookup" else s
              for s in SCEN]
    c = client(service(scenarios=broken))
    run = c.post("/v1/simulations/runs", json={"skipJudge": True}).json()
    assert not run["passed"] and run["counts"]["required_failed"] == 1
    gate = c.get("/v1/simulations/gate").json()["gates"][0]
    assert not gate["satisfied"] and any("order-lookup" in r for r in gate["reasons"])


# ---------------- repositories and command line ----------------
@pytest.fixture(params=["memory", "postgres"])
def run_repo(request):
    if request.param == "memory":
        return InMemorySimRuns()
    from northcx.db import PgSimRuns
    return PgSimRuns(request.getfixturevalue("engine"))


async def test_run_repository_contract(run_repo):
    a, b = fake_run(created=1.0), fake_run(created=2.0, passed=False)
    a.meta = {"commit": "héllo"}
    for r in (a, b):
        await run_repo.add(r)
    got = await run_repo.get(a.id)
    assert (got.mode, got.passed, got.meta, got.agent_digests) == ("scripted", True, {"commit": "héllo"}, {"support": DIGEST})
    assert got.results == a.results and got.counts == a.counts
    assert [r.id for r in await run_repo.list()] == [b.id, a.id]
    assert len(await run_repo.list(limit=1)) == 1 and await run_repo.get("missing") is None


async def test_the_gate_works_from_runs_stored_in_postgres(engine):
    from northcx.db import PgSimRuns
    svc = SimulationService(SCEN, factory, PgSimRuns(engine), {"support": DIGEST})
    run = await svc.run("scripted", skip_judge=True)
    again = SimulationService(SCEN, factory, PgSimRuns(engine), {"support": DIGEST})  # a "restarted" process
    g = await again.gate("support")
    assert g.satisfied and g.run_ids == [run.id]
    assert not (await SimulationService(SCEN, factory, PgSimRuns(engine), {"support": "changed"}).gate("support")).satisfied


ARGS = [str(ROOT / "examples" / "scenarios"), "--specs", str(ROOT / "examples"), "--registry", "examples.support_agent:registry", "--skip-judge"]


def test_cli_records_runs_for_the_gate(db_url, engine, monkeypatch, capsys):
    from northcx.db import PgSimRuns
    monkeypatch.setenv("NORTHCX_DATABASE_URL", db_url)
    assert cli(ARGS + ["--record", "--source", "ci", "--meta", "commit=abc123", "--meta", "branch=main"]) == 0
    assert "recorded run" in capsys.readouterr().out
    from sqlalchemy.pool import NullPool
    from northcx.db import create_engine

    async def fetch():
        eng = create_engine(db_url, poolclass=NullPool)
        try:
            return await PgSimRuns(eng).list()
        finally:
            await eng.dispose()

    runs = asyncio.run(fetch())
    assert len(runs) == 1 and runs[0].source == "ci" and runs[0].meta == {"commit": "abc123", "branch": "main"}
    assert evaluate_gate("support", DIGEST, SCEN, runs).satisfied  # the CLI used the same digests the server computes


def test_cli_record_errors(monkeypatch):
    monkeypatch.delenv("NORTHCX_DATABASE_URL", raising=False)
    assert cli(ARGS + ["--record"]) == 2
    assert cli(ARGS + ["--meta", "novalue"]) == 2
