"""WP 5.2: branch and foreach (A4 to A7), and the rule that a change needs a person on every path."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from northcx.automations import AutomationError, AutomationService, Hooks, _approved, validate_definition
from tests.test_automation_tools import ASK, LOOKUP, SAVE, finished, publish, routine, world

REFUND = {"id": "refund", "kind": "tool", "tool": "issue_refund", "args": {"order_id": "{{input.order}}", "amount": 20}}
TOOLS = {"lookup_order": {"effect": "read", "allowed": True}, "issue_refund": {"effect": "write", "allowed": True}}


def branch(when, then="continue", else_="stop", sid="check"):
    return {"id": sid, "kind": "branch", "when": when, "then": then, "else": else_}


def run_routine(d, input_data):
    app, key, loop = world()
    c, ann, ben = TestClient(app), key("ann", "release_manager"), key("ben", "release_manager")
    publish(c, ann, ben, d)
    return loop.run_until_complete(app.state.automations.run(d["id"], "manual", "ann", json.dumps(input_data))), (app, c, ann, ben, key, loop)


def test_a_branch_carries_on_when_the_condition_holds_and_stops_the_run_when_it_does_not():
    d = routine("delivered-only", [LOOKUP, branch("previous.status == 'delivered'"), SAVE])
    run, _ = run_routine(d, {"order": "1042"})
    assert run.status == "succeeded" and [s["id"] for s in run.steps] == ["find", "check", "save"]
    assert run.steps[1]["condition"] is True and run.steps[1]["took"] == "continue"
    run, _ = run_routine({**d, "id": "delivered-only-2"}, {"order": "3150"})
    assert run.status == "succeeded" and [s["id"] for s in run.steps] == ["find", "check"]
    assert run.steps[1]["condition"] is False and run.steps[1]["took"] == "stop" and json.loads(run.outcome)["status"] == "in_transit"


def test_a_branch_can_skip_steps_ahead():
    d = routine("skip-save", [LOOKUP, branch("previous.total > 100", then={"skip": 1}, else_="continue"), {**SAVE, "id": "save-small"},
                              {"id": "save-big", "kind": "output", "title": "Big {date}"}])
    run, _ = run_routine(d, {"order": "2077"})
    assert [s["id"] for s in run.steps] == ["find", "check", "save-big"] and run.steps[1]["took"] == "skip 1"
    run, _ = run_routine({**d, "id": "skip-save-2"}, {"order": "1042"})
    assert [s["id"] for s in run.steps] == ["find", "check", "save-small", "save-big"]


def test_a_branch_reads_the_trigger_input_too():
    d = routine("urgent-only", [branch("input.priority == 'urgent'"), SAVE])
    assert [s["id"] for s in run_routine(d, {"priority": "urgent"})[0].steps] == ["check", "save"]
    assert [s["id"] for s in run_routine({**d, "id": "urgent-only-2"}, {"priority": "low"})[0].steps] == ["check"]


@pytest.mark.parametrize("step,why", [
    (branch(""), "write the condition"),
    (branch("__import__('os')"), "condition is not valid"),
    (branch("item.id == 1"), "only inside a foreach"),
    (branch("previous.a == 1", then={"skip": 0}), "continue, stop, or"),
    (branch("previous.a == 1", then={"skip": 10}), "continue, stop, or"),
    (branch("previous.a == 1", else_="jump"), "continue, stop, or"),
])
def test_a_bad_branch_is_refused_with_the_reason(step, why):
    with pytest.raises(AutomationError, match=why):
        validate_definition(routine("bad-branch", [step, SAVE]), set(), tools=TOOLS)


def test_a_skip_cannot_jump_around_the_person_step_before_a_change():
    ask = {**ASK}
    unsafe = routine("around", [LOOKUP, branch("previous.total > 100", then={"skip": 1}, else_="continue"), ask, REFUND])
    with pytest.raises(AutomationError, match="'person' step must come before"):
        validate_definition(unsafe, set(), tools=TOOLS)
    safe = routine("through", [LOOKUP, branch("previous.total > 100", then="continue", else_="stop"), ask, REFUND])
    assert validate_definition(safe, set(), tools=TOOLS)["steps"][-1]["id"] == "refund"
    skip_past = routine("past", [branch("input.x == 1", then={"skip": 1}, else_="continue"), ask, SAVE, REFUND])
    with pytest.raises(AutomationError):
        validate_definition(skip_past, set(), tools=TOOLS)


def test_which_steps_are_approved_on_every_path():
    steps = [{"kind": "tool"}, {"kind": "branch", "then": {"skip": 1}, "else": "continue"}, {"kind": "person"}, {"kind": "tool"}, {"kind": "tool"}]
    assert _approved(steps) == [False, False, False, False, False]          # the skip reaches step 3 without the person; step 4 follows 3
    safe = [{"kind": "person"}, {"kind": "branch", "then": {"skip": 1}, "else": "continue"}, {"kind": "tool"}, {"kind": "tool"}]
    assert _approved(safe) == [False, True, True, True]


def test_a_foreach_runs_the_step_for_each_item_and_collects_the_results():
    d = routine("each-order", [{"id": "each", "kind": "foreach", "over": "input.orders", "do": {"kind": "tool", "tool": "lookup_order", "args": {"order_id": "{{item}}"}}}, SAVE])
    run, _ = run_routine(d, {"orders": ["1042", "2077"]})
    assert run.status == "succeeded", run.error
    assert [r["id"] for r in json.loads(run.steps[0]["output"])] == ["1042", "2077"] and run.steps[0]["items"] == 2 and run.steps[0]["done"] == 2


def test_a_foreach_refuses_more_items_than_its_limit_and_a_value_that_is_not_a_list():
    d = routine("limited", [{"id": "each", "kind": "foreach", "over": "input.orders", "max": 3, "do": {"kind": "tool", "tool": "lookup_order", "args": {"order_id": "{{item}}"}}}])
    run, _ = run_routine(d, {"orders": ["1", "2", "3", "4"]})
    assert run.status == "stopped" and "has 4 items and the step goes through at most 3" in run.error
    run, _ = run_routine({**d, "id": "limited-2"}, {"orders": "1042"})
    assert run.status == "stopped" and "is not a list" in run.error


@pytest.mark.parametrize("step,why", [
    ({"id": "e", "kind": "foreach", "over": "input.o", "max": 21, "do": {"kind": "tool", "tool": "lookup_order"}}, "from 1 to 20"),
    ({"id": "e", "kind": "foreach", "over": "item.o", "do": {"kind": "tool", "tool": "lookup_order"}}, "path to a list"),
    ({"id": "e", "kind": "foreach", "over": "input.o", "do": {"kind": "person", "ask": "Is this fine?"}}, "one tool or assistant step"),
    ({"id": "e", "kind": "foreach", "over": "input.o", "do": {"kind": "foreach"}}, "one tool or assistant step"),
    ({"id": "e", "kind": "foreach", "over": "input.o", "do": {"kind": "assistant", "assistant": "x", "prompt": "hi"}}, "prompt of 5 to 2000"),
    ({"id": "e", "kind": "foreach", "over": "input.o", "do": {"kind": "tool", "tool": "issue_refund", "args": {"order_id": "{{item}}", "amount": 5}}}, "'person' step must come before"),
])
def test_a_bad_foreach_is_refused_with_the_reason(step, why):
    with pytest.raises(AutomationError, match=why):
        validate_definition(routine("bad-each", [step]), set(), tools=TOOLS)


def test_an_item_cannot_be_used_outside_a_foreach_step():
    with pytest.raises(AutomationError, match="only inside a foreach"):
        validate_definition(routine("loose-item", [{"id": "a", "kind": "assistant", "assistant": "x", "prompt": "Look at {{item}}"}]), set())


def test_a_foreach_change_needs_a_person_first_and_one_failing_item_stops_the_run_and_says_which():
    each = {"id": "each", "kind": "foreach", "over": "input.refunds", "do": {"kind": "tool", "tool": "issue_refund", "args": {"order_id": "{{item.order_id}}", "amount": "{{item.amount}}"}}}
    d = routine("refund-each", [ASK, each])
    app, key, loop = world()
    c, ann, ben, rev = TestClient(app), key("ann", "release_manager"), key("ben", "release_manager"), key("rev", "reviewer")
    publish(c, ann, ben, d)
    run = loop.run_until_complete(app.state.automations.run("refund-each", "manual", "ann", json.dumps({"refunds": [{"order_id": "1042", "amount": 20}, {"order_id": "3150", "amount": 10}]})))
    assert c.post(f"/v1/automation-runs/{run.id}/decision", headers=rev, json={"approve": True}).status_code == 200
    done = finished(c, run.id, ann)
    assert done["status"] == "stopped" and "item 2 of 2" in done["error"] and "Only delivered orders can be refunded" in done["error"]
    assert done["steps"][-1]["done"] == 1


def test_each_item_gets_its_own_key_and_the_results_are_not_cut_off():
    keys = []
    async def go(items):
        svc = AutomationService()
        async def noop(*a): return ("", "completed", None)
        async def call(name, args, key):
            keys.append(key)
            return {"v": "x" * 300}
        svc.hooks = Hooks(noop, noop, tools=lambda: {"t": TOOLS["lookup_order"]}, call_tool=call)
        a = await svc.create(routine("keys", [{"id": "each", "kind": "foreach", "over": "input.l", "max": 20, "do": {"kind": "tool", "tool": "t", "args": {"x": "{{item}}"}}}]), "ann")
        await svc.propose(a.id, "ann")
        await svc.decide(a.id, True, "ben", None)
        return await svc.run(a.id, "manual", "ann", json.dumps({"l": list(range(items))}))
    run = asyncio.run(go(3))
    assert keys == [f"auto:{run.id}:each:{i}" for i in range(3)]
    big = asyncio.run(go(20))
    assert big.status == "stopped" and "at most 4000 can be passed on" in big.error
