"""Edit a customer message and run the conversation again from there, in a sandbox.

A person testing an agent asks "what if the customer had said this instead?". The conversation before that message is copied into a
throwaway runtime (its own stores, simulated writes, no outbox, no hand-offs that anyone sees) and the edited message is answered there.
The real conversation, its traces and its customer are never touched. Staff only (docs/01-chat/NorthCX_Rerun-and-Replay.md)."""
from __future__ import annotations

from typing import Any

from .approvals import ApprovalStore
from .handoffs import InMemoryHandoffs
from .outbox import Outbox
from .runtime import Runtime, _flat
from .store import InMemoryStore
from .trace import TraceStore


def customer_turns(messages: list[dict[str, Any]]) -> list[int]:
    """Positions of the customer's own messages: not tool results, not platform notes (which start with a bracket)."""
    return [i for i, m in enumerate(messages) if m.get("role") == "user" and isinstance(m.get("content"), str) and not m["content"].startswith("[")]


def original_reply(messages: list[dict[str, Any]], index: int) -> str | None:
    """The last words the agent said after the message at `index` and before the customer's next message."""
    later = [i for i in customer_turns(messages) if i > index]
    end = later[0] if later else len(messages)
    said = [_flat(m["content"]) for m in messages[index + 1:end] if m.get("role") == "assistant" and _flat(m["content"]).strip()]
    return said[-1] if said else None


async def sandbox_run(runtime: Runtime, agent: Any, resolver: Any, history: list[dict[str, Any]], message: str) -> dict[str, Any]:
    """Answer `message` after `history` in a throwaway runtime: its own stores, simulated writes, no delivery. The real model is used and the
    daily budget counts it. Nothing is saved anywhere else."""
    sandbox = Runtime(runtime.llm, InMemoryStore(), TraceStore(), ApprovalStore(), Outbox(), InMemoryHandoffs(), secrets=runtime.secrets, dry_run=True, ledger=runtime.ledger)
    sandbox.agent_resolver = resolver
    session = "sandbox"
    await sandbox.store.save_messages(session, [dict(m) for m in history])
    result = await sandbox.run(agent, session, message, None)
    return {"message": message, "reply": result.reply, "status": result.status, "toolsCalled": result.trace.tools_called(), "events": result.trace.to_dict()["events"], "trace": result.trace}


async def rerun(runtime: Runtime, agent: Any, resolver: Any, messages: list[dict[str, Any]], index: int, message: str) -> dict[str, Any]:
    """Answer `message` in place of the customer message at `index`, after the conversation that came before it."""
    out = await sandbox_run(runtime, agent, resolver, messages[:index], message)
    out.pop("trace")
    return out
