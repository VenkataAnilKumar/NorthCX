"""Performance figures for staff (E15): what a person handled, and what the team handled, each with what it counts.

Hand-offs and approvals carry who decided them and when, so the figures come straight from those records. The team view is aggregated;
a person's own row is shown only to someone allowed to see individuals, and a handler with fewer than MIN_GROUP items in the period is
folded into "Others" so a small number cannot single anyone out.
"""
from __future__ import annotations

import time
from typing import Any

from .insights import percentile

MIN_GROUP = 5
APPROVED_STATES = {"approved", "executing", "executed", "failed"}   # an approved action moves on once it runs
DAY = 86400.0


def _times(items: list[tuple[float, float]]) -> dict[str, Any]:
    waits = [max(0.0, end - start) for start, end in items]
    return {"count": len(waits), "medianSeconds": percentile(waits, 0.5), "p90Seconds": percentile(waits, 0.9)}


def _series(stamps: list[float], since: float, days: int) -> list[dict[str, Any]]:
    out = [{"day": time.strftime("%Y-%m-%d", time.gmtime(since + i * DAY)), "count": 0} for i in range(days)]
    for s in stamps:
        i = int((s - since) // DAY)
        if 0 <= i < days:
            out[i]["count"] += 1
    return out


def figures(handoffs: list[Any], approvals: list[Any], me: str, since: float, until: float, individuals: bool, now: float | None = None,
            teams: dict[tuple[str, str], str] | None = None) -> dict[str, Any]:
    now = now or time.time()
    days = max(1, int(round((until - since) / DAY)))
    done_h = [h for h in handoffs if h.resolved_by and h.resolved_at and since <= h.resolved_at <= until]
    done_a = [a for a in approvals if a.decided_by and a.decided_at and since <= a.decided_at <= until and a.state != "expired"]
    open_h = [h for h in handoffs if not h.resolved_by and h.state == "open"]

    def mine(who: str) -> dict[str, Any]:
        hs = [h for h in done_h if h.resolved_by == who]
        ap = [a for a in done_a if a.decided_by == who]
        return {"handoffsResolved": len(hs), "approvalsDecided": len(ap), "approved": sum(a.state in APPROVED_STATES for a in ap), "rejected": sum(a.state == "rejected" for a in ap),
                "handoffTime": _times([(h.created_at, h.resolved_at) for h in hs]), "approvalTime": _times([(a.created_at, a.decided_at) for a in ap]),
                "series": _series([h.resolved_at for h in hs] + [a.decided_at for a in ap], since, days)}

    handlers: dict[str, int] = {}
    for h in done_h:
        handlers[h.resolved_by] = handlers.get(h.resolved_by, 0) + 1
    for a in done_a:
        handlers[a.decided_by] = handlers.get(a.decided_by, 0) + 1
    team: dict[str, Any] = {
        "handoffsResolved": len(done_h), "approvalsDecided": len(done_a), "handlers": len(handlers),
        "handoffTime": _times([(h.created_at, h.resolved_at) for h in done_h]), "approvalTime": _times([(a.created_at, a.decided_at) for a in done_a]),
        "openNow": len(open_h), "oldestOpenSeconds": round(now - min((h.created_at for h in open_h), default=now), 1) if open_h else None,
        "afterHours": sum(h.after_hours for h in done_h), "series": _series([h.resolved_at for h in done_h] + [a.decided_at for a in done_a], since, days),
    }
    if teams is not None:                                                  # figures by team; a team with fewer than MIN_GROUP items is folded into "Other teams"
        by: dict[str, dict[str, Any]] = {}
        for h in done_h:
            by.setdefault(teams.get(("handoff", h.id), "(no team)"), {"h": [], "a": []})["h"].append(h)
        for a in done_a:
            by.setdefault(teams.get(("approval", a.id), "(no team)"), {"h": [], "a": []})["a"].append(a)
        rows, small = [], {"h": [], "a": []}
        for name, v in sorted(by.items()):
            if len(v["h"]) + len(v["a"]) >= MIN_GROUP:
                rows.append({"team": name, "handoffsResolved": len(v["h"]), "approvalsDecided": len(v["a"]), "handoffTime": _times([(h.created_at, h.resolved_at) for h in v["h"]]),
                             "approvalTime": _times([(a.created_at, a.decided_at) for a in v["a"]])})
            else:
                small["h"] += v["h"]
                small["a"] += v["a"]
        if small["h"] or small["a"]:
            rows.append({"team": "Other teams (fewer than %d items each)" % MIN_GROUP, "handoffsResolved": len(small["h"]), "approvalsDecided": len(small["a"]),
                         "handoffTime": _times([(h.created_at, h.resolved_at) for h in small["h"]]), "approvalTime": _times([(a.created_at, a.decided_at) for a in small["a"]])})
        team["byTeam"] = rows
    if individuals:
        shown = sorted(((w, n) for w, n in handlers.items() if n >= MIN_GROUP), key=lambda x: -x[1])
        small = sum(n for w, n in handlers.items() if n < MIN_GROUP)
        team["people"] = [{"name": w, "items": n} for w, n in shown] + ([{"name": "Others (fewer than %d items each)" % MIN_GROUP, "items": small}] if small else [])
    return {"since": since, "until": until, "days": days, "mine": mine(me), "team": team, "individualsShown": individuals,
            "counts": {"handoffsResolved": "Hand-offs marked resolved in the period", "approvalsDecided": "Approvals approved or rejected in the period (expired ones are not counted)",
                       "handoffTime": "From the hand-off being opened to it being resolved", "approvalTime": "From the request to the decision"}}
