"""AG-UI events for a run. The names are those of the AG-UI protocol's run, text-message and tool-call events.

The interrupt and resume fields are not confirmed against the specification text (docs/01-chat/NorthCX_AG-UI-Check.md, decision 203):
`finished()` and `interrupt()` are the only places that decide how an outcome and an interrupt look, so a correction is made here."""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

from northcx.api.common import _pieces

REASON = "approval_required"


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def started(thread_id: str, run_id: str) -> dict[str, Any]:
    return {"type": "RUN_STARTED", "threadId": thread_id, "runId": run_id}


def tool_call(name: str) -> list[dict[str, Any]]:
    """The runtime reports a tool when it starts one, with no arguments or result, so the card is a start and an end."""
    call_id = f"call-{uuid.uuid4().hex[:12]}"
    return [{"type": "TOOL_CALL_START", "toolCallId": call_id, "toolCallName": name}, {"type": "TOOL_CALL_END", "toolCallId": call_id}]


def message(reply: str) -> list[dict[str, Any]]:
    """The approved reply as one assistant message in pieces (the same pieces as the existing stream)."""
    if not reply:
        return []
    mid = f"msg-{uuid.uuid4().hex[:12]}"
    return [{"type": "TEXT_MESSAGE_START", "messageId": mid, "role": "assistant"},
            *({"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": p} for p in _pieces(reply)),
            {"type": "TEXT_MESSAGE_END", "messageId": mid}]


def interrupt(pending: dict[str, Any]) -> dict[str, Any]:
    """A held action. `pending` is an entry of RunResult.pending_approvals."""
    return {"id": pending["id"], "reason": REASON, "toolCallName": pending["tool"], "input": pending["input"], "message": pending.get("reason", "")}


def finished(thread_id: str, run_id: str, pending: Iterable[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    held = [interrupt(p) for p in pending]
    out: dict[str, Any] = {"type": "RUN_FINISHED", "threadId": thread_id, "runId": run_id, "outcome": "interrupt" if held else "success", "result": result}
    if held:
        out["interrupts"] = held
    return out


def error(message_: str, code: str) -> dict[str, Any]:
    return {"type": "RUN_ERROR", "message": message_, "code": code}
