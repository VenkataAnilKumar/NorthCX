"""Shadow mode: the agent drafts each reply, a person sends it, edits it or rejects it, and the customer sees only what a person approved.

Design and requirements: docs/01-chat/NorthCX_Shadow-Mode.md. The runtime stores a draft instead of returning the reply (an empty reply is
never sent by any channel) and holds every action that changes something as an approval. This module holds the drafts and the decisions."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .catalog import AgentUnavailable, as_provider
from .insights import ratio
from .trace import Trace

PENDING, SENT, EDITED, REJECTED, EXPIRED = "pending", "sent", "edited", "rejected", "expired"
STATES = (PENDING, SENT, EDITED, REJECTED, EXPIRED)
ACTION_STATE = {"send": SENT, "edit": EDITED, "reject": REJECTED}
REASON = "Shadow mode: a person approves every action"
REJECT_REASONS = ("wrong", "tone", "incomplete", "unsafe", "other")  # a short list, so the figures can be read; the note takes the rest
NOT_SENT = "[No reply was sent for this message.]"  # what the conversation history keeps in place of a draft nobody sent
EXPIRED_REPLY = "Thanks for waiting. I'm connecting you with a person who can help."
MAX_TEXT = 4000


class ShadowError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class ShadowDraft:
    session_id: str
    agent_id: str
    trace_id: str
    customer_message: str
    draft: str
    agent_version: int | None = None
    customer_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: str = PENDING
    final_text: str | None = None
    reasons: list[str] = field(default_factory=list)
    note: str | None = None
    decided_by: str | None = None
    decided_at: float | None = None
    created_at: float = field(default_factory=time.time)


class ShadowRepo(Protocol):
    """Every transition is atomic, so two people cannot both decide one draft."""

    async def add(self, **kw: Any) -> ShadowDraft: ...
    async def get(self, draft_id: str) -> ShadowDraft | None: ...
    async def list(self, state: str | None = None, since: float | None = None, session_id: str | None = None, limit: int = 500) -> list[ShadowDraft]: ...
    async def decide(self, draft_id: str, state: str, by: str, final_text: str | None, reasons: list[str], note: str | None) -> ShadowDraft: ...
    async def expire(self, draft_id: str) -> ShadowDraft | None: ...
    async def erase_session(self, session_id: str) -> int: ...


class InMemoryShadowDrafts:
    def __init__(self) -> None:
        self._items: dict[str, ShadowDraft] = {}

    async def add(self, **kw: Any) -> ShadowDraft:
        d = ShadowDraft(**kw)
        self._items[d.id] = d
        return d

    async def get(self, draft_id: str) -> ShadowDraft | None:
        return self._items.get(draft_id)

    async def list(self, state: str | None = None, since: float | None = None, session_id: str | None = None, limit: int = 500) -> list[ShadowDraft]:
        found = [d for d in self._items.values() if (not state or d.state == state) and (since is None or d.created_at >= since) and (not session_id or d.session_id == session_id)]
        return sorted(found, key=lambda d: d.created_at)[:limit]

    async def decide(self, draft_id: str, state: str, by: str, final_text: str | None, reasons: list[str], note: str | None) -> ShadowDraft:
        d = self._items.get(draft_id)
        if d is None:
            raise KeyError(draft_id)
        if d.state != PENDING:
            raise ValueError(f"Draft {draft_id} is already {d.state}")
        d.state, d.decided_by, d.decided_at, d.final_text, d.reasons, d.note = state, by, time.time(), final_text, list(reasons), note
        return d

    async def expire(self, draft_id: str) -> ShadowDraft | None:
        d = self._items.get(draft_id)
        if d is None or d.state != PENDING:
            return None
        d.state, d.decided_at = EXPIRED, time.time()
        return d

    async def erase_session(self, session_id: str) -> int:
        gone = [k for k, d in self._items.items() if d.session_id == session_id]
        for k in gone:
            del self._items[k]
        return len(gone)


def draft_json(d: ShadowDraft) -> dict[str, Any]:
    return {"id": d.id, "sessionId": d.session_id, "agentId": d.agent_id, "agentVersion": d.agent_version, "traceId": d.trace_id, "customerMessage": d.customer_message,
            "draft": d.draft, "state": d.state, "finalText": d.final_text, "reasons": d.reasons, "note": d.note, "decidedBy": d.decided_by, "decidedAt": d.decided_at, "createdAt": d.created_at}


def _text_of(content: Any) -> str | None:
    """The words of a stored assistant turn: a plain string, or the text blocks of the model's own turn. A turn with a tool call is not a reply."""
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and all(isinstance(b, dict) and b.get("type") == "text" for b in content):
        return "".join(str(b.get("text", "")) for b in content)
    return None


def _swap_in_history(messages: list[dict[str, Any]], draft: str, replacement: str) -> bool:
    """Put what was really sent (or a note that nothing was) where the draft is in the stored conversation, so the next turn builds on what the customer saw."""
    for m in reversed(messages):
        if m.get("role") == "assistant" and _text_of(m.get("content")) == draft:
            m["content"] = replacement
            return True
    return False


class ShadowFlow:
    def __init__(self, runtime: Any):
        self.rt = runtime

    async def decide(self, agents: Any, draft_id: str, action: str, by: str, text: str | None = None, reasons: list[str] | None = None, note: str | None = None) -> ShadowDraft:
        """Send as is, edit and send, or reject. Raises ShadowError with what the person should do next."""
        if action not in ACTION_STATE:
            raise ShadowError(400, "action must be send, edit or reject")
        reasons = list(dict.fromkeys(reasons or []))
        bad = [r for r in reasons if r not in REJECT_REASONS]
        if bad or len(reasons) > 5:
            raise ShadowError(400, f"reasons must come from: {', '.join(REJECT_REASONS)}")
        d = await self.rt.shadow.get(draft_id)
        if d is None:
            raise ShadowError(404, "Unknown draft")
        if d.state != PENDING:
            raise ShadowError(409, f"This draft was already {d.state}. Nothing was sent from here.")
        final = d.draft if action == "send" else None
        if action == "edit":
            final = self.rt.secrets.redact_text((text or "").strip())
            if not final:
                raise ShadowError(400, "Write the reply to send, or choose Reject")
            if len(final) > MAX_TEXT:
                raise ShadowError(400, f"The reply is longer than {MAX_TEXT} characters; shorten it")
            if final == d.draft:
                raise ShadowError(400, "The text is the same as the draft; choose Send as is")
            await self._check_edit(agents, d, final)
        try:
            done = await self.rt.shadow.decide(draft_id, ACTION_STATE[action], by, final, reasons, note)
        except ValueError:
            raise ShadowError(409, "Someone decided this draft first. Nothing was sent from here.") from None
        messages = await self.rt.store.load_messages(d.session_id)
        if _swap_in_history(messages, d.draft, final if final is not None else NOT_SENT):
            await self.rt.store.save_messages(d.session_id, messages)
        trace = await self.rt.traces.get(d.trace_id)
        if trace is not None:
            trace.add("shadow_decision", draft=d.id, action=action, reasons=reasons)
            await self.rt.traces.save(trace)
        if final is not None:
            await self.rt.outbox.publish(d.session_id, "shadow_reply", {"draftId": d.id, "reply": final, "status": "completed", "traceId": d.trace_id, "edited": action == "edit"})
        return done

    async def _check_edit(self, agents: Any, d: ShadowDraft, final: str) -> None:
        """A person's edit is customer-facing text: it meets the agent's reply checks like the agent's own would."""
        try:
            agent = await as_provider(agents).get(d.agent_id, "production", d.session_id)
        except AgentUnavailable as e:
            raise ShadowError(409, f"The agent is not available, so an edit cannot be checked ({e}). Send the draft or try again later") from None
        if agent is None:
            raise ShadowError(409, "The agent no longer exists, so an edit cannot be checked. Send the draft or reject it")
        trace = await self.rt.traces.get(d.trace_id) or Trace(d.agent_id, d.session_id)
        blocked = await self.rt._check(agent, "reply", final, d.session_id, await self.rt.store.load_messages(d.session_id), trace,
                                       {"customer_id": d.customer_id, "facts": {}, "channel": None})
        if blocked:
            raise ShadowError(400, f"A check stopped this reply: {blocked}. Change the text and try again")

    async def expire_stale(self, agents: Any, ttl_seconds: float, now: float | None = None) -> list[ShadowDraft]:
        """Expire drafts nobody decided within the limit and hand each conversation to a person."""
        cutoff = (now if now is not None else time.time()) - ttl_seconds
        expired = []
        for d in await self.rt.shadow.list(PENDING):
            if d.created_at > cutoff:
                continue
            done = await self.rt.shadow.expire(d.id)  # None if a person decided it in the meantime
            if done is None:
                continue
            expired.append(done)
            messages = await self.rt.store.load_messages(done.session_id)
            _swap_in_history(messages, done.draft, EXPIRED_REPLY)
            await self.rt.store.save_messages(done.session_id, messages)
            trace = await self.rt.traces.get(done.trace_id) or Trace(done.agent_id, done.session_id)
            trace.add("shadow_decision", draft=done.id, action="expired", reasons=[])
            await self.rt.traces.save(trace)
            handoff = await self.rt.create_handoff(agent_id=done.agent_id, session_id=done.session_id, customer_id=done.customer_id, trace=trace, messages=messages,
                                                   trigger="shadow_expired", reason="No one reviewed the agent's draft in time", topics=[])
            await self.rt.outbox.publish(done.session_id, "shadow_expired", {"handoffId": handoff.id, "draftId": done.id, "reply": EXPIRED_REPLY, "status": "escalated", "traceId": done.trace_id})
        return expired

    async def summary(self, since: float | None = None, agent: str | None = None) -> dict[str, Any]:
        """How often people changed what the agent wrote. Counts and a ratio with its denominator; not a measure of whether the agent was right."""
        items = [d for d in await self.rt.shadow.list(since=since, limit=100000) if not agent or d.agent_id == agent]
        n = {s: sum(d.state == s for d in items) for s in STATES}
        decided = n[SENT] + n[EDITED] + n[REJECTED] + n[EXPIRED]
        reasons: dict[str, int] = {}
        for d in items:
            for r in d.reasons:
                reasons[r] = reasons.get(r, 0) + 1
        return {"total": len(items), "pending": n[PENDING], "sent": n[SENT], "edited": n[EDITED], "rejected": n[REJECTED], "expired": n[EXPIRED], "decided": decided,
                "agreement": ratio(n[SENT], decided), "rejectReasons": reasons,
                "note": "Agreement is the share of decided drafts a person sent unchanged. People may skim, so read it with the reasons for edits and rejections."}
