"""WP 6.6 (O8): a customer who comes back counts against the resolution figure; the old figure is unchanged and both show their denominators."""
import asyncio

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.insights import TurnFacts, compute, resolution, resolution_firm
from northcx.llm import ScriptedLLM, text
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

DAY = 86400.0
T0 = 1_800_000_000.0
UNTIL = T0 + 20 * DAY


def t(session, at, status="completed"):
    return TurnFacts(f"t-{session}-{at}", session, "support", "production", at, 1.0, status)


def figure(turns, customers, handed=()):
    return resolution_firm(turns, set(handed), UNTIL, customers)


def test_a_customer_who_starts_a_new_conversation_within_the_window_reopens_the_first_one():
    turns = [t("a1", T0), t("a2", T0 + 2 * DAY)]                    # the same customer again, two days later
    f = figure(turns, {"a1": "ann", "a2": "ann"})
    assert f["denominator"] == 2 and f["reopened"] == 1 and f["numerator"] == 1       # a1 is reopened by a2; a2 is quiet since
    assert resolution(turns, set(), UNTIL)["numerator"] == 2                           # the old figure counts both and is unchanged


def test_a_return_after_the_window_or_by_another_customer_does_not_count():
    after = [t("a1", T0), t("a2", T0 + 4 * DAY)]                    # four days: past the three-day window
    assert figure(after, {"a1": "ann", "a2": "ann"})["reopened"] == 0
    other = [t("a1", T0), t("b1", T0 + DAY)]
    f = figure(other, {"a1": "ann", "b1": "ben"})
    assert f["reopened"] == 0 and f["numerator"] == 2


def test_an_earlier_conversation_is_reopened_by_a_later_one_never_the_other_way_round():
    turns = [t("a1", T0 + DAY), t("a0", T0)]                        # the earlier conversation does not reopen the later one
    f = figure(turns, {"a1": "ann", "a0": "ann"})
    assert f["reopened"] == 1                                       # a0 (earlier) is reopened by a1 (later); a1 itself is not reopened by a0
    assert f["numerator"] == 1


def test_conversations_with_no_known_customer_cannot_be_checked_and_the_page_can_say_how_many():
    turns = [t("w1", T0), t("w2", T0 + DAY), t("a1", T0 + 2 * DAY)]
    f = figure(turns, {"a1": "ann"})
    assert f["checkable"] == 1 and f["reopened"] == 0 and f["numerator"] == 3 and f["denominator"] == 3


def test_a_conversation_that_was_not_resolved_in_the_first_place_stays_out_either_way():
    turns = [t("a1", T0, "escalated"), t("a2", T0 + DAY)]
    f = figure(turns, {"a1": "ann", "a2": "ann"})
    assert f["numerator"] == 1 and f["reopened"] == 0 and f["denominator"] == 2
    handed = figure([t("a1", T0), t("a2", T0 + DAY)], {"a1": "ann", "a2": "ann"}, handed=["a1"])
    assert handed["numerator"] == 1 and handed["reopened"] == 0


def test_the_overview_carries_both_figures_with_their_denominators_and_the_old_one_keeps_its_meaning():
    turns = [t("a1", T0), t("a2", T0 + DAY)]
    out = compute(turns, [], [], T0 - 1, UNTIL, customers={"a1": "ann", "a2": "ann"})
    assert out["resolutionRate"]["numerator"] == 2 and out["resolutionRate"]["provisional"] is True
    assert out["resolutionFirm"] == {"value": 0.5, "numerator": 1, "denominator": 2, "reopened": 1, "checkable": 2, "windowDays": 3.0}
    assert compute(turns, [], [], T0 - 1, UNTIL)["resolutionFirm"]["reopened"] == 0                    # no customer links: same as the old figure


def test_through_the_api_a_returning_customer_is_counted_once_the_conversations_are_old_enough():
    rt = Runtime(ScriptedLLM([text("Hello!")] * 4), InMemoryStore(), TraceStore())
    app = create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key="boot" * 10))
    loop = asyncio.new_event_loop()
    loop.run_until_complete(rt.run(support_agent(), "s-first", "hello", "cust-ann"))
    loop.run_until_complete(rt.run(support_agent(), "s-again", "hello again", "cust-ann"))
    loop.run_until_complete(rt.run(support_agent(), "s-anon", "hello", None))
    c = TestClient(app)
    import time
    future = time.time() + 10 * DAY
    out = c.get(f"/v1/insights/overview?from={time.time() - 3600}&to={future}", headers={"authorization": "Bearer " + "boot" * 10}).json()
    assert out["resolutionRate"]["denominator"] == 3 and out["resolutionRate"]["numerator"] == 3
    firm = out["resolutionFirm"]
    assert firm["denominator"] == 3 and firm["checkable"] == 2 and firm["reopened"] == 1 and firm["numerator"] == 2


def test_the_postgres_privacy_index_answers_which_customer_each_session_belongs_to(db_url):
    from sqlalchemy.pool import NullPool

    from northcx.db import create_engine
    from northcx.db.stores.privacy import PgPrivacy

    async def go():
        eng = create_engine(db_url, poolclass=NullPool)
        try:
            p = PgPrivacy(eng)
            await p.link("rf-1", "ann")
            await p.link("rf-2", "ann")
            await p.link("rf-3", None)
            return await p.customers_for_sessions(["rf-1", "rf-2", "rf-3", "rf-none"]), await p.customers_for_sessions([])
        finally:
            await eng.dispose()
    got, empty = asyncio.run(go())
    assert got == {"rf-1": "ann", "rf-2": "ann"} and empty == {}                                     # an anonymous session has no customer; an unknown one is left out
