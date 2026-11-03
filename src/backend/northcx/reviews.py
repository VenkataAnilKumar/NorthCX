"""Conversation review (U4): people check what agents did, and the platform turns their judgements into quality numbers.

A review queue puts conversations that most need a human look first (hand-offs, low ratings, blocked or failed turns), plus a
small deterministic sample of the rest, because success measures that depend on correctness must not rely on automated checks alone.
A review records whether the agent was right, whether a hand-off was needed, what kind of failure it was, and a note.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .insights import FeedbackFacts, HandoffFacts, TurnFacts, mask, ratio

VERDICTS = ("correct", "wrong")
HANDOFF_JUDGEMENTS = ("needed", "unneeded", "not_applicable")
FAILURES = ("wrong_answer", "missed_policy", "hallucination", "bad_tone", "tool_misuse", "unneeded_handoff", "missed_handoff", "slow", "other")
LOW_RATING = 2
NOTE_MAX = 1000


class ReviewError(ValueError):
    pass


@dataclass
class Review:
    session_id: str
    verdict: str
    handoff: str
    failures: list[str]
    note: str
    reviewer: str
    reviewed_at: float = field(default_factory=time.time)


def validate(verdict: str, handoff: str, failures: list[str], note: str, handed_off: bool | None = None) -> tuple[str, str, list[str], str]:
    problems = []
    if verdict not in VERDICTS:
        problems.append(f"verdict must be one of {', '.join(VERDICTS)}")
    if handoff not in HANDOFF_JUDGEMENTS:
        problems.append(f"handoff must be one of {', '.join(HANDOFF_JUDGEMENTS)}")
    bad = [f for f in failures if f not in FAILURES]
    if bad:
        problems.append(f"unknown failure kind(s) {', '.join(bad)} (known: {', '.join(FAILURES)})")
    if verdict == "correct" and failures:
        problems.append("a conversation judged correct cannot also list failures")
    if verdict == "wrong" and not failures:
        problems.append("say what went wrong: choose at least one failure kind")
    if handed_off is False and handoff != "not_applicable":
        problems.append("this conversation was not handed to a person, so the hand-off judgement must be not_applicable")
    if handed_off is True and handoff == "not_applicable":
        problems.append("this conversation was handed to a person: say whether that was needed or unneeded")
    if len(note) > NOTE_MAX:
        problems.append(f"the note is longer than {NOTE_MAX} characters")
    if problems:
        raise ReviewError("; ".join(problems))
    return verdict, handoff, list(dict.fromkeys(failures)), note.strip()


class ReviewRepo(Protocol):
    async def put(self, review: Review) -> bool: ...  # True when new
    async def get(self, session_id: str) -> Review | None: ...
    async def between(self, since: float, until: float) -> list[Review]: ...
    async def for_sessions(self, session_ids: list[str]) -> dict[str, Review]: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryReviews:
    def __init__(self) -> None:
        self.items: dict[str, Review] = {}

    async def put(self, review: Review) -> bool:
        new = review.session_id not in self.items
        self.items[review.session_id] = review
        return new

    async def get(self, session_id) -> Review | None:
        return self.items.get(session_id)

    async def between(self, since, until) -> list[Review]:
        return [r for r in self.items.values() if since <= r.reviewed_at <= until]

    async def for_sessions(self, session_ids) -> dict[str, Review]:
        return {s: self.items[s] for s in session_ids if s in self.items}

    async def erase_session(self, session_id) -> int:
        return 1 if self.items.pop(session_id, None) else 0


def sampled(session_id: str, fraction: float) -> bool:
    """A fixed share of otherwise unremarkable conversations, chosen by their id so the same ones are always picked."""
    return fraction >= 1 or (fraction > 0 and int(hashlib.sha256(("review:" + session_id).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < fraction)


def queue(turns: list[TurnFacts], handoffs: list[HandoffFacts], feedback: list[FeedbackFacts], reviews: dict[str, Review],
          include_reviewed: bool = False, sample: float = 0.05, limit: int = 50) -> list[dict[str, Any]]:
    """Conversations to review, most worrying first. Each carries the reasons it is there."""
    by: dict[str, list[TurnFacts]] = {}
    for t in turns:
        by.setdefault(t.session_id, []).append(t)
    hands: dict[str, list[HandoffFacts]] = {}
    for h in handoffs:
        hands.setdefault(h.session_id, []).append(h)
    rating = {f.session_id: f.rating for f in feedback}
    rows = []
    for sid, ts in by.items():
        ts.sort(key=lambda t: t.started_at)
        reasons, weight = [], 0
        for h in hands.get(sid, []):
            reasons.append(f"handed to a person: {h.trigger}")
            weight += 3
        if rating.get(sid) is not None and rating[sid] <= LOW_RATING:
            reasons.append(f"rated {rating[sid]}/5")
            weight += 4
        if any(t.tool_errors for t in ts):
            reasons.append("a tool failed")
            weight += 2
        if any(t.errored and not t.tool_errors for t in ts):
            reasons.append("an error occurred")
            weight += 2
        if any(t.guardrails for t in ts):
            reasons.append("a check blocked something")
            weight += 1
        if not reasons:
            if not sampled(sid, sample):
                continue
            reasons.append("random sample")
        rev = reviews.get(sid)
        if rev is not None and not include_reviewed:
            continue
        last = ts[-1]
        rows.append({"sessionId": sid, "agentId": ts[0].agent_id, "turns": len(ts), "startedAt": ts[0].started_at, "endedAt": last.started_at + last.duration,
                     "lastStatus": last.status, "firstMessage": mask(ts[0].first_message, 200), "reasons": reasons, "weight": weight,
                     "handedOff": sid in hands, "rating": rating.get(sid), "review": review_json(rev) if rev else None})
    rows.sort(key=lambda r: (-r["weight"], -r["endedAt"]))
    return rows[:limit]


def review_json(r: Review) -> dict[str, Any]:
    return {"verdict": r.verdict, "handoff": r.handoff, "failures": r.failures, "note": r.note, "reviewer": r.reviewer, "reviewedAt": r.reviewed_at}


def quality(reviews: list[Review]) -> dict[str, Any]:
    """The success-metric numbers that need a human: how often the agent was right, and how often hand-offs were warranted."""
    handed = [r for r in reviews if r.handoff != "not_applicable"]
    kinds: dict[str, int] = {}
    for r in reviews:
        for f in r.failures:
            kinds[f] = kinds.get(f, 0) + 1
    return {"reviewed": len(reviews), "correctRate": ratio(sum(r.verdict == "correct" for r in reviews), len(reviews)),
            "escalationCorrectness": ratio(sum(r.handoff == "needed" for r in handed), len(handed)),
            "unneededEscalationRate": ratio(sum(r.handoff == "unneeded" for r in handed), len(handed)),
            "failuresByKind": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
            "note": "Figures cover only reviewed conversations, which are a mix of flagged ones and a random sample; flagged conversations are not representative of all traffic."}
