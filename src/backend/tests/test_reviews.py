"""Conversation review (U4): queue ordering, validation, quality numbers, API, permissions, audit and erasure."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.insights import FeedbackFacts, HandoffFacts, TurnFacts
from northcx.reviews import InMemoryReviews, Review, ReviewError, quality, queue, sampled, validate
from northcx.server import create_app
from tests.test_insights import KEY, H, conversations

NOW = 1_800_000_000.0


def turn(i, session=None, status="completed", **kw):
    return TurnFacts(f"t{i}", session or f"s{i}", "support", "production", NOW + i, 1.0, status, 10, 1, 0, kw.pop("tools", []), kw.pop("tool_errors", []),
                     kw.pop("guardrails", []), **kw)


def test_validation_collects_every_problem():
    assert validate("correct", "not_applicable", [], " ok ") == ("correct", "not_applicable", [], "ok")
    assert validate("wrong", "unneeded", ["bad_tone", "bad_tone"], "", True)[2] == ["bad_tone"]
    with pytest.raises(ReviewError) as e:
        validate("maybe", "later", ["nope"], "x" * 1001)
    for part in ("verdict", "handoff", "unknown failure", "longer than"):
        assert part in str(e.value)
    for args, text in [(("correct", "not_applicable", ["slow"], ""), "cannot also list"), (("wrong", "not_applicable", [], ""), "at least one"),
                       (("correct", "needed", [], "", False), "not handed"), (("correct", "not_applicable", [], "", True), "needed or unneeded")]:
        with pytest.raises(ReviewError, match=text):
            validate(*args)


def test_sampling_is_deterministic_and_proportionate():
    assert all(sampled(f"s{i}", 1) for i in range(5)) and not any(sampled(f"s{i}", 0) for i in range(5))
    picked = [sampled(f"s{i}", 0.1) for i in range(2000)]
    assert picked == [sampled(f"s{i}", 0.1) for i in range(2000)] and 100 < sum(picked) < 300


def test_queue_puts_worrying_conversations_first_and_hides_reviewed():
    turns = [turn(1), turn(2, status="escalated"), turn(3, tool_errors=["x"], tools=["x"]), turn(4), turn(5, guardrails=["g"])]
    hands = [HandoffFacts("s2", "t2", "agent_handoff", [], "billing", NOW)]
    fb = [FeedbackFacts("s4", 1, NOW), FeedbackFacts("s1", 5, NOW)]
    rows = queue(turns, hands, fb, {}, sample=0)
    assert [r["sessionId"] for r in rows] == ["s4", "s2", "s3", "s5"]  # s1 is fine and not sampled
    assert rows[0]["reasons"] == ["rated 1/5"] and rows[1]["handedOff"] and rows[1]["reasons"] == ["handed to a person: agent_handoff"]
    assert [r["sessionId"] for r in queue(turns, hands, fb, {}, sample=1, limit=2)] == ["s4", "s2"]
    done = {"s4": Review("s4", "wrong", "not_applicable", ["slow"], "", "rae")}
    assert "s4" not in [r["sessionId"] for r in queue(turns, hands, fb, done, sample=0)]
    assert queue(turns, hands, fb, done, include_reviewed=True, sample=0)[0]["review"]["failures"] == ["slow"]
    assert [r["reasons"] for r in queue([turn(9)], [], [], {}, sample=1)] == [["random sample"]]


def test_quality_numbers_have_numerators_and_denominators():
    rs = [Review("a", "correct", "not_applicable", [], "", "r"), Review("b", "wrong", "needed", ["wrong_answer"], "", "r"),
          Review("c", "wrong", "unneeded", ["unneeded_handoff", "bad_tone"], "", "r"), Review("d", "correct", "needed", [], "", "r")]
    q = quality(rs)
    assert q["reviewed"] == 4 and q["correctRate"] == {"value": 0.5, "numerator": 2, "denominator": 4}
    assert q["escalationCorrectness"] == {"value": 0.6667, "numerator": 2, "denominator": 3} and q["unneededEscalationRate"]["numerator"] == 1
    assert q["failuresByKind"] == {"wrong_answer": 1, "unneeded_handoff": 1, "bad_tone": 1} and quality([])["correctRate"]["value"] is None


@pytest.fixture(params=["memory", "postgres"])
def review_repo(request):
    if request.param == "memory":
        return InMemoryReviews()
    from northcx.db import PgReviews
    return PgReviews(request.getfixturevalue("engine"))


async def test_review_repository_contract(review_repo):
    assert await review_repo.put(Review("s1", "wrong", "unneeded", ["slow", "other"], "n", "rae", 100.0)) is True
    assert await review_repo.put(Review("s1", "correct", "not_applicable", [], "", "jo", 200.0)) is False  # a second review replaces the first
    got = await review_repo.get("s1")
    assert (got.verdict, got.reviewer, got.failures) == ("correct", "jo", []) and await review_repo.get("nope") is None
    await review_repo.put(Review("s2", "wrong", "needed", ["slow"], "", "rae", 300.0))
    assert [r.session_id for r in await review_repo.between(250, 400)] == ["s2"]
    assert set(await review_repo.for_sessions(["s1", "s2", "s3"])) == {"s1", "s2"} and await review_repo.for_sessions([]) == {}
    assert await review_repo.erase_session("s1") == 1 and await review_repo.erase_session("s1") == 0


def api():
    rt = asyncio.new_event_loop().run_until_complete(conversations())
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac)), ac, rt


def test_api_queue_context_review_quality_permissions_audit_and_erasure():
    c, ac, rt = api()
    q = c.get("/v1/reviews/queue?sample=0", headers=H).json()["queue"]
    ids = [r["sessionId"] for r in q]
    assert {"s-handoff", "s-legal", "s-guard"} <= set(ids) and "s-ok" not in ids
    assert c.get("/v1/reviews/queue?sample=2", headers=H).status_code == 400
    ctx = c.get("/v1/sessions/s-handoff/transcript", headers=H).json()
    assert ctx["handoffs"] and ctx["traces"] and ctx["review"] is None and ctx["transcript"] and c.get("/v1/sessions/never/transcript", headers=H).status_code == 404
    # hand-off judgement must match whether the conversation was handed over
    bad = c.put("/v1/sessions/s-handoff/review", headers=H, json={"verdict": "correct"})
    assert bad.status_code == 400 and "handed to a person" in bad.json()["error"]["message"]
    ok = c.put("/v1/sessions/s-handoff/review", headers=H, json={"verdict": "wrong", "handoff": "unneeded", "failures": ["unneeded_handoff"], "note": "could have answered"})
    assert ok.json() == {"saved": True, "replaced": False}
    assert c.put("/v1/sessions/s-ok/review", headers=H, json={"verdict": "correct"}).json()["saved"]
    assert c.put("/v1/sessions/s-ok/review", headers=H, json={"verdict": "wrong", "failures": ["slow"]}).json()["replaced"] is True
    assert c.put("/v1/sessions/never/review", headers=H, json={"verdict": "correct"}).status_code == 404
    assert c.get("/v1/sessions/s-handoff/transcript", headers=H).json()["review"]["note"] == "could have answered"
    assert "s-handoff" not in [r["sessionId"] for r in c.get("/v1/reviews/queue?sample=0", headers=H).json()["queue"]]
    qual = c.get("/v1/insights/review-quality", headers=H).json()
    assert qual["reviewed"] == 2 and qual["correctRate"]["numerator"] == 0 and qual["unneededEscalationRate"]["numerator"] == 1
    loop = asyncio.new_event_loop()
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    for role, write, read in [("reviewer", 200, 200), ("developer", 200, 200), ("viewer", 403, 200), ("auditor", 403, 200), ("channel", 403, 403)]:
        h = {"authorization": f"Bearer {key(role)}"}
        assert c.put("/v1/sessions/s-ok/review", headers=h, json={"verdict": "correct"}).status_code == write, role
        assert c.get("/v1/reviews/queue", headers=h).status_code == read, role
    assert "conversation.review" in [e["action"] for e in c.get("/v1/audit?limit=50", headers=H).json()["entries"]]
    c.delete("/v1/privacy/customers/cust", headers=H)
    assert c.get("/v1/sessions/s-handoff/transcript", headers=H).status_code in (200, 404)
    assert c.get("/v1/insights/review-quality", headers=H).json()["reviewed"] == 0
