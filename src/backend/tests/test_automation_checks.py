"""WP 5.4: a routine runs a live agent's scenarios and raises an alert when some fail (A10, A11)."""
import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.alerts import AlertManager
from northcx.automations import AutomationError, validate_definition
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService, load_scenarios
from northcx.spec import AgentSpec, BuildContext, load_specs
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, ReleaseService
from tests.test_automation_tools import ADM, KEY, finished, publish, routine

ROOT = Path(__file__).resolve().parents[1]
SPECS = {s.id: s for s in load_specs(ROOT / "examples")}
_broken = json.loads(SPECS["support"].canonical())
_broken["forced_handoff"] = [*_broken.get("forced_handoff", []), {"name": "orders", "patterns": ["order"]}]                       # every order question goes to a person
BROKEN = {**SPECS, "support": AgentSpec.model_validate(_broken)}

CHECK = {"id": "check", "kind": "simulate", "agent": "support"}
WHEN_FAILED = {"id": "failed", "kind": "branch", "when": "previous.failed > 0", "then": "continue", "else": "stop"}
ALERT = {"id": "tell", "kind": "alert", "severity": "critical", "text": "The live support agent fails its own scenarios."}


class Insights:
    async def overview(self, *a, **k):
        return {}


def world(specs):
    loop = asyncio.new_event_loop()
    r = registry()
    sim = SimulationService(load_scenarios(ROOT / "examples" / "scenarios"), lambda a, l: r.build(specs[a], BuildContext(llm=l)), InMemorySimRuns(), {},
                            spec_builder=lambda spec, llm: r.build(spec, BuildContext(llm=llm)))
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), r, specs, sim)
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    alerts = AlertManager(Insights(), rt.monitor.repo, [])
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc, simulations=sim, alerts=alerts)
    key = lambda n, rl: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, rl, "t"))[1]}  # noqa: E731
    return app, TestClient(app), key, loop, alerts


def findings(c):
    return c.get("/v1/monitor/findings?rule=alert:routine:watch-support", headers=ADM).json()["findings"]


def test_a_deliberately_broken_agent_raises_an_alert_that_names_the_failing_scenarios():
    app, c, key, loop, alerts = world(BROKEN)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("watch-support", [CHECK, WHEN_FAILED, ALERT]))
    run = loop.run_until_complete(app.state.automations.run("watch-support", "manual", "ann"))
    assert run.status == "succeeded", run.error
    result = json.loads(run.steps[0]["output"])
    assert result["failed"] > 0 and result["failedNames"] and result["total"] >= result["failed"] and result["mode"] == "scripted"
    assert run.steps[-1]["alerted"] == "critical"
    got = findings(c)
    assert len(got) == 1 and got[0]["severity"] == "critical"
    assert "The live support agent fails its own scenarios." in got[0]["detail"] and result["failedNames"][0] in got[0]["detail"] and "Watch Support" in got[0]["detail"]
    assert [e["rule"] for e in alerts.events] == ["routine:watch-support"]


def test_a_healthy_agent_raises_nothing():
    app, c, key, loop, alerts = world(SPECS)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("watch-support", [CHECK, WHEN_FAILED, ALERT]))
    run = loop.run_until_complete(app.state.automations.run("watch-support", "manual", "ann"))
    assert run.status == "succeeded" and json.loads(run.steps[0]["output"])["failed"] == 0
    assert [s["id"] for s in run.steps] == ["check", "failed"] and findings(c) == [] and alerts.events == []


def test_the_alert_is_the_fixed_wording_plus_scenario_names_and_the_check_is_recorded_as_a_routines_test_run():
    app, c, key, loop, alerts = world(BROKEN)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("watch-support", [CHECK, ALERT]))
    run = loop.run_until_complete(app.state.automations.run("watch-support", "manual", "ann"))
    names = json.loads(run.steps[0]["output"])["failedNames"][:5]
    assert findings(c)[0]["detail"] == f"Routine 'Watch Support': {ALERT['text']} Failing scenarios: {', '.join(names)}."
    runs = c.get("/v1/simulations/runs", headers=ADM).json()["runs"]
    assert any(r.get("source") == "automation" for r in runs)


@pytest.mark.parametrize("step,why", [
    ({"id": "a", "kind": "simulate"}, "name the agent"),
    ({"id": "a", "kind": "simulate", "agent": "support", "mode": "fast"}, "scripted .* or live"),
    ({"id": "a", "kind": "alert", "text": "hey"}, "5 to 200 characters"),
    ({"id": "a", "kind": "alert", "text": "Failing: {{previous.failedNames}}"}, "fixed wording"),
    ({"id": "a", "kind": "alert", "text": "Something is wrong here", "severity": "loud"}, "warning or critical"),
])
def test_a_bad_simulate_or_alert_step_is_refused_with_the_reason(step, why):
    with pytest.raises(AutomationError, match=why):
        validate_definition(routine("bad-check", [step]), set())


def test_a_routine_cannot_check_an_agent_that_has_nothing_live():
    app, c, key, loop, alerts = world(SPECS)
    ann = key("ann", "release_manager")
    assert c.post("/v1/automations", headers=ann, json={"definition": routine("watch-ghost", [{"id": "c", "kind": "simulate", "agent": "ghost"}])}).status_code == 201
    r = c.post("/v1/automations/watch-ghost/propose", headers=ann)
    assert r.status_code == 409 and "nothing is live for 'ghost'" in r.json()["error"]["message"]


def test_a_scheduled_routine_runs_on_its_schedule_and_alerts():
    app, c, key, loop, alerts = world(BROKEN)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("watch-support", [CHECK, WHEN_FAILED, ALERT], trigger={"type": "schedule", "everyHours": 1}))
    svc = app.state.automations

    async def go():
        assert await svc.tick(time.time() + 3601) == 1
        for t in list(svc._tasks):
            await t
    loop.run_until_complete(go())
    assert len(findings(c)) == 1


def test_a_live_check_stops_the_run_with_the_reason_when_no_real_model_is_set_up():
    app, c, key, loop, alerts = world(SPECS)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("watch-live", [{**CHECK, "mode": "live"}]))
    run = loop.run_until_complete(app.state.automations.run("watch-live", "manual", "ann"))
    assert run.status == "stopped" and "mode 'live' is not available" in run.error


def test_an_alert_raised_by_a_routine_is_in_the_audit_log():
    app, c, key, loop, alerts = world(BROKEN)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("watch-support", [CHECK, ALERT]))
    run = loop.run_until_complete(app.state.automations.run("watch-support", "manual", "ann"))
    entries = [e for e in c.get("/v1/audit?limit=60", headers=ADM).json()["entries"] if e["action"] == "automation.alert"]
    assert len(entries) == 1 and entries[0]["target"] == "watch-support" and entries[0]["detail"] == {"run": run.id, "step": "tell", "severity": "critical"}
