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
    ap = [approval("ann", NOW - 1000, 60), approval("ann", NOW - 900, 120, "rejected"), approval("ben", NOW - 800, 30), approval("ben", NOW - 700, 30, "expired")]
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
