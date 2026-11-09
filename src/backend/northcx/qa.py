"""Quality: score conversations against a rubric, check the scores against people, and keep coaching notes (E7).

A rubric is a list of deterministic checks, each with a weight. Scoring needs no model: every check looks at facts already recorded about the
conversation (hand-offs, tool errors, blocked replies, the customer's rating, wording of the last reply). A check that does not apply to a
conversation (for example a rating nobody gave) is left out, not counted as a pass. Reviewers' verdicts are the check on the scores: calibration
shows how often the score and the person agree, and which conversations they disagree on.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .budget_settings import InMemorySettings, SettingsRepo
from .insights import HandoffFacts, TurnFacts, ratio
from .tenancy import current_tenant

KEY = "qa_rubric"
CACHE_SECONDS = 5.0
MAX_CRITERIA = 20
CHECKS = {
    "no_tool_errors": "No tool failed",
    "no_errors": "No error occurred",
    "no_guardrail_blocks": "No check blocked a reply",
    "no_handoff": "Handled without passing to a person",
    "rating_at_least": "The customer's rating was at least {n} (left out when nobody rated)",
    "within_turns": "Finished within {n} customer messages",
    "reply_excludes": "The last reply avoids these phrases",
    "reply_includes": "The last reply includes one of these phrases",
}
NEEDS_N = {"rating_at_least": (1, 5), "within_turns": (1, 100)}
NEEDS_PHRASES = {"reply_excludes", "reply_includes"}


class QAError(ValueError):
    pass


DEFAULT_RUBRIC: dict[str, Any] = {
    "criteria": [
        {"id": "tools", "label": "No tool failed", "weight": 3, "check": "no_tool_errors"},
        {"id": "errors", "label": "No error occurred", "weight": 3, "check": "no_errors"},
        {"id": "blocked", "label": "No check blocked a reply", "weight": 2, "check": "no_guardrail_blocks"},
        {"id": "rating", "label": "Rated 4 or more", "weight": 3, "check": "rating_at_least", "n": 4},
        {"id": "short", "label": "Finished within 8 messages", "weight": 1, "check": "within_turns", "n": 8},
    ],
    "passMark": 70, "sample": 0.1,
}


def validate_rubric(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise QAError("A rubric is a mapping")
    crit = data.get("criteria")
    if not isinstance(crit, list) or not 1 <= len(crit) <= MAX_CRITERIA:
        raise QAError(f"A rubric needs between 1 and {MAX_CRITERIA} criteria")
    out, seen = [], set()
    for i, c in enumerate(crit, 1):
        if not isinstance(c, dict):
            raise QAError(f"Criterion {i} must be a mapping")
        cid, label, w, check = c.get("id"), c.get("label"), c.get("weight", 1), c.get("check")
        if not isinstance(cid, str) or not cid.replace("_", "").replace("-", "").isalnum() or not 1 <= len(cid) <= 30 or cid in seen:
            raise QAError(f"Criterion {i}: give a unique id of letters, digits, - or _ (up to 30 characters)")
        seen.add(cid)
        if not isinstance(label, str) or not 3 <= len(label.strip()) <= 120:
            raise QAError(f"Criterion '{cid}': the label must be 3 to 120 characters")
        if isinstance(w, bool) or not isinstance(w, int) or not 1 <= w <= 10:
            raise QAError(f"Criterion '{cid}': the weight is a whole number from 1 to 10")
        if check not in CHECKS:
            raise QAError(f"Criterion '{cid}': unknown check '{check}' (checks: {', '.join(CHECKS)})")
        item: dict[str, Any] = {"id": cid, "label": label.strip(), "weight": w, "check": check}
        if check in NEEDS_N:
            lo, hi = NEEDS_N[check]
            n = c.get("n")
            if isinstance(n, bool) or not isinstance(n, int) or not lo <= n <= hi:
                raise QAError(f"Criterion '{cid}': n must be a whole number from {lo} to {hi}")
            item["n"] = n
        if check in NEEDS_PHRASES:
            ph = c.get("phrases")
            if not isinstance(ph, list) or not 1 <= len(ph) <= 20 or not all(isinstance(p, str) and 2 <= len(p.strip()) <= 80 for p in ph):
                raise QAError(f"Criterion '{cid}': give 1 to 20 phrases of 2 to 80 characters")
            item["phrases"] = [p.strip() for p in ph]
        out.append(item)
    mark, sample = data.get("passMark", 70), data.get("sample", 0.1)
    if isinstance(mark, bool) or not isinstance(mark, (int, float)) or not 1 <= mark <= 100:
        raise QAError("The pass mark is a number from 1 to 100")
    if isinstance(sample, bool) or not isinstance(sample, (int, float)) or not 0 <= sample <= 1:
        raise QAError("The sample is a share between 0 and 1")
    return {"criteria": out, "passMark": float(mark), "sample": float(sample)}


def score(turns: list[TurnFacts], handoffs: list[HandoffFacts], rating: int | None, rubric: dict[str, Any]) -> dict[str, Any]:
    """Score one conversation. Returns the score (0 to 100, or None when no check applied) and each check's result with its reason."""
    ts = sorted(turns, key=lambda t: t.started_at)
    last = ts[-1].last_reply.lower() if ts else ""
    results = []
    for c in rubric["criteria"]:
        k = c["check"]
        if k == "no_tool_errors":
            ok = not any(t.tool_errors for t in ts)
            why = None if ok else "a tool failed"
        elif k == "no_errors":
            ok = not any(t.errored for t in ts)
            why = None if ok else "an error occurred"
        elif k == "no_guardrail_blocks":
            ok = not any(t.guardrails for t in ts)
            why = None if ok else "a check blocked a reply"
        elif k == "no_handoff":
            ok = not handoffs
            why = None if ok else "handed to a person"
        elif k == "rating_at_least":
            if rating is None:
                results.append({"id": c["id"], "label": c["label"], "weight": c["weight"], "result": "na", "reason": "no rating given"})
                continue
            ok, why = rating >= c["n"], None if rating >= c["n"] else f"rated {rating}"
        elif k == "within_turns":
            ok, why = len(ts) <= c["n"], None if len(ts) <= c["n"] else f"{len(ts)} messages"
        elif k == "reply_excludes":
            hit = next((p for p in c["phrases"] if p.lower() in last), None)
            ok, why = hit is None, None if hit is None else f"used '{hit}'"
        else:  # reply_includes
            ok, why = any(p.lower() in last for p in c["phrases"]), "none of the phrases appear"
            why = None if ok else why
        results.append({"id": c["id"], "label": c["label"], "weight": c["weight"], "result": "pass" if ok else "fail", "reason": why})
    got = sum(r["weight"] for r in results if r["result"] == "pass")
    total = sum(r["weight"] for r in results if r["result"] != "na")
    return {"score": round(100 * got / total, 1) if total else None, "criteria": results}


def calibration(scored: dict[str, float | None], verdicts: dict[str, str], pass_mark: float) -> dict[str, Any]:
    """How often the automatic score and a reviewer's verdict agree, over conversations that have both."""
    both = [(sid, s, verdicts[sid]) for sid, s in scored.items() if s is not None and sid in verdicts]
    agree, disagree = [], []
    for sid, s, v in both:
        (agree if (s >= pass_mark) == (v == "correct") else disagree).append({"sessionId": sid, "score": s, "verdict": v})
    return {"compared": len(both), "agreement": ratio(len(agree), len(both)), "scoreSaidGoodReviewerSaidWrong": sum(d["score"] >= pass_mark for d in disagree),
            "scoreSaidBadReviewerSaidCorrect": sum(d["score"] < pass_mark for d in disagree), "disagreements": sorted(disagree, key=lambda d: d["score"])[:25],
            "note": "Only conversations that have both a score and a reviewer's verdict are compared. Review a mix, not only flagged ones, or the agreement will not reflect normal traffic."}


class RubricService:
    """The rubric in force for this organization, kept in the per-tenant settings; a default applies until one is saved."""

    def __init__(self, repo: SettingsRepo | None = None):
        self.repo = repo or InMemorySettings()
        self._cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

    async def stored(self) -> dict[str, Any] | None:
        t = current_tenant()
        hit = self._cache.get(t)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        try:
            v = await self.repo.get(KEY)
        except Exception:  # noqa: BLE001 - the default rubric keeps working if the setting cannot be read
            return hit[1] if hit else None
        self._cache[t] = (time.monotonic(), v)
        return v

    async def get(self) -> dict[str, Any]:
        s = await self.stored()
        return {**(s or DEFAULT_RUBRIC), "version": (s or {}).get("version", 0), "isDefault": s is None}

    async def put(self, data: dict[str, Any], by: str) -> dict[str, Any]:
        clean = validate_rubric(data)
        cur = await self.stored()
        clean["version"] = (cur or {}).get("version", 0) + 1
        await self.repo.put(KEY, clean, by)
        self._cache.pop(current_tenant(), None)
        return {**clean, "isDefault": False}

    async def reset(self) -> bool:
        gone = await self.repo.delete(KEY)
        self._cache.pop(current_tenant(), None)
        return gone


@dataclass
class CoachingNote:
    session_id: str
    about: str                  # who or what the note is about: a person's name or an agent id
    note: str
    author: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "sessionId": self.session_id, "about": self.about, "note": self.note, "author": self.author, "createdAt": self.created_at}


class CoachingRepo(Protocol):
    async def add(self, n: CoachingNote) -> None: ...
    async def list(self, session_id: str | None = None, about: str | None = None, limit: int = 100) -> list[CoachingNote]: ...
    async def delete(self, note_id: str) -> bool: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryCoaching:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], CoachingNote] = {}

    async def add(self, n: CoachingNote) -> None:
        self._items[(current_tenant(), n.id)] = n

    async def list(self, session_id: str | None = None, about: str | None = None, limit: int = 100) -> list[CoachingNote]:
        t = current_tenant()
        rows = [n for (tt, _), n in self._items.items() if tt == t and (session_id is None or n.session_id == session_id) and (about is None or n.about == about)]
        return sorted(rows, key=lambda n: -n.created_at)[:limit]

    async def delete(self, note_id: str) -> bool:
        return self._items.pop((current_tenant(), note_id), None) is not None

    async def erase_session(self, session_id: str) -> int:
        t = current_tenant()
        gone = [k for k, n in self._items.items() if k[0] == t and n.session_id == session_id]
        for k in gone:
            del self._items[k]
        return len(gone)
