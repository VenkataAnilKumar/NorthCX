"""The Pilot's "Do" style: it can propose a few actions, and nothing happens until the person confirms (E5, decision 163: anything that writes asks first).

The model never changes anything. It calls a `propose_...` tool, which only writes down what it would do. The person sees the proposal in the Pilot, and confirming runs it with
their own permissions, checked again at that moment; cancelling, or leaving it for 30 minutes, ends it. Three actions exist, all reversible or private:
tag a conversation (saved as `pilot-<tag>`), add a staff note to the customer of a conversation, and save an output.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .agent import Tool, ToolContext
from .audit import AuditEntry
from .tenancy import current_tenant

EXPIRES_SECONDS = 1800
MAX_PENDING = 10


class ActionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class TagInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=200, description="The conversation to tag")
    tag: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$", description="A short lowercase tag; it is saved with the prefix pilot-")


class CustomerNoteInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=200, description="A conversation whose customer the note is about")
    note: str = Field(min_length=5, max_length=300, description="A short note for colleagues. No card numbers, passwords or instructions.")


class SaveOutputInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=20000)
    kind: str = Field(default="note", pattern="^(note|answer|report|table|digest)$")


class CoachingInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=200, description="The conversation the note is about")
    about: str = Field(min_length=2, max_length=80, description="The person or agent the note is for")
    note: str = Field(min_length=5, max_length=300, description="What went well and what to try next time. No customer details.")


ACTIONS: dict[str, tuple[type[BaseModel], str, str]] = {
    "add_coaching_note": (CoachingInput, "reviews:write", "Add a coaching note to a conversation"),          # tool -> (input model, permission needed, what it does)
    "tag_conversation": (TagInput, "conversations:tag", "Tag a conversation"),
    "add_customer_note": (CustomerNoteInput, "customers:write", "Add a staff note about a conversation's customer"),
    "save_output": (SaveOutputInput, "workspace:use", "Save a result to Outputs"),
}


@dataclass
class PilotAction:
    owner: str
    chat_id: str
    tool: str
    input: dict[str, Any]
    summary: str
    id: str = field(default_factory=lambda: "act-" + uuid.uuid4().hex[:10])
    state: str = "proposed"                 # proposed, done, cancelled, expired, failed
    result: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "tool": self.tool, "summary": self.summary, "input": self.input, "state": self.state, "result": self.result, "chatId": self.chat_id,
                "createdAt": self.created_at, "expiresAt": self.created_at + EXPIRES_SECONDS}


class ActionRepo(Protocol):
    async def put(self, a: PilotAction) -> None: ...
    async def get(self, action_id: str) -> PilotAction | None: ...
    async def list(self, owner: str, chat_id: str | None, state: str | None) -> list[PilotAction]: ...


class InMemoryActions:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], PilotAction] = {}

    async def put(self, a: PilotAction) -> None:
        self._items[(current_tenant(), a.id)] = a

    async def get(self, action_id: str) -> PilotAction | None:
        return self._items.get((current_tenant(), action_id))

    async def list(self, owner: str, chat_id: str | None, state: str | None) -> list[PilotAction]:
        t = current_tenant()
        rows = [a for (tt, _), a in self._items.items() if tt == t and a.owner == owner and (chat_id is None or a.chat_id == chat_id) and (state is None or a.state == state)]
        return sorted(rows, key=lambda a: a.created_at)


class PilotActionService:
    def __init__(self, repo: ActionRepo | None = None):
        self.repo = repo or InMemoryActions()
        self.ws: Any = None                     # the WorkspaceService, for its audit log and the stores an action changes

    def tools(self, chat_id: str) -> list[Tool]:
        """What the model is offered in Do mode: tools that only write a proposal down."""
        out = []
        for name, (model, perm, doc) in ACTIONS.items():
            async def propose(inp: BaseModel, ctx: ToolContext, _name: str = name) -> dict[str, Any]:
                a = await self.propose(ctx.actor, chat_id, _name, inp.model_dump())
                return {"proposed": True, "id": a.id, "summary": a.summary, "note": "Nothing has changed. The person must confirm this in the Pilot first; tell them what you proposed."}
            out.append(Tool("propose_" + name, f"Propose to: {doc.lower()}. This only writes the proposal down; it happens only if the person confirms it.", model, propose, effect="read", audience="staff", permission=perm))
        return out

    async def propose(self, actor: Any, chat_id: str, tool: str, data: dict[str, Any]) -> PilotAction:
        if tool not in ACTIONS:
            raise ActionError(400, "Unknown action")
        pending = [a for a in await self.repo.list(actor.name, None, "proposed") if a.created_at > time.time() - EXPIRES_SECONDS]
        if len(pending) >= MAX_PENDING:
            raise ActionError(429, f"You already have {MAX_PENDING} proposals waiting; confirm or cancel some first")
        summary = {"tag_conversation": lambda d: f"Tag conversation {d['session_id'][:24]} as pilot-{d['tag']}", "add_customer_note": lambda d: f"Add a note about the customer of {d['session_id'][:24]}: {d['note'][:80]}",
                   "save_output": lambda d: f"Save '{d['title']}' to Outputs ({len(d['body'])} characters)",
                   "add_coaching_note": lambda d: f"Add a coaching note for {d['about']} on {d['session_id'][:24]}: {d['note'][:80]}"}[tool](data)
        a = PilotAction(actor.name, chat_id, tool, data, summary)
        await self.repo.put(a)
        return a

    async def _mine(self, action_id: str, actor: Any) -> PilotAction:
        a = await self.repo.get(action_id)
        if a is None or a.owner != actor.name:
            raise ActionError(404, "Unknown action")                      # someone else's proposal looks like a missing one
        return a

    async def confirm(self, action_id: str, actor: Any) -> PilotAction:
        a = await self._mine(action_id, actor)
        if a.state != "proposed":
            raise ActionError(409, f"That action is already {a.state}")
        if a.created_at < time.time() - EXPIRES_SECONDS:
            a.state = "expired"
            await self.repo.put(a)
            raise ActionError(409, "That proposal expired; ask again")
        if not actor.can(ACTIONS[a.tool][1]):                              # checked again now, not when it was proposed
            raise ActionError(403, f"Your role cannot do this (needs {ACTIONS[a.tool][1]})")
        try:
            a.result = await self._run(a, actor)
            a.state = "done"
        except ActionError as e:
            a.state, a.result = "failed", str(e)[:200]
            await self.repo.put(a)
            raise
        await self.repo.put(a)
        await self.ws.audit.append(AuditEntry(actor=actor.name, role=actor.role, key_id=actor.key_id, action="workspace.pilot_action", target=a.tool, detail={"action": a.id, "summary": a.summary[:200]}))
        return a

    async def cancel(self, action_id: str, actor: Any) -> PilotAction:
        a = await self._mine(action_id, actor)
        if a.state != "proposed":
            raise ActionError(409, f"That action is already {a.state}")
        a.state = "cancelled"
        await self.repo.put(a)
        return a

    async def _run(self, a: PilotAction, actor: Any) -> str:
        rt = self.ws.runtime
        d = a.input
        if a.tool == "tag_conversation":
            if not await self.ws.traces.summaries(d["session_id"], 1):
                raise ActionError(404, "Unknown conversation")
            try:
                await self.ws.tags.add(d["session_id"], "pilot-" + d["tag"], actor.name)
            except ValueError as e:
                raise ActionError(409, str(e)) from e
            return f"Tagged as pilot-{d['tag']}"
        if a.tool == "add_coaching_note":
            from .memory import MemoryRejected
            from .qa import CoachingNote
            from .workspace import screen_staff_note
            repo = getattr(rt, "coaching", None)
            if repo is None:
                raise ActionError(501, "Coaching notes are not configured on this server")
            if not await self.ws.traces.summaries(d["session_id"], 1):
                raise ActionError(404, "Unknown conversation")
            try:
                clean = screen_staff_note(d["note"])
            except MemoryRejected as e:
                raise ActionError(400, str(e)) from e
            await repo.add(CoachingNote(d["session_id"], d["about"].strip(), clean, actor.name))
            return "Coaching note added"
        if a.tool == "add_customer_note":
            from .customers import CustomerNote
            from .memory import MemoryRejected, check_note
            svc = getattr(rt, "customers", None)
            if svc is None or not await svc.enabled():
                raise ActionError(403, "The Customers view is not available")
            cid = await rt.privacy.customer_for_session(d["session_id"])
            if not cid:
                raise ActionError(404, "No customer is linked to that conversation")
            try:
                clean = check_note(d["note"])
            except MemoryRejected as e:
                raise ActionError(400, str(e)) from e
            await svc.notes.add(CustomerNote(cid, clean, actor.name))
            return "Note added"
        from .outputs import ContentError
        content = getattr(rt, "content", None)
        if content is None:
            raise ActionError(501, "Outputs are not configured on this server")
        try:
            o = await content.create_output(actor.name, d["title"], d["body"], d.get("kind", "note"), "private", None, "pilot", 90, actor.can("keys:manage"))
        except ContentError as e:
            raise ActionError(e.status, str(e)) from e
        return f"Saved as output {o.id}"
