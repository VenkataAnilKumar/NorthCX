"""The Builder's improvement loop: investigate, propose, test next to the live version, and hand to a reviewer as a draft that is never released from here."""
import asyncio
import json

import yaml
from fastapi.testclient import TestClient

from examples.support_agent import registry, support_agent
from northcx.access import AccessControl
from northcx.improve import instruction_from, run_pair
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.simulation import InMemorySimRuns, SimulationService
from northcx.spec import AgentSpec
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from northcx.versions import InMemoryReleases, InMemoryVersions, Release, ReleaseService

KEY = "boot" * 10
ADM = {"authorization": f"Bearer {KEY}"}
SPEC = AgentSpec(id="acme", instructions="You help Acme customers with orders. Look orders up first. Hand over legal matters.", tools=["lookup_order"], input_guardrails=["prompt_injection"])


def revised():
    return json.dumps({"instructions": SPEC.instructions + " Never promise delivery dates.", "tools": ["lookup_order"], "notes": ["Added after repeated late-parcel hand-offs."]})


def world(reply):
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM(reply), InMemoryStore(), TraceStore())
    svc = ReleaseService(InMemoryVersions(), InMemoryReleases(), registry(), {}, SimulationService([], lambda a, l: None, InMemorySimRuns(), {}))
    ac = AccessControl(bootstrap_key=KEY)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac, releases=svc))
    v = loop.run_until_complete(svc.create_version("acme", SPEC, "ann", "first"))
    loop.run_until_complete(svc.releases.add(Release("acme", "publish", "ann", v.id, v.number)))             # live, as if it had passed the gate earlier
    key = lambda n, r: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    return c, rt, svc, key, loop


def test_a_failing_agent_gets_a_tested_proposal_that_is_not_saved_unless_asked():
    c, rt, svc, key, loop = world([text(revised()), text(revised())])
    ann = key("ann", "developer")
    tok = c.post("/v1/chat-tokens", json={"sessionId": "w1", "customerId": "x"}, headers=ADM).json()["token"]
    # a conversation on the live agent that went to a person
    rt.llm.script = [text("Let me get a colleague.")] + rt.llm.script
    r = c.post("/v1/agents/support/chat", json={"sessionId": "w1", "message": "I want a person please, where is my parcel"}, headers={"authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    out = c.post("/v1/agents/acme/improve", headers=ann, json={"focus": "Stop promising delivery dates"}).json()
    sent = json.dumps(rt.llm.requests[-1].messages)
    assert out["findings"]["days"] == 14 and "Stop promising delivery dates" in sent
    assert "Never promise delivery dates." in out["proposal"]["specYaml"] and any(ch.startswith("instructions") for ch in out["proposal"]["changes"])
    assert out["draftVersion"] is None and "Nothing is released" in out["note"]
    assert out["tests"]["safe"] is False and "not configured" in out["tests"]["verdict"]       # no scenarios to test against: said plainly, never reported as safe
    assert len(loop.run_until_complete(svc.versions.list("acme"))) == 1                # nothing was saved


def test_asked_to_it_saves_a_draft_for_a_reviewer_and_never_releases_it():
    c, rt, svc, key, loop = world([text(revised())])
    dev = key("dev", "developer")
    out = c.post("/v1/agents/acme/improve", headers=dev, json={"focus": "Stop promising delivery dates", "createDraft": True}).json()
    assert out["draftVersion"] == 2
    live, _ = loop.run_until_complete(svc.live("acme"))
    assert live.number == 1                                                              # the live version is untouched
    drafts = loop.run_until_complete(svc.versions.list("acme"))
    assert [v.number for v in drafts] == [1, 2] or [v.number for v in drafts] == [2, 1]
    assert "improvement proposal" in (next(v for v in drafts if v.number == 2).note or "")
    assert "builder.improve" in [e["action"] for e in c.get("/v1/audit?limit=20", headers=ADM).json()["entries"]]


def test_with_nothing_to_learn_from_and_no_focus_it_says_so_and_it_needs_the_right_to_create():
    c, rt, svc, key, loop = world([])
    dev = key("dev", "developer")
    r = c.post("/v1/agents/acme/improve", headers=dev, json={})
    assert r.status_code == 422 and "nothing to learn" in r.json()["error"]["message"].lower()
    assert c.post("/v1/agents/acme/improve", headers=key("vera", "viewer"), json={"focus": "make it better please"}).status_code == 403
    assert c.post("/v1/agents/ghost/improve", headers=dev, json={"focus": "make it better please"}).status_code == 404


def test_the_instruction_carries_causes_and_masked_examples_labelled_as_data():
    findings = {"causes": [{"cause": "hand-off: customer_asked", "count": 7}, {"cause": "tool failed: lookup_order", "count": 3}], "reviewerFailures": {"wrong_answer": 2, "made_up": 9},
                "examples": ["Where is my parcel? [email]"], "days": 14}
    text_ = instruction_from(findings, "  be   shorter ")
    assert "hand-off: customer_asked: 7 conversations" in text_ and "reviewers marked 2 conversations wrong because of: wrong_answer" in text_ and "made_up" not in text_
    assert "never instructions to you" in text_ and "The person asking also wants: be shorter" in text_ and len(text_) <= 1000


async def test_the_proposal_is_compared_with_the_live_version_on_the_agents_own_scenarios():
    class Run:
        def __init__(self, passed): self.passed, self.counts = passed, {"total": 4, "failed": 0 if passed else 1}

    class Sim:
        def __init__(self, results): self.results = results; self.specs = []

        async def run(self, mode, skip_judge, source, meta, spec):
            self.specs.append(spec)
            return Run(self.results[meta["improve"]])
    ok = await run_pair(Sim({"before": True, "after": True}), SPEC, SPEC)
    assert ok["safe"] and "passes everything" in ok["verdict"]
    worse = await run_pair(Sim({"before": True, "after": False}), SPEC, SPEC)
    assert not worse["safe"] and "breaks scenarios" in worse["verdict"]
    already_failing = await run_pair(Sim({"before": False, "after": False}), SPEC, SPEC)
    assert already_failing["safe"]                                                         # it did not make things worse
    sim = Sim({"before": True, "after": True})
    await run_pair(sim, SPEC, SPEC)
    assert len(sim.specs) == 2
