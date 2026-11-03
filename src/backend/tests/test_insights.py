"""Insights: metrics with numerators and denominators, time series, failure analysis, intent gaps, feedback."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.agent import Agent
from northcx.insights import (FeedbackFacts, HandoffFacts, InMemoryFeedback, InMemoryInsightsSource, InsightsService, TurnFacts, compute, facts_from_trace,
                              failures, gaps, percentile, ratio, timeseries)
from northcx.knowledge import InMemoryKnowledge, Source, knowledge_tool
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import Trace, TraceStore

NOW = 1_800_000_000.0


def turn(i, status="completed", session=None, dur=1.0, tokens=100, tools=(), tool_errors=(), guardrails=(), at=NOW, **kw):
    return TurnFacts(f"t{i}", session or f"s{i}", "support", "production", at, dur, status, tokens, 1, 0, list(tools), list(tool_errors), list(guardrails), **kw)


def test_helpers():
    assert ratio(1, 4) == {"value": 0.25, "numerator": 1, "denominator": 4} and ratio(0, 0)["value"] is None
    assert percentile([], 0.5) is None and percentile([5], 0.95) == 5 and percentile([1, 2, 3, 4], 0.5) == 2.5 and percentile([1, 2, 3, 4, 100], 0.95) == 80.8


def test_metrics_report_numerators_denominators_and_period():
    turns = [turn(1, tools=["lookup_order"]), turn(2, "escalated", session="s2", tools=["lookup_order"], tool_errors=["lookup_order"]),
             turn(3, "needs_approval", session="s3", guardrails=["no-card-numbers"]), turn(4, session="s1", dur=3.0, tokens=300)]
    hands = [HandoffFacts("s2", "t2", "agent_handoff", ["legal"], "billing", NOW), HandoffFacts("other", "x", "step_limit", [], None, NOW)]
    fb = [FeedbackFacts("s1", 5, NOW), FeedbackFacts("s3", 3, NOW), FeedbackFacts("elsewhere", 1, NOW)]
    m = compute(turns, hands, fb, NOW - 100, NOW + 100, price_per_million_tokens=10)
    assert m["conversations"] == 3 and m["turns"] == 4 and m["period"] == {"from": NOW - 100, "to": NOW + 100}
    assert m["containmentRate"] == {"value": 0.6667, "numerator": 2, "denominator": 3}  # one of three conversations reached a person
    assert m["escalationRate"]["numerator"] == 1 and m["approvalRate"]["numerator"] == 1 and m["guardrailBlockRate"]["numerator"] == 1
    assert m["toolErrorRate"] == {"value": 0.5, "numerator": 1, "denominator": 2}  # only turns that used tools count
    assert m["tokens"] == {"total": 600, "perConversation": 200, "modelCalls": 4} and m["estimatedCost"]["amount"] == 0.006
    assert m["handoffs"]["byTrigger"] == {"agent_handoff": 1, "step_limit": 1} and m["handoffs"]["byQueue"] == {"billing": 1, "general": 1} and m["handoffs"]["byTopic"] == {"legal": 1}
    assert m["satisfaction"]["average"] == 4.0 and m["satisfaction"]["responses"] == 2  # feedback for conversations outside the period is not counted
    assert m["satisfaction"]["responseRate"]["denominator"] == 3 and m["satisfaction"]["distribution"] == {"1": 0, "2": 0, "3": 1, "4": 0, "5": 1}
    assert m["latencySeconds"]["p50"] == 1.0 and m["tools"] == {"used": {"lookup_order": 2}, "errors": {"lookup_order": 1}} and "not a resolution rate" in m["note"]


def test_empty_periods_are_honest_not_zero():
    m = compute([], [], [], 0, 1)
    assert m["containmentRate"]["value"] is None and m["latencySeconds"]["p95"] is None and m["satisfaction"]["average"] is None and "estimatedCost" not in m


def test_time_series_buckets_by_hour_and_day_and_fills_gaps():
    turns = [turn(1, at=NOW), turn(2, "escalated", at=NOW + 10), turn(3, at=NOW + 7200, guardrails=["g"])]
    hours = timeseries(turns, NOW - 3600, NOW + 8000, "hour")
    by = {p["start"]: p for p in hours}
    first = int(NOW // 3600) * 3600
    assert by[first]["turns"] == 2 and by[first]["escalated"] == 1 and by[first + 7200]["guardrailBlocks"] == 1 and by[first + 3600]["turns"] == 0
    days = timeseries(turns, NOW - 86400, NOW + 86400, "day")
    assert sum(p["turns"] for p in days) == 3 and len(days) >= 3


def test_failure_analysis_ranks_causes_with_examples():
    turns = [turn(1, "escalated"), turn(2, "escalated"), turn(3, tool_errors=["issue_refund"]), turn(4, guardrails=["no-card-numbers"]), turn(5, tool_errors=["issue_refund", "issue_refund"])]
    hands = [HandoffFacts("s1", "t1", "step_limit", [], None, NOW), HandoffFacts("s2", "t2", "step_limit", [], None, NOW)]
    rows = failures(turns, hands)
    assert [(r["cause"], r["count"]) for r in rows[:3]] == [("hand-off: step_limit", 2), ("tool failed: issue_refund", 2), ("blocked by: no-card-numbers", 1)]
    assert rows[0]["exampleTraceIds"] == ["t1", "t2"] and rows[0]["share"] == {"value": 0.4, "numerator": 2, "denominator": 5}
    assert failures([], []) == []


def test_gaps_show_unanswered_searches_and_masked_messages_before_hand_offs():
    turns = [turn(1, "escalated", empty_searches=["Gift Wrapping "], first_message="Do you offer gift wrapping? My email is jane@example.com"),
             turn(2, empty_searches=["gift wrapping", "warranty"]), turn(3, "escalated", first_message="legal stuff")]
    hands = [HandoffFacts("s1", "t1", "agent_handoff", [], None, NOW), HandoffFacts("s3", "t3", "forced_topic", ["legal"], None, NOW)]
    g = gaps(turns, hands)
    assert g["unansweredSearches"][0] == {"query": "gift wrapping", "count": 2} and {"query": "warranty", "count": 1} in g["unansweredSearches"]
    msgs = [m["message"] for m in g["messagesBeforeHandoff"]]
    assert len(msgs) == 1 and "jane@example.com" not in msgs[0] and msgs[0].startswith("do you offer gift wrapping")  # only agent-side failures, personal data masked


# ---- from real recorded conversations ----
async def conversations(kb=None):
    kb = kb or InMemoryKnowledge()
    await kb.create_source(Source("help", "Help"))
    agent = Agent(id="support", instructions="i", tools=[*support_agent().tools, knowledge_tool(kb)], guardrails=support_agent().guardrails,
                  input_guardrails=support_agent().input_guardrails, forced_handoffs=support_agent().forced_handoffs)
    script = [tool_call("lookup_order", {"order_id": "1042"}, "a"), text("Delivered."),                        # s-ok
              tool_call("search_knowledge", {"query": "gift wrapping"}, "b"), text("I couldn't find that."),    # s-gap
              tool_call("handoff_to_human", {"reason": "wants a person"}, "c"),                                # s-agent-handoff
              text("Your card 4111 1111 1111 1111 is fine."), text("Your order is fine.")]                      # s-guard (rejected, rewritten)
    rt = Runtime(ScriptedLLM(script), InMemoryStore(), TraceStore())
    for sid, msg in [("s-ok", "where is 1042?"), ("s-gap", "do you wrap gifts?"), ("s-handoff", "get me a person"), ("s-legal", "my lawyer will call"), ("s-guard", "status?")]:
        await rt.run(agent, sid, msg, "cust")
    return rt


async def test_facts_come_straight_from_recorded_traces():
    rt = await conversations()
    facts = {f.session_id: f for f in (facts_from_trace(t) for t in rt.traces._traces.values())}
    assert facts["s-ok"].tools == ["lookup_order"] and facts["s-ok"].status == "completed" and facts["s-ok"].first_message == "where is 1042?"
    assert facts["s-gap"].empty_searches == ["gift wrapping"]
    assert facts["s-handoff"].status == "escalated" and facts["s-legal"].status == "escalated"
    assert facts["s-guard"].guardrails == ["no-card-numbers"] and facts["s-ok"].duration >= 0


async def test_overview_over_real_conversations():
    rt = await conversations()
    fb = InMemoryFeedback()
    await fb.add("s-ok", 5, "great")
    svc = InsightsService(InMemoryInsightsSource(rt, fb))
    m = await svc.overview(time.time() - 3600, time.time() + 60)
    assert m["conversations"] == 5 and m["turns"] == 5 and m["containmentRate"]["numerator"] == 3  # two of five reached a person
    assert m["handoffs"]["byTrigger"] == {"agent_handoff": 1, "forced_topic": 1} and m["guardrails"] == {"no-card-numbers": 1}
    assert m["satisfaction"]["average"] == 5.0 and m["environment"] == "production" and m["truncated"] is False
    assert (await svc.overview(time.time() - 3600, time.time() + 60, agent="nobody"))["turns"] == 0
    assert (await svc.overview(time.time() - 3600, time.time() + 60, environment="staging"))["turns"] == 0
    assert (await svc.intent_gaps(time.time() - 3600, time.time() + 60))["unansweredSearches"] == [{"query": "gift wrapping", "count": 1}]
    causes = {r["cause"] for r in await svc.failure_analysis(time.time() - 3600, time.time() + 60)}
    assert {"hand-off: agent_handoff", "hand-off: forced_topic", "blocked by: no-card-numbers"} <= causes


async def test_postgres_gives_the_same_answers_as_memory(engine):
    from northcx import db
    from northcx.monitor import Monitor
    kb = InMemoryKnowledge()
    await kb.create_source(Source("help", "Help"))
    agent = Agent(id="support", instructions="i", tools=[*support_agent().tools, knowledge_tool(kb)], guardrails=support_agent().guardrails,
                  input_guardrails=support_agent().input_guardrails, forced_handoffs=support_agent().forced_handoffs)
    script = [tool_call("lookup_order", {"order_id": "1042"}, "a"), text("Delivered."), tool_call("search_knowledge", {"query": "gift wrapping"}, "b"), text("Not found."),
              tool_call("handoff_to_human", {"reason": "x"}, "c")]
    mem = Runtime(ScriptedLLM(list(script)), InMemoryStore(), TraceStore())
    pg = Runtime(ScriptedLLM(list(script)), db.PgMemoryStore(engine), db.PgTraceStore(engine), db.PgApprovalStore(engine), handoffs=db.PgHandoffs(engine),
                 monitor=Monitor(db.PgMonitor(engine)), privacy=db.PgPrivacy(engine))
    for rt in (mem, pg):
        for sid, msg in [("s-ok", "where is 1042?"), ("s-gap", "gift wrap?"), ("s-handoff", "person please")]:
            await rt.run(agent, sid, msg, "c")
    fb_m, fb_p = InMemoryFeedback(), db.PgFeedback(engine)
    for fb in (fb_m, fb_p):
        await fb.add("s-ok", 4, "fine")
        assert await fb.add("s-ok", 5, "better") is False  # a second rating replaces the first
    a = await InsightsService(InMemoryInsightsSource(mem, fb_m)).overview(time.time() - 3600, time.time() + 60)
    b = await InsightsService(db.PgInsightsSource(engine)).overview(time.time() - 3600, time.time() + 60)
    strip = lambda m: {k: v for k, v in m.items() if k not in ("latencySeconds", "period")}  # noqa: E731
    assert strip(a) == strip(b) and b["satisfaction"]["average"] == 5.0
    assert (await db.PgInsightsSource(engine).turns(0, time.time() + 60, "support", "production", 1))[0].session_id in {"s-ok", "s-gap", "s-handoff"}
    assert (await fb_p.for_session("s-ok")).comment == "better" and await fb_p.for_session("nope") is None
    assert await fb_p.erase_session("s-ok") == 1 and await fb_m.erase_session("s-ok") == 1 and await fb_p.erase_session("s-ok") == 0


# ---- API and privacy ----
KEY = "boot" * 10
H = {"authorization": f"Bearer {KEY}"}


def api():
    rt = asyncio.new_event_loop().run_until_complete(conversations())
    ac = AccessControl(bootstrap_key=KEY)
    return TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac)), ac, rt


def test_api_overview_series_failures_gaps_and_window_rules():
    c, ac, rt = api()
    o = c.get("/v1/insights/overview", headers=H).json()
    assert o["conversations"] == 5 and o["containmentRate"]["denominator"] == 5
    assert c.get("/v1/insights/overview?agent=nobody", headers=H).json()["turns"] == 0
    now = time.time()
    s = c.get(f"/v1/insights/timeseries?bucket=hour&from={now - 7200}&to={now + 60}", headers=H).json()
    assert s["bucket"] == "hour" and sum(p["turns"] for p in s["points"]) == 5
    assert c.get("/v1/insights/timeseries?bucket=week", headers=H).status_code == 400
    assert {"cause", "count", "share", "exampleTraceIds"} <= set(c.get("/v1/insights/failures", headers=H).json()["causes"][0])
    assert "unansweredSearches" in c.get("/v1/insights/gaps", headers=H).json()
    assert c.get(f"/v1/insights/overview?from={now}&to={now - 10}", headers=H).status_code == 400
    assert c.get(f"/v1/insights/overview?from=0&to={now}", headers=H).status_code == 400  # at most 366 days


def test_api_feedback_scope_and_permissions():
    c, ac, rt = api()
    token = c.post("/v1/chat-tokens", json={"sessionId": "s-ok", "customerId": "cust"}, headers=H).json()["token"]
    t = {"authorization": f"Bearer {token}"}
    assert c.post("/v1/sessions/s-ok/feedback", json={"rating": 5, "comment": "great"}, headers=t).status_code == 201
    again = c.post("/v1/sessions/s-ok/feedback", json={"rating": 4}, headers=t).json()
    assert again == {"saved": True, "replaced": True}
    assert c.post("/v1/sessions/s-gap/feedback", json={"rating": 1}, headers=t).status_code == 403  # another conversation
    assert c.post("/v1/sessions/never/feedback", json={"rating": 3}, headers=H).status_code == 404
    for bad in ({"rating": 0}, {"rating": 6}, {"rating": "great"}, {}):
        assert c.post("/v1/sessions/s-ok/feedback", json=bad, headers=H).status_code == 400
    assert c.get("/v1/insights/overview", headers=H).json()["satisfaction"]["average"] == 4.0
    assert c.get("/v1/insights/overview", headers=t).status_code == 403
    viewer = asyncio.new_event_loop().run_until_complete(ac.issue("v", "viewer", "root"))[1]
    assert c.get("/v1/insights/overview", headers={"authorization": f"Bearer {viewer}"}).status_code == 200
    assert c.post("/v1/sessions/s-ok/feedback", json={"rating": 1}, headers={"authorization": f"Bearer {viewer}"}).status_code == 403


def test_erasing_a_customer_removes_their_rating():
    c, ac, rt = api()
    c.post("/v1/sessions/s-ok/feedback", json={"rating": 5}, headers=H)
    assert c.get("/v1/insights/overview", headers=H).json()["satisfaction"]["responses"] == 1
    c.delete("/v1/privacy/customers/cust", headers=H)
    assert c.get("/v1/insights/overview", headers=H).json()["satisfaction"]["responses"] == 0


# ---- conversation search and tagging ----
@pytest.fixture(params=["memory", "postgres"])
def tag_repo(request):
    if request.param == "memory":
        from northcx.insights import InMemoryTags
        return InMemoryTags()
    from northcx.db import PgTags
    return PgTags(request.getfixturevalue("engine"))


async def test_tag_repository_contract(tag_repo):
    assert await tag_repo.add("s1", "wrong-answer", "rae") is True and await tag_repo.add("s1", "wrong-answer", "rae") is False
    await tag_repo.add("s1", "billing", "rae")
    await tag_repo.add("s2", "billing", "jo")
    assert await tag_repo.all_for("s1") == ["billing", "wrong-answer"] and await tag_repo.for_sessions(["s1", "s2", "s3"]) == {"s1": ["billing", "wrong-answer"], "s2": ["billing"]}
    assert await tag_repo.for_sessions([]) == {}
    assert await tag_repo.remove("s1", "billing") is True and await tag_repo.remove("s1", "billing") is False
    for i in range(18):
        await tag_repo.add("s9", f"t{i}", "x")
    await tag_repo.add("s9", "t18", "x")
    await tag_repo.add("s9", "t19", "x")
    with pytest.raises(ValueError, match="at most 20"):
        await tag_repo.add("s9", "t20", "x")
    assert await tag_repo.add("s9", "t0", "x") is False  # an existing tag is not an error at the limit
    assert await tag_repo.erase_session("s9") == 20 and await tag_repo.all_for("s9") == []


async def test_search_finds_text_in_what_either_side_said_and_filters():
    rt = await conversations()
    svc = InsightsService(InMemoryInsightsSource(rt, InMemoryFeedback()))
    from northcx.insights import InMemoryTags
    tags = InMemoryTags()
    await tags.add("s-gap", "needs-article", "rae")
    w = (time.time() - 3600, time.time() + 60)
    find = lambda **kw: svc.search(*w, tags, **kw)  # noqa: E731
    assert [r["sessionId"] for r in await find(q="gift")] == ["s-gap"]
    assert [r["sessionId"] for r in await find(q="DELIVERED")] == ["s-ok"]  # case-insensitive, and the agent's words count
    assert {r["sessionId"] for r in await find(handed_off=True)} == {"s-handoff", "s-legal"} and len(await find(handed_off=False)) == 3
    assert [r["sessionId"] for r in await find(tag="needs-article")] == ["s-gap"] and (await find(tag="needs-article"))[0]["tags"] == ["needs-article"]
    assert {r["sessionId"] for r in await find(status="escalated")} == {"s-handoff", "s-legal"}
    assert len(await find(limit=2)) == 2 and await find(q="no such words anywhere") == [] and await find(agent="nobody") == []
    row = (await find(q="lawyer"))[0]
    assert row["handedOff"] and row["handoffTriggers"] == ["forced_topic"] and row["turns"] == 1 and row["firstMessage"] == "my lawyer will call"


async def test_search_masks_personal_data_in_what_it_shows():
    rt = Runtime(ScriptedLLM([text("Noted, jane@example.com.")]), InMemoryStore(), TraceStore())
    await rt.run(support_agent(), "s1", "my email is jane@example.com and my ssn is 123-45-6789")
    svc = InsightsService(InMemoryInsightsSource(rt, InMemoryFeedback()))
    from northcx.insights import InMemoryTags
    row = (await svc.search(time.time() - 60, time.time() + 60, InMemoryTags()))[0]
    assert "jane@example.com" not in str(row) and "123-45-6789" not in str(row)


def test_api_search_and_tagging_with_permissions_audit_and_erasure():
    c, ac, rt = api()
    loop = asyncio.new_event_loop()
    r = c.get("/v1/conversations/search?q=gift", headers=H).json()["conversations"]
    assert [x["sessionId"] for x in r] == ["s-gap"]
    assert c.put("/v1/sessions/s-gap/tags/needs-article", headers=H).json()["tags"] == ["needs-article"]
    assert c.put("/v1/sessions/s-gap/tags/needs-article", headers=H).json()["added"] is False
    assert [x["sessionId"] for x in c.get("/v1/conversations/search?tag=needs-article", headers=H).json()["conversations"]] == ["s-gap"]
    assert c.get("/v1/sessions/s-gap/tags", headers=H).json()["tags"] == ["needs-article"]
    assert c.put("/v1/sessions/s-gap/tags/Bad Tag", headers=H).status_code == 400 and c.put("/v1/sessions/never/tags/x", headers=H).status_code == 404
    assert c.get("/v1/conversations/search?from=10&to=5", headers=H).status_code == 400 and c.get("/v1/conversations/search?q=" + "x" * 201, headers=H).status_code == 400
    key = lambda role: loop.run_until_complete(ac.issue(role, role, "root"))[1]  # noqa: E731
    for role, can_tag, can_search in [("reviewer", 200, 200), ("developer", 200, 200), ("viewer", 403, 200), ("auditor", 403, 200), ("channel", 403, 403)]:
        h = {"authorization": f"Bearer {key(role)}"}
        assert c.put("/v1/sessions/s-ok/tags/checked", headers=h).status_code == can_tag, role
        assert c.get("/v1/conversations/search", headers=h).status_code == can_search, role
    assert c.delete("/v1/sessions/s-ok/tags/checked", headers=H).json()["removed"] is True and c.delete("/v1/sessions/s-ok/tags/checked", headers=H).status_code == 404
    actions = [e["action"] for e in c.get("/v1/audit?limit=50", headers=H).json()["entries"]]
    assert "conversation.tag" in actions and "conversation.untag" in actions
    c.delete("/v1/privacy/customers/cust", headers=H)
    assert c.get("/v1/sessions/s-gap/tags", headers=H).json()["tags"] == []
