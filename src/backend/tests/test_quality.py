"""E7: rubric scoring from recorded facts, calibration against reviewers, and coaching notes."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.insights import HandoffFacts, TurnFacts
from northcx.llm import ScriptedLLM, text
from northcx.qa import DEFAULT_RUBRIC, QAError, RubricService, calibration, score, validate_rubric
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

KEY = "boot" * 10


def turn(**kw):
    base = dict(trace_id="t", session_id="s", agent_id="support", environment="production", started_at=1.0, duration=1.0, status="completed", last_reply="happy to help")
    return TurnFacts(**{**base, **kw})


def test_a_clean_conversation_scores_full_marks_and_each_failure_costs_its_weight():
    r = DEFAULT_RUBRIC
    assert score([turn()], [], 5, r)["score"] == 100.0
    bad = score([turn(tool_errors=["lookup"], errored=True)], [], 5, r)
    assert bad["score"] == round(100 * 6 / 12, 1)                              # tools (3) and errors (3) failed out of 12
    assert [c["reason"] for c in bad["criteria"] if c["result"] == "fail"] == ["a tool failed", "an error occurred"]
    low = score([turn()], [], 2, r)
    assert low["score"] == round(100 * 9 / 12, 1) and next(c for c in low["criteria"] if c["id"] == "rating")["reason"] == "rated 2"


def test_a_check_that_does_not_apply_is_left_out_rather_than_counted_as_a_pass():
    r = score([turn(errored=True)], [], None, DEFAULT_RUBRIC)
    rating = next(c for c in r["criteria"] if c["id"] == "rating")
    assert rating["result"] == "na" and r["score"] == round(100 * 6 / 9, 1)    # the unrated 3 points are not in the total
    only_rating = {"criteria": [{"id": "rating", "label": "Rated well", "weight": 3, "check": "rating_at_least", "n": 4}], "passMark": 70, "sample": 0.1}
    assert score([turn()], [], None, only_rating)["score"] is None             # nothing applied: no score at all


def test_phrase_handoff_and_length_checks():
    r = validate_rubric({"criteria": [
        {"id": "nopromise", "label": "No promises", "weight": 2, "check": "reply_excludes", "phrases": ["guarantee", "100%"]},
        {"id": "polite", "label": "Says thanks", "weight": 1, "check": "reply_includes", "phrases": ["thank"]},
        {"id": "nohand", "label": "Handled alone", "weight": 1, "check": "no_handoff"},
        {"id": "short", "label": "Short", "weight": 1, "check": "within_turns", "n": 2}], "passMark": 80, "sample": 0.2})
    ho = [HandoffFacts("s", "t", "legal", [], None, 1.0)]
    out = score([turn(last_reply="We guarantee it. Thank you!"), turn(started_at=2.0, last_reply="We guarantee it. Thank you!"), turn(started_at=3.0, last_reply="We guarantee it. Thank you!")], ho, None, r)
    got = {c["id"]: (c["result"], c["reason"]) for c in out["criteria"]}
    assert got == {"nopromise": ("fail", "used 'guarantee'"), "polite": ("pass", None), "nohand": ("fail", "handed to a person"), "short": ("fail", "3 messages")}


@pytest.mark.parametrize("bad", [
    {}, {"criteria": []}, {"criteria": [{"id": "a b", "label": "Label", "weight": 1, "check": "no_errors"}]},
    {"criteria": [{"id": "a", "label": "Label", "weight": 11, "check": "no_errors"}]},
    {"criteria": [{"id": "a", "label": "Label", "weight": 1, "check": "magic"}]},
    {"criteria": [{"id": "a", "label": "Label", "weight": 1, "check": "rating_at_least"}]},
    {"criteria": [{"id": "a", "label": "Label", "weight": 1, "check": "reply_excludes", "phrases": []}]},
    {"criteria": [{"id": "a", "label": "Label", "weight": 1, "check": "no_errors"}, {"id": "a", "label": "Label", "weight": 1, "check": "no_errors"}]},
    {"criteria": [{"id": "a", "label": "Label", "weight": 1, "check": "no_errors"}], "passMark": 0},
    {"criteria": [{"id": "a", "label": "Label", "weight": 1, "check": "no_errors"}], "sample": 2},
])
def test_a_bad_rubric_is_refused_with_the_reason(bad):
    with pytest.raises(QAError):
        validate_rubric(bad)


def test_calibration_counts_agreement_and_names_the_disagreements():
    out = calibration({"a": 90.0, "b": 40.0, "c": 95.0, "d": 30.0, "e": None, "f": 80.0}, {"a": "correct", "b": "wrong", "c": "wrong", "d": "correct", "e": "correct"}, 70.0)
    assert out["compared"] == 4 and out["agreement"]["value"] == 0.5 and out["scoreSaidGoodReviewerSaidWrong"] == 1 and out["scoreSaidBadReviewerSaidCorrect"] == 1
    assert [d["sessionId"] for d in out["disagreements"]] == ["d", "c"]       # lowest score first; the unscored and unreviewed ones are not compared
    assert calibration({}, {}, 70.0)["agreement"]["value"] is None


async def test_the_rubric_is_versioned_and_defaults_until_one_is_saved():
    s = RubricService()
    assert (await s.get())["isDefault"] and (await s.get())["version"] == 0
    new = {"criteria": [{"id": "e", "label": "No error", "weight": 1, "check": "no_errors"}]}
    assert (await s.put(new, "ann"))["version"] == 1 and (await s.put(new, "ann"))["version"] == 2
    assert not (await s.get())["isDefault"] and await s.reset() and (await s.get())["isDefault"]


def world():
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([text("Happy to help.")] * 10), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key=KEY)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    key = lambda n, r: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    return c, rt, key


def chat(c, sid, message="where is my order"):
    return c.post("/v1/agents/support/chat", headers={"authorization": f"Bearer {KEY}"}, json={"sessionId": sid, "message": message})


def test_api_scorecards_calibration_and_the_rubric_permissions():
    c, rt, key = world()
    adm, rev, dev = {"authorization": f"Bearer {KEY}"}, key("rev", "reviewer"), key("dev", "developer")
    for i in range(3):
        assert chat(c, f"q-{i}").status_code == 200
    card = c.get("/v1/quality/scorecards?days=7", headers=rev).json()
    assert card["conversations"] == 3 and card["scored"] == 3 and card["averageScore"] is not None and card["rubricVersion"] == 0
    assert {x["id"] for x in card["byCheck"]} == {"tools", "errors", "blocked", "rating", "short"} and "recorded facts" in card["note"]
    assert c.get("/v1/quality/scorecards?days=0", headers=rev).status_code == 400
    # a reviewer's verdicts feed calibration
    for i in range(3):
        assert c.put(f"/v1/sessions/q-{i}/review", headers=rev, json={"verdict": "correct", "handoff": "not_applicable", "failures": [], "note": ""}).status_code == 200
    cal = c.get("/v1/quality/calibration", headers=rev).json()
    assert cal["compared"] == 3 and cal["agreement"]["value"] == 1.0
    # only someone who may publish changes the rubric
    body = {"criteria": [{"id": "e", "label": "No error", "weight": 1, "check": "no_errors"}], "passMark": 90, "sample": 0.5}
    assert c.put("/v1/quality/rubric", headers=rev, json=body).status_code == 403 and c.put("/v1/quality/rubric", headers=dev, json=body).status_code == 403
    assert c.put("/v1/quality/rubric", headers=adm, json=body).json()["version"] == 1
    assert c.put("/v1/quality/rubric", headers=adm, json={**body, "criteria": [{"id": "x", "label": "Bad", "weight": 1, "check": "magic"}]}).status_code == 400
    assert c.get("/v1/quality/scorecards", headers=rev).json()["rubricVersion"] == 1
    assert c.delete("/v1/quality/rubric", headers=adm).json()["reset"] is True
    assert c.get("/v1/quality/scorecards").status_code == 401


def test_coaching_notes_are_screened_audited_and_removable_by_their_author():
    c, rt, key = world()
    adm, ann, ben = {"authorization": f"Bearer {KEY}"}, key("ann", "reviewer"), key("ben", "reviewer")
    chat(c, "k-1")
    r = c.post("/v1/quality/coaching", headers=ann, json={"sessionId": "k-1", "about": "rae", "note": "Good summary; next time confirm the order number first."})
    assert r.status_code == 201 and r.json()["author"] == "ann"
    assert c.post("/v1/quality/coaching", headers=ann, json={"sessionId": "k-1", "about": "rae", "note": "Her email is jo@example.com, call her."}).status_code == 400
    assert c.post("/v1/quality/coaching", headers=ann, json={"sessionId": "nope", "about": "rae", "note": "A fine note about nothing."}).status_code == 404
    assert [n["about"] for n in c.get("/v1/quality/coaching?sessionId=k-1", headers=ben).json()["notes"]] == ["rae"]
    assert c.delete(f"/v1/quality/coaching/{r.json()['id']}", headers=ben).status_code == 403
    assert c.delete(f"/v1/quality/coaching/{r.json()['id']}", headers=ann).status_code == 200 and c.delete(f"/v1/quality/coaching/{r.json()['id']}", headers=adm).status_code == 404
    assert c.post("/v1/quality/coaching", headers=key("dev", "viewer"), json={"sessionId": "k-1", "about": "rae", "note": "A viewer may not coach."}).status_code == 403
    actions = [e["action"] for e in c.get("/v1/audit?limit=20", headers=adm).json()["entries"]]
    assert "quality.coaching" in actions and "quality.coaching_delete" in actions


def test_erasing_a_conversation_erases_its_coaching_notes():
    c, rt, key = world()
    adm = {"authorization": f"Bearer {KEY}"}
    chat(c, "k-2")
    c.post("/v1/quality/coaching", headers=adm, json={"sessionId": "k-2", "about": "rae", "note": "A note that must go with the chat."})
    assert len(c.get("/v1/quality/coaching?sessionId=k-2", headers=adm).json()["notes"]) == 1
    erase = c.delete("/v1/privacy/sessions/k-2", headers=adm)
    assert erase.status_code in (200, 202), erase.text
    assert c.get("/v1/quality/coaching?sessionId=k-2", headers=adm).json()["notes"] == []


async def test_coaching_notes_and_the_rubric_survive_the_database_and_stay_in_their_tenant(app_engine):
    from northcx.db import PgCoaching, PgSettings
    from northcx.qa import CoachingNote
    from northcx.tenancy import TENANT
    notes, rub = PgCoaching(app_engine), RubricService(PgSettings(app_engine))
    one = {"criteria": [{"id": "e", "label": "No error", "weight": 1, "check": "no_errors"}]}
    for tenant in ("acme", "globex"):
        token = TENANT.set(tenant)
        try:
            await notes.add(CoachingNote("s1", "rae", f"A note for {tenant} only.", "ann"))
            await rub.put(one, "ann")
        finally:
            TENANT.reset(token)
    token = TENANT.set("acme")
    try:
        got = await notes.list("s1")
        assert [n.note for n in got] == ["A note for acme only."] and (await rub.get())["version"] == 1
        assert await notes.erase_session("s1") == 1 and await notes.list("s1") == []
    finally:
        TENANT.reset(token)
    token = TENANT.set("globex")
    try:
        assert len(await notes.list("s1")) == 1
    finally:
        TENANT.reset(token)
    token = TENANT.set("nobody")
    try:
        assert await notes.list("s1") == [] and (await rub.get())["isDefault"]
    finally:
        TENANT.reset(token)
