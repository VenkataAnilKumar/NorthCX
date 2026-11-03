"""Handoff to a person: the package a human receives, and the queue it lands in.

The package is built deterministically from what the platform already knows (history, customer facts, the traces of
the session, approvals). It contains personal data, so access to it must be restricted like conversations are."""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .approvals import Approval
from .trace import Trace
from .types import Message

# Why a conversation reached a person.
TRIGGERS = {
    "agent_handoff": "The agent handed the conversation to a person",
    "forced_topic": "The message matched a topic that always goes to a person",
    "input_blocked": "The customer's message was blocked by an input policy",
    "supervisor_rejections": "The agent's replies were repeatedly rejected by supervisors",
    "step_limit": "The agent could not finish within its step limit",
    "model_error": "The model could not be reached",
    "approval_expired": "A held action was not approved in time",
    "budget_exceeded": "The model budget for this conversation or day was used up",
}
OPEN, RESOLVED = "open", "resolved"


@dataclass
class Handoff:
    session_id: str
    trace_id: str
    agent_id: str
    trigger: str
    reason: str
    package: dict[str, Any]
    customer_id: str | None = None
    topics: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: str = OPEN
    created_at: float = field(default_factory=time.time)
    resolved_by: str | None = None
    resolved_at: float | None = None
    note: str | None = None
    queue: str | None = None
    after_hours: bool = False  # the team was offline when this arrived


class HandoffRepo(Protocol):
    async def add(self, handoff: Handoff) -> Handoff: ...
    async def get(self, handoff_id: str) -> Handoff | None: ...
    async def list(self, state: str | None = None, session_id: str | None = None, limit: int = 200, queue: str | None = None) -> list[Handoff]: ...
    async def resolve(self, handoff_id: str, by: str, note: str | None = None) -> Handoff: ...


class InMemoryHandoffs:
    def __init__(self) -> None:
        self._items: dict[str, Handoff] = {}

    async def add(self, handoff: Handoff) -> Handoff:
        self._items[handoff.id] = handoff
        return handoff

    async def get(self, handoff_id: str) -> Handoff | None:
        return self._items.get(handoff_id)

    async def list(self, state: str | None = None, session_id: str | None = None, limit: int = 200, queue: str | None = None) -> list[Handoff]:
        items = [h for h in self._items.values() if (not state or h.state == state) and (not session_id or h.session_id == session_id)
                 and (not queue or h.queue == queue)]
        return sorted(items, key=lambda h: h.created_at, reverse=True)[:limit]

    async def resolve(self, handoff_id: str, by: str, note: str | None = None) -> Handoff:
        h = self._items.get(handoff_id)
        if h is None:
            raise KeyError(f"Unknown handoff {handoff_id}")
        if h.state != OPEN:
            raise ValueError(f"Handoff {handoff_id} already {h.state}")
        h.state, h.resolved_by, h.resolved_at, h.note = RESOLVED, by, time.time(), note
        return h


def transcript(messages: list[Message]) -> list[dict[str, str]]:
    """What was said, in order. Tool plumbing is left out; actions are listed separately."""
    out: list[dict[str, str]] = []
    for m in messages:
        c = m["content"]
        if m["role"] == "user":
            if isinstance(c, str):
                if c.startswith("[summary]") and "[/summary]" in c:  # earlier turns were summarised to save space
                    note, _, rest = c.removeprefix("[summary]").partition("[/summary]")
                    out.append({"from": "platform", "text": "Earlier in this conversation: " + note.strip()})
                    if rest.strip():
                        out.append({"from": "customer", "text": rest.strip()})
                elif c.startswith("[system]"):
                    out.append({"from": "platform", "text": c.removeprefix("[system]").strip()})
                elif not c.startswith("[supervisor]"):
                    out.append({"from": "customer", "text": c})
        elif isinstance(c, str):
            out.append({"from": "agent", "text": c})
        else:
            text = "".join(b.get("text", "") for b in c if b.get("type") == "text").strip()
            if text:
                out.append({"from": "agent", "text": text})
    return out


def actions(traces: list[Trace]) -> list[dict[str, Any]]:
    """Every tool call the agent attempted in the session, with what happened to it."""
    found: list[dict[str, Any]] = []
    for trace in traces:
        ev = trace.events
        for i, e in enumerate(ev):
            if e.type != "tool_call" or e.data.get("name") == "handoff_to_human":
                continue
            outcome, detail = "not executed", None
            for nxt in ev[i + 1:]:
                if nxt.type in ("tool_call", "llm", "reply"):
                    break
                if nxt.type == "tool_result" and nxt.data.get("name") == e.data["name"]:
                    outcome, detail = ("simulated" if nxt.data.get("dry_run") else "succeeded"), nxt.data.get("output")
                    break
                if nxt.type == "error" and nxt.data.get("tool") == e.data["name"]:
                    outcome, detail = "failed", nxt.data.get("error")
                    break
                if nxt.type == "approval":
                    outcome, detail = "held for approval", nxt.data.get("reason")
                    break
                if nxt.type == "guardrail":
                    outcome, detail = "blocked by policy", nxt.data.get("reason")
                    break
            found.append({"tool": e.data["name"], "input": e.data.get("input"), "outcome": outcome,
                          "detail": detail, "traceId": trace.id, "at": e.t})
    return found


def summarize(trigger: str, reason: str, msgs: list[dict[str, str]], acts: list[dict[str, Any]],
              approvals: list[Approval]) -> str:
    parts = [f"{TRIGGERS.get(trigger, trigger)}." + (f" Reason: {reason}." if reason else "")]
    last = next((m["text"] for m in reversed(msgs) if m["from"] == "customer"), None)
    if last:
        parts.append("Customer's last message: “" + (last if len(last) <= 200 else last[:197] + "...") + "”.")
    if acts:
        parts.append("Actions: " + "; ".join(f"{a['tool']} {a['outcome']}" for a in acts[-6:]) + ".")
    pending = [a for a in approvals if a.state == "pending"]
    if pending:
        parts.append(f"{len(pending)} approval(s) still pending: " + ", ".join(a.tool for a in pending) + ".")
    return " ".join(parts)


def build_package(*, messages: list[Message], traces: list[Trace], approvals: list[Approval], facts: dict[str, str],
                  trigger: str, reason: str, topics: list[str]) -> dict[str, Any]:
    msgs = transcript(messages)
    acts = actions(traces)
    return {
        "summary": summarize(trigger, reason, msgs, acts, approvals),
        "trigger": trigger,
        "triggerDescription": TRIGGERS.get(trigger, trigger),
        "reason": reason,
        "topics": topics,
        "transcript": msgs,
        "customerFacts": facts,
        "actions": acts,
        "approvals": [{"id": a.id, "tool": a.tool, "state": a.state, "reason": a.reason, "input": a.input,
                       "note": a.note, "result": a.result} for a in approvals],
    }


@dataclass
class ForcedTopic:
    """A topic that always goes to a person (for example legal threats). Matching is deterministic."""

    name: str
    patterns: list[str]
    reply: str = "I'm connecting you with a person who can help with this."

    def __post_init__(self) -> None:
        if not self.patterns:
            raise ValueError(f"Forced topic '{self.name}' needs at least one pattern")
        self._compiled = []
        for p in self.patterns:
            if len(p) > 300:
                raise ValueError(f"Forced topic '{self.name}': pattern is too long (limit 300 characters)")
            try:
                self._compiled.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                raise ValueError(f"Forced topic '{self.name}': invalid pattern {p!r}: {e}") from e

    def matches(self, text: str) -> bool:
        return any(c.search(text) for c in self._compiled)
