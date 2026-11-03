"""Business hours and queue routing."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.routing import Queue, Router, RoutingError, Schedule, load_router, parse_days, parse_windows
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

NY = ZoneInfo("America/New_York")


def at(y, m, d, h, mi=0, tz=NY):
    return datetime(y, m, d, h, mi, tzinfo=tz).timestamp()


def office():
    return Router("America/New_York", Schedule.from_config({"mon-fri": "09:00-17:00"}),
                  [Queue("billing", topics=["formal_complaint"], triggers=["budget_exceeded"], schedule=Schedule.from_config({"mon-fri": ["08:00-12:00", "13:00-20:00"], "sat": "10:00-14:00"})),
                   Queue("general")], "general", {datetime(2026, 12, 25).date()})


def test_days_and_windows():
    assert parse_days("mon-fri") == [0, 1, 2, 3, 4] and parse_days("sat,sun") == [5, 6] and parse_days("Fri-Mon") == [0, 4, 5, 6] and parse_days("wed") == [2]
    assert parse_windows("09:00-17:00") == [(540, 1020)] and parse_windows(["13:00-17:00", "09:00-12:00"]) == [(540, 720), (780, 1020)]
    assert parse_windows("00:00-24:00") == [(0, 1440)]
    for bad in ["9-17", "17:00-09:00", "09:00-09:00", "25:00-26:00", "09:60-10:00", "", [], 5]:
        with pytest.raises(RoutingError):
            parse_windows(bad)
    for bad in ["funday", "mon-xyz", ""]:
        with pytest.raises(RoutingError):
            parse_days(bad)


def test_open_and_closed_in_the_companys_time_zone():
    r = office()
    assert r.is_open("general", at(2026, 11, 3, 9, 0)) and r.is_open("general", at(2026, 11, 3, 16, 59))
    assert not r.is_open("general", at(2026, 11, 3, 8, 59)) and not r.is_open("general", at(2026, 11, 3, 17, 0))
    assert not r.is_open("general", at(2026, 11, 7, 12, 0))  # Saturday
    assert r.is_open("billing", at(2026, 11, 7, 12, 0)) and not r.is_open("billing", at(2026, 11, 3, 12, 30))  # billing's own hours, lunch break
    assert not r.is_open("general", at(2026, 12, 25, 10, 0)) and not r.is_open("billing", at(2026, 12, 25, 10, 0))  # holiday
    assert r.is_open("unknown-queue", at(2026, 11, 3, 10, 0))  # unknown queues use the default schedule


def test_daylight_saving_changes_follow_the_clock_not_utc():
    r = Router("America/New_York", Schedule.from_config({"mon-fri": "09:00-17:00"}))
    winter = datetime(2026, 11, 3, 14, 0, tzinfo=ZoneInfo("UTC")).timestamp()  # 09:00 EST
    summer = datetime(2026, 7, 7, 13, 0, tzinfo=ZoneInfo("UTC")).timestamp()  # 09:00 EDT
    assert r.is_open("x", winter) and r.is_open("x", summer)
    assert not r.is_open("x", datetime(2026, 7, 7, 12, 59, tzinfo=ZoneInfo("UTC")).timestamp())


def test_next_opening():
    r = office()
    assert r.next_open("general", at(2026, 11, 3, 18, 0)) == at(2026, 11, 4, 9, 0)  # Tuesday evening -> Wednesday morning
    assert r.next_open("general", at(2026, 11, 6, 18, 0)) == at(2026, 11, 9, 9, 0)  # Friday evening -> Monday
    assert r.next_open("billing", at(2026, 11, 3, 12, 30)) == at(2026, 11, 3, 13, 0)  # lunch break
    assert r.next_open("general", at(2026, 12, 24, 18, 0)) == at(2026, 12, 28, 9, 0)  # skips the holiday and the weekend
    assert r.next_open("general", at(2026, 11, 3, 8, 0)) == at(2026, 11, 3, 9, 0)
    assert Router().next_open("general") is None and Router().is_open("general")
    never = Router("UTC", Schedule.from_config({}))
    assert never.next_open("x", 0) is None and not never.is_open("x", 0)


def test_queue_matching_and_routes():
    r = office()
    assert r.queue_for(["formal_complaint"], "forced_topic") == "billing" and r.queue_for([], "budget_exceeded") == "billing"
    assert r.queue_for(["legal"], "forced_topic") == "general" and r.queue_for([], "agent_handoff") == "general"
    open_ = r.route([], "agent_handoff", at(2026, 11, 3, 10))
    assert open_.open_now and open_.message is None and open_.next_open is None
    closed = r.route([], "agent_handoff", at(2026, 11, 6, 20))
    assert not closed.open_now and closed.queue == "general" and closed.next_open == at(2026, 11, 9, 9)
    assert "Monday 09:00 America/New_York" in closed.message and "{when}" not in closed.message
    assert "Monday 08:00 America/New_York" in r.route(["formal_complaint"], "x", at(2026, 11, 7, 20)).message  # billing reopens earlier than general


def test_describe_reports_each_queue():
    d = office().describe(at(2026, 11, 3, 10))
    assert d["timezone"] == "America/New_York" and d["holidays"] == ["2026-12-25"]
    assert {q["name"]: q["open"] for q in d["queues"]} == {"billing": True, "general": True}
    d2 = office().describe(at(2026, 11, 6, 22))
    assert all(not q["open"] and q["nextOpen"] for q in d2["queues"])


def test_configuration_is_validated_in_one_pass(tmp_path):
    good = tmp_path / "r.yaml"
    good.write_text("""
timezone: Europe/Oslo
hours: {mon-fri: "08:00-16:00"}
holidays: [2026-12-25, 2026-12-26]
default_queue: general
after_hours_message: "We are closed{when}. Leave a message."
queues:
  - {name: billing, topics: [formal_complaint], hours: always}
  - {name: general}
""")
    r = load_router(good)
    assert r.tzname == "Europe/Oslo" and r.queue_for(["formal_complaint"], "x") == "billing" and r.is_open("billing", at(2026, 11, 7, 3))
    bad = tmp_path / "bad.yaml"
    bad.write_text("""
timezone: Mars/Olympus
hours: {funday: "9-17"}
holidays: [christmas]
colour: blue
queues:
  - {name: Bad Name}
  - {name: ok, hours: {mon: "17:00-09:00"}}
""")
    with pytest.raises(RoutingError) as e:
        load_router(bad)
    msg = str(e.value)
    assert all(s in msg for s in ["unknown setting 'colour'", "hours:", "christmas", "queue 1", "queue 'ok' hours"])
    for content, frag in [("timezone: Mars/Olympus\n", "unknown time zone"), ("queues: [{name: a}, {name: a}]\n", "unique"), ("queues: [{name: a}]\ndefault_queue: z\n", "default_queue"),
                          ("- not a map\n", "must be a map"), (": : :\n\t", "cannot read")]:
        p = tmp_path / "x.yaml"
        p.write_text(content)
        with pytest.raises(RoutingError, match=frag):
            load_router(p)
    with pytest.raises(RoutingError, match="cannot read"):
        load_router(tmp_path / "missing.yaml")


# ---- the runtime ----
def closed_router():
    return Router("UTC", Schedule.from_config({"mon-fri": "09:00-17:00"}), [Queue("billing", topics=["formal_complaint"]), Queue("general")], "general")


async def test_hand_offs_get_a_queue_and_the_customer_hears_when_to_expect_a_person(monkeypatch):
    llm = ScriptedLLM([tool_call("handoff_to_human", {"reason": "wants a person"}, "t1")])
    rt = Runtime(llm, InMemoryStore(), TraceStore(), router=closed_router())
    monkeypatch.setattr("northcx.routing.time.time", lambda: datetime(2026, 11, 7, 12, 0, tzinfo=ZoneInfo("UTC")).timestamp())  # Saturday
    r = await rt.run(support_agent(), "s1", "get me a person", "jane")
    assert r.status == "escalated" and "Monday 09:00 UTC" in r.reply and r.reply.startswith("I'm connecting you with a teammate")
    h = await rt.handoffs.get(r.handoff_id)
    assert h.queue == "general" and h.after_hours is True and h.package["routing"]["afterHours"] is True and h.package["routing"]["nextOpen"]
    saved = await rt.store.load_messages("s1")
    assert "Monday 09:00 UTC" in str(saved[-1]["content"])  # what the customer was told is what is on record


async def test_forced_topics_route_to_their_queue_and_open_hours_add_no_message(monkeypatch):
    monkeypatch.setattr("northcx.routing.time.time", lambda: datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("UTC")).timestamp())  # Tuesday noon
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore(), router=closed_router())
    r = await rt.run(support_agent(), "s1", "I want to file a formal complaint about this")
    h = await rt.handoffs.get(r.handoff_id)
    assert h.queue == "billing" and h.after_hours is False and "offline" not in r.reply and "reply when we reopen" not in r.reply
    assert [x.id for x in await rt.handoffs.list(queue="billing")] == [h.id] and await rt.handoffs.list(queue="general") == []


async def test_without_a_routing_file_nothing_changes():
    rt = Runtime(ScriptedLLM([tool_call("handoff_to_human", {"reason": "x"}, "t1")]), InMemoryStore(), TraceStore())
    r = await rt.run(support_agent(), "s", "person please")
    h = await rt.handoffs.get(r.handoff_id)
    assert h.queue == "general" and h.after_hours is False and "reopen" not in r.reply


async def test_queue_filter_and_columns_in_postgres(engine):
    from northcx import db
    from northcx.monitor import Monitor
    rt = Runtime(ScriptedLLM([tool_call("handoff_to_human", {"reason": "x"}, "t1")] * 2), db.PgMemoryStore(engine), db.PgTraceStore(engine), db.PgApprovalStore(engine),
                 handoffs=db.PgHandoffs(engine), router=closed_router(), monitor=Monitor(db.PgMonitor(engine)), privacy=db.PgPrivacy(engine))
    a = await rt.run(support_agent(), "s1", "person")
    b = await rt.run(support_agent(), "s2", "I want to file a formal complaint")
    got = await rt.handoffs.get(b.handoff_id)
    assert got.queue == "billing" and isinstance(got.after_hours, bool)
    assert [h.id for h in await rt.handoffs.list(queue="billing")] == [b.handoff_id]
    assert {h.id for h in await rt.handoffs.list()} == {a.handoff_id, b.handoff_id}


# ---- API ----
def test_api_exposes_queues_and_filters_hand_offs():
    rt = Runtime(ScriptedLLM([tool_call("handoff_to_human", {"reason": "x"}, "t1")]), InMemoryStore(), TraceStore(), router=closed_router())
    ac = AccessControl(bootstrap_key="boot" * 10)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    H = {"authorization": "Bearer " + "boot" * 10}
    c.post("/v1/agents/support/chat", json={"sessionId": "s1", "message": "person please"}, headers=H)
    c.post("/v1/agents/support/chat", json={"sessionId": "s2", "message": "I need to file a formal complaint"}, headers=H)
    assert [h["queue"] for h in c.get("/v1/handoffs?queue=billing", headers=H).json()["handoffs"]] == ["billing"]
    both = c.get("/v1/handoffs", headers=H).json()["handoffs"]
    assert {h["queue"] for h in both} == {"general", "billing"} and all("afterHours" in h for h in both)
    r = c.get("/v1/routing", headers=H).json()
    assert r["timezone"] == "UTC" and {q["name"] for q in r["queues"]} == {"billing", "general"} and "open" in r["queues"][0]
    viewer = asyncio.new_event_loop().run_until_complete(ac.issue("v", "viewer", "root"))[1]
    chan = asyncio.new_event_loop().run_until_complete(ac.issue("c", "channel", "root"))[1]
    assert c.get("/v1/routing", headers={"authorization": f"Bearer {viewer}"}).status_code == 200
    assert c.get("/v1/routing", headers={"authorization": f"Bearer {chan}"}).status_code == 403 and c.get("/v1/routing").status_code == 401
