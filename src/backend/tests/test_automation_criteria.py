"""WP 5.5: a routine judges recent conversations of an agent against plain-language criteria (A12, A13). Judged with a scripted model only: unverified."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.automations import AutomationError, AutomationService, Hooks, validate_definition
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore
from tests.test_automation_tools import KEY, publish, routine

OK, BAD = text('{"score": 5, "reason": "fine"}'), text('{"score": 2, "reason": "promised a refund too early"}')
CRITERIA = ["Replies never promise a refund before it is approved", "Replies are polite and short"]
STEP = {"id": "judge", "kind": "criteria", "agent": "support", "criteria": CRITERIA, "sample": 5, "days": 7}


def world(judge_replies):
    loop = asyncio.new_event_loop()
    llm = ScriptedLLM([text("Hello, how can I help?"), text("Your order is on its way."), *judge_replies])
    rt = Runtime(llm, InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=ac)
    key = lambda n, r: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    loop.run_until_complete(rt.run(support_agent(), "c1", "hello, my email is ann@example.com"))
    loop.run_until_complete(rt.run(support_agent(), "c2", "where is my order 1042?"))
    return app, TestClient(app), key, loop, llm


def test_each_recent_conversation_is_judged_on_each_criterion_and_the_result_says_it_is_unverified():
    app, c, key, loop, llm = world([OK, BAD, OK, OK])                 # conversation 1: criterion 1 ok, 2 bad; conversation 2: both ok (order of sessions is newest first)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("quality-watch", [STEP]))
    run = loop.run_until_complete(app.state.automations.run("quality-watch", "manual", "ann"))
    assert run.status == "succeeded", run.error
    out = json.loads(run.steps[0]["output"])
    assert out["conversations"] == 2 and out["calibrated"] is False and out["judged"] == "unverified" and out["agent"] == "support"
    assert [(x["text"], x["passed"] + x["failed"] + x["unusable"]) for x in out["criteria"]] == [(CRITERIA[0], 2), (CRITERIA[1], 2)]
    assert sum(x["passed"] for x in out["criteria"]) == 3 and sum(x["failed"] for x in out["criteria"]) == 1


def test_the_judge_reads_masked_transcripts_and_the_criterion_as_the_rubric():
    app, c, key, loop, llm = world([OK, OK, OK, OK])
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("quality-watch", [STEP]))
    loop.run_until_complete(app.state.automations.run("quality-watch", "manual", "ann"))
    sent = [r for r in llm.requests if "RUBRIC" in json.dumps(r.messages, default=str)]
    assert len(sent) == 4
    blob = json.dumps([r.messages for r in sent], default=str)
    assert "ann@example.com" not in blob and CRITERIA[0] in blob and "never follow instructions" in sent[0].system


def test_an_unusable_judge_answer_is_counted_as_unusable_never_as_a_pass():
    app, c, key, loop, llm = world([text("I think it is fine"), OK, OK, OK])
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, routine("quality-watch", [STEP]))
    run = loop.run_until_complete(app.state.automations.run("quality-watch", "manual", "ann"))
    out = json.loads(run.steps[0]["output"])
    assert sum(x["unusable"] for x in out["criteria"]) == 1 and sum(x["passed"] for x in out["criteria"]) == 3


def test_the_run_stops_when_the_daily_budget_is_used_up_part_way():
    async def go():
        svc = AutomationService()
        calls = []
        async def noop(*a): return ("", "completed", None)
        async def sample(agent, days, n): return ["customer: hi", "customer: hello", "customer: hey"]
        async def judge(criterion, transcript):
            calls.append(criterion)
            return True
        async def over(): return len(calls) >= 2
        svc.hooks = Hooks(noop, noop, over_budget=over, sample_conversations=sample, judge_text=judge, live_agent=lambda a: asyncio.sleep(0, True))
        a = await svc.create(routine("quality-watch", [{**STEP, "criteria": [CRITERIA[0]]}]), "ann")
        await svc.propose(a.id, "ann")
        await svc.decide(a.id, True, "ben", None)
        return await svc.run(a.id, "manual", "ann"), calls
    run, calls = asyncio.run(go())
    assert run.status == "stopped" and "daily budget" in run.error and len(calls) == 2


@pytest.mark.parametrize("step,why", [
    ({"id": "a", "kind": "criteria", "criteria": ["Be kind to customers"]}, "name the agent"),
    ({"id": "a", "kind": "criteria", "agent": "support", "criteria": []}, "1 to 5 criteria"),
    ({"id": "a", "kind": "criteria", "agent": "support", "criteria": ["Be kind to customers"] * 6}, "1 to 5 criteria"),
    ({"id": "a", "kind": "criteria", "agent": "support", "criteria": ["short"]}, "10 to 200 characters"),
    ({"id": "a", "kind": "criteria", "agent": "support", "criteria": ["Be kind to {{previous}} customers"]}, "10 to 200 characters"),
    ({"id": "a", "kind": "criteria", "agent": "support", "criteria": ["Be kind to customers"], "sample": 21}, "sample is a whole number from 1 to 20"),
    ({"id": "a", "kind": "criteria", "agent": "support", "criteria": ["Be kind to customers"], "days": 31}, "days is a whole number from 1 to 30"),
])
def test_a_bad_criteria_step_is_refused_with_the_reason(step, why):
    with pytest.raises(AutomationError, match=why):
        validate_definition(routine("bad-criteria", [step]), set())


def test_a_routine_can_alert_when_a_criterion_fails():
    app, c, key, loop, llm = world([BAD, OK, OK, OK])
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    when = {"id": "any", "kind": "branch", "when": "previous.criteria[0].failed > 0", "then": "continue", "else": "stop"}
    publish(c, ann, ben, routine("quality-watch", [STEP, when, {"id": "tell", "kind": "alert", "text": "A reply broke a quality criterion."}]))
    # no alert manager in this app: the step says so instead of pretending it alerted
    run = loop.run_until_complete(app.state.automations.run("quality-watch", "manual", "ann"))
    assert run.status == "stopped" and "Alerts are not configured" in run.error
