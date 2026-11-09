"""E15: performance figures. Counts with what they count, aggregated by default, small groups folded, individual rows audited."""
import time

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.approvals import Approval
from northcx.handoffs import Handoff
from northcx.llm import ScriptedLLM
from northcx.performance import MIN_GROUP, figures
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

NOW = 1_000_000.0


def handoff(by, opened, took, after=False):
    h = Handoff("s", "t", "support", "x", "r", {}, created_at=opened, after_hours=after)
    if by:
        h.state, h.resolved_by, h.resolved_at = "resolved", by, opened + took
    return h


def approval(by, opened, took, state="approved"):
    return Approval("t", "s", "issue_refund", {}, "r", state=state, created_at=opened, decided_by=by, decided_at=opened + took)


def test_figures_count_what_they_say_and_separate_me_from_the_team():
    hs = [handoff("ann", NOW - 3600, 600), handoff("ann", NOW - 7200, 1200), handoff("ben", NOW - 5000, 300, after=True), handoff(None, NOW - 4000, 0)]
    ap = [approval("ann", NOW - 1000, 60, "executed"), approval("ann", NOW - 900, 120, "rejected"), approval("ben", NOW - 800, 30), approval("ben", NOW - 700, 30, "expired")]
    f = figures(hs, ap, "ann", NOW - 7 * 86400, NOW, False, now=NOW)
    assert f["mine"]["handoffsResolved"] == 2 and f["mine"]["approvalsDecided"] == 2 and f["mine"]["approved"] == 1 and f["mine"]["rejected"] == 1
    assert f["mine"]["handoffTime"]["medianSeconds"] == 900.0
    assert f["team"]["handoffsResolved"] == 3 and f["team"]["approvalsDecided"] == 3 and f["team"]["handlers"] == 2     # the expired approval is not a decision
    assert f["team"]["openNow"] == 1 and f["team"]["oldestOpenSeconds"] == 4000.0 and f["team"]["afterHours"] == 1
    assert "people" not in f["team"] and f["individualsShown"] is False and f["days"] == 7 and sum(d["count"] for d in f["team"]["series"]) == 6


def test_individual_rows_fold_small_counts_into_others():
    hs = [handoff("ann", NOW - 100 * i, 10) for i in range(1, MIN_GROUP + 1)] + [handoff("ben", NOW - 50, 10), handoff("cy", NOW - 60, 10)]
    f = figures(hs, [], "ann", NOW - 86400, NOW, True, now=NOW)
    names = [p["name"] for p in f["team"]["people"]]
    assert names[0] == "ann" and "ben" not in names and "cy" not in names and f["team"]["people"][-1]["items"] == 2


def test_api_individuals_need_the_audit_permission_and_are_audited():
    import asyncio
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key="boot" * 10)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    key = lambda n, r: {"authorization": "Bearer " + loop.run_until_complete(ac.issue(n, r, "t"))[1]}  # noqa: E731
    dev, aud = key("dev", "developer"), key("aud", "auditor")
    r = c.get("/v1/workspace/performance?days=7", headers=dev)
    assert r.status_code == 200 and r.json()["mine"]["handoffsResolved"] == 0 and r.json()["team"]["handlers"] == 0
    assert c.get("/v1/workspace/performance?days=0", headers=dev).status_code == 400
    assert c.get("/v1/workspace/performance?individuals=true", headers=dev).status_code == 403
    assert c.get("/v1/workspace/performance?individuals=true", headers=aud).json()["individualsShown"] is True
    actions = [e["action"] for e in c.get("/v1/audit?limit=10", headers={"authorization": "Bearer " + "boot" * 10}).json()["entries"]]
    assert "workspace.performance_individuals" in actions
    assert c.get("/v1/workspace/performance").status_code == 401


def test_figures_by_team_fold_small_teams_and_need_no_individual_names():
    hs = [handoff("ann", NOW - 100 * i, 60) for i in range(1, 6)] + [handoff("ben", NOW - 50, 30), handoff("cy", NOW - 60, 30)]
    ap = [approval("ann", NOW - 40, 10)]
    teams = {("handoff", h.id): "billing" for h in hs[:5]} | {("handoff", hs[5].id): "returns", ("handoff", hs[6].id): "returns", ("approval", ap[0].id): "billing"}
    f = figures(hs, ap, "ann", NOW - 86400, NOW, False, now=NOW, teams=teams)
    rows = {r["team"]: r for r in f["team"]["byTeam"]}
    assert rows["billing"]["handoffsResolved"] == 5 and rows["billing"]["approvalsDecided"] == 1 and rows["billing"]["handoffTime"]["medianSeconds"] == 60.0
    assert "returns" not in rows and rows["Other teams (fewer than 5 items each)"]["handoffsResolved"] == 2                    # two items: too few to show a team on its own
    assert "people" not in f["team"] and f["individualsShown"] is False
    assert "byTeam" not in figures(hs, ap, "ann", NOW - 86400, NOW, False, now=NOW)["team"]                                   # without team records there is no team table


def test_a_resolved_handoff_and_a_decided_approval_remember_the_team_of_whoever_answered():
    import asyncio
    from northcx.decision_teams import InMemoryTeams, NO_TEAM, team_of
    from northcx.access import Identity
    assert team_of(Identity("a", "reviewer", "k", groups=("returns", "billing"))) == "billing" and team_of(Identity("a", "reviewer", "k")) == NO_TEAM
    loop = asyncio.new_event_loop()
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    ac = AccessControl(bootstrap_key="boot" * 10)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    sso = {"authorization": "Bearer " + loop.run_until_complete(ac.issue_session("Rae", "reviewer", 8, groups=["returns"]))[1]}
    plain = {"authorization": "Bearer " + loop.run_until_complete(ac.issue("pat", "reviewer", "t"))[1]}
    h = loop.run_until_complete(rt.handoffs.add(Handoff("s1", "t1", "support", "customer_asked", "why", {})))
    h2 = loop.run_until_complete(rt.handoffs.add(Handoff("s2", "t2", "support", "customer_asked", "why", {})))
    assert c.post(f"/v1/handoffs/{h.id}/resolve", headers=sso, json={"note": "done"}).status_code == 200
    assert c.post(f"/v1/handoffs/{h2.id}/resolve", headers=plain, json={"note": "done"}).status_code == 200
    teams = loop.run_until_complete(rt.decision_teams.for_ids("handoff", [h.id, h2.id]))
    assert teams == {h.id: "returns", h2.id: "(no team)"}


async def test_the_team_record_survives_the_database_and_stays_in_its_tenant(app_engine):
    from northcx.db import PgTeams
    from northcx.tenancy import TENANT
    repo = PgTeams(app_engine)
    for tenant, team in (("acme", "billing"), ("globex", "returns")):
        token = TENANT.set(tenant)
        try:
            await repo.record("handoff", "h1", team)
            await repo.record("handoff", "h1", team)                     # recording again changes nothing
        finally:
            TENANT.reset(token)
    token = TENANT.set("acme")
    try:
        assert await repo.for_ids("handoff", ["h1", "h2"]) == {"h1": "billing"} and await repo.for_ids("approval", ["h1"]) == {}
    finally:
        TENANT.reset(token)
    token = TENANT.set("nobody")
    try:
        assert await repo.for_ids("handoff", ["h1"]) == {}
    finally:
        TENANT.reset(token)
