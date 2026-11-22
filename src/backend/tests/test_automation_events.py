"""WP 5.3: a delivery that carries an event id starts a routine once (A8); a trigger can name a condition on what arrives (A9)."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from northcx.automations import AutomationError, validate_definition
from tests.test_automations import ADM, BRIEF, EVENT_ROUTINE, propose_and_approve, sign, world, world_with_events

HOOK = {**BRIEF, "id": "on-hook", "trigger": {"type": "webhook"}}


def hook_world(trigger=None):
    app, rt, key, loop = world()
    c = TestClient(app)
    ann, ben, chan = key("ann", "release_manager"), key("ben", "release_manager"), key("hook", "trigger")
    made = c.post("/v1/automations", headers=ann, json={"definition": {**HOOK, "trigger": trigger or HOOK["trigger"]}})
    assert made.status_code == 201, made.text
    propose_and_approve(c, ann, ben, "on-hook")
    secret = made.json()["webhookSecret"]

    def send(body, event_id=None):
        raw = json.dumps(body).encode()
        return c.post("/v1/automations/on-hook/hook", content=raw, headers={**chan, "x-northcx-signature": sign(secret, raw), **({"x-northcx-event-id": event_id} if event_id else {})})

    def runs():
        return c.get("/v1/automations/on-hook/runs", headers=ann).json()["runs"]

    def settle():
        for _ in range(100):
            if all(r["status"] != "running" for r in runs()):
                return
            time.sleep(0.05)
    return c, send, runs, settle


def test_the_same_delivery_sent_twice_starts_the_routine_once_and_names_the_first_run():
    c, send, runs, settle = hook_world()
    first = send({"order": "1042"}, "evt-1")
    assert first.status_code == 202
    again = send({"order": "1042"}, "evt-1")
    assert again.status_code == 200 and again.json()["duplicate"] is True and again.json()["runId"] == first.json()["id"]
    assert again.headers["idempotent-replay"] == "true"
    settle()
    assert len(runs()) == 1
    audit = [e for e in c.get("/v1/audit?limit=40", headers=ADM).json()["entries"] if e["action"] == "automation.hook"]
    assert any("duplicate" in json.dumps(e) for e in audit)
    other = send({"order": "2077"}, "evt-2")                      # a different event is a different run
    assert other.status_code == 202 and other.json()["id"] != first.json()["id"]
    settle()
    assert len(runs()) == 2


def test_an_event_id_used_with_a_different_body_is_refused_and_a_bad_id_is_rejected():
    c, send, runs, settle = hook_world()
    assert send({"order": "1042"}, "evt-9").status_code == 202
    r = send({"order": "9999"}, "evt-9")
    assert r.status_code == 422 and r.json()["error"]["code"] == "event_id_reused"
    assert send({"order": "1"}, "has a space").status_code == 400
    assert send({"order": "1"}, "x" * 201).status_code == 400
    settle()
    assert len(runs()) == 1


def test_a_delivery_that_could_not_start_does_not_use_up_its_event_id():
    app, rt, key, loop = world()
    c = TestClient(app)
    ann, ben, chan = key("ann", "release_manager"), key("ben", "release_manager"), key("hook", "trigger")
    made = c.post("/v1/automations", headers=ann, json={"definition": HOOK})
    propose_and_approve(c, ann, ben, "on-hook")
    raw = json.dumps({"n": 1}).encode()
    headers = {**chan, "x-northcx-signature": sign(made.json()["webhookSecret"], raw), "x-northcx-event-id": "evt-p"}
    assert c.post("/v1/automations/on-hook/pause", headers=ann).status_code == 200
    assert c.post("/v1/automations/on-hook/hook", content=raw, headers=headers).status_code == 409        # paused: refused
    assert c.post("/v1/automations/on-hook/resume", headers=ann).status_code == 200
    assert c.post("/v1/automations/on-hook/hook", content=raw, headers=headers).status_code == 202        # the same event id works once the routine can run


def test_only_events_that_match_the_trigger_condition_start_a_run_and_the_rest_are_recorded_as_ignored():
    c, send, runs, settle = hook_world({"type": "webhook", "when": "input.priority == 'urgent' and input.total > 100"})
    assert send({"priority": "low", "total": 500}).json() == {"ignored": True}
    assert send({"priority": "urgent", "total": 50}).status_code == 200
    assert runs() == []
    assert send({"priority": "urgent", "total": 500}).status_code == 202
    settle()
    assert len(runs()) == 1
    audit = [e for e in c.get("/v1/audit?limit=60", headers=ADM).json()["entries"] if e["action"] == "automation.hook"]
    assert sum(1 for e in audit if "ignored" in json.dumps(e)) == 2


def test_a_body_that_is_not_json_does_not_match_a_condition_on_its_fields():
    c, send, runs, settle = hook_world({"type": "webhook", "when": "input.priority == 'urgent'"})
    assert send("urgent").json() == {"ignored": True}


@pytest.mark.parametrize("trigger,why", [
    ({"type": "manual", "when": "input.a == 1"}, "only with a webhook or an event"),
    ({"type": "schedule", "everyHours": 2, "when": "input.a == 1"}, "only with a webhook or an event"),
    ({"type": "webhook", "when": "previous.a == 1"}, "can read only input"),
    ({"type": "webhook", "when": "__import__('x')"}, "not valid"),
    ({"type": "webhook", "when": ""}, "write the condition"),
])
def test_a_bad_trigger_condition_is_refused_with_the_reason(trigger, why):
    with pytest.raises(AutomationError, match=why):
        validate_definition({**HOOK, "trigger": trigger}, {"performance", "quality"}, events={"handoff.created"})


def test_an_event_routine_with_a_condition_starts_only_for_the_events_that_match_it():
    app, feed, key, loop = world_with_events()
    c = TestClient(app)
    ann, ben = key("ann", "release_manager"), key("ben", "release_manager")
    routine = {**EVENT_ROUTINE, "trigger": {"type": "event", "event": "handoff.created", "when": "input.data.queue == 'billing'"}}
    assert c.post("/v1/automations", headers=ann, json={"definition": routine}).status_code == 201
    propose_and_approve(c, ann, ben, "on-handoff")
    svc = app.state.automations

    async def go():
        assert await svc.events_tick() == 0
        await feed.emit("handoff.created", {"queue": "returns"}, "s-1")
        await feed.emit("handoff.created", {"queue": "billing"}, "s-2")
        await feed.emit("handoff.created", {"queue": "returns"}, "s-3")
        assert await svc.events_tick() == 1
        for t in list(svc._tasks):
            await t
        assert await svc.events_tick() == 0
        return await svc.repo.runs("on-handoff", 10)
    runs = loop.run_until_complete(go())
    assert len(runs) == 1 and json.loads(runs[0].input_text)["sessionId"] == "s-2"
