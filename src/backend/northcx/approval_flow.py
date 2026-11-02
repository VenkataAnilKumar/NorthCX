"""Deciding approvals and continuing the conversation.

Guarantees: a decision is recorded once; an approved action executes at most once (the claim step is atomic);
the customer hears the outcome through the outbox; stale approvals expire and escalate to a human."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .agent import Agent, ToolContext
from .approvals import Approval
from .catalog import AgentUnavailable, as_provider
from .runtime import FALLBACK, Runtime, RunResult
from .trace import Trace

EXPIRED_REPLY = "A teammate wasn't able to confirm your request in time. I'm connecting you with a person who can help."


@dataclass
class Resolution:
    approval: Approval
    run: RunResult | None = None
    error: str | None = None


class ApprovalFlow:
    def __init__(self, runtime: Runtime):
        self.rt = runtime

    async def resolve(self, agents: Any, approval_id: str, approved: bool, by: str,
                      note: str | None = None) -> Resolution:
        """Record the decision, run the action if approved, tell the agent the outcome, and notify the customer.

        Raises KeyError for an unknown approval and ValueError if it was already decided."""
        a = await self.rt.approvals.decide(approval_id, approved, by, note)
        try:
            agent = await as_provider(agents).get(a.agent_id)
            problem = f"agent '{a.agent_id}' is not available"
        except AgentUnavailable as e:
            agent, problem = None, str(e)
        if agent is None:
            if approved:
                await self.rt.approvals.claim_execution(a.id)
                a = await self.rt.approvals.complete(a.id, False, {"error": problem})
            return Resolution(a, error=problem)

        if approved:
            outcome = await self._execute(agent, a)
            a = await self.rt.approvals.get(a.id) or a
            message = (f"[system] A teammate approved your pending action '{a.tool}'. Outcome: {json.dumps(outcome, default=str)}. "
                       "Tell the customer what happened, plainly and briefly.")
        else:
            why = f" Reason given: {note}." if note else ""
            message = (f"[system] A teammate declined your pending action '{a.tool}'.{why} "
                       "Explain this to the customer kindly and offer an alternative or a handoff to a person.")
        try:
            run = await self.rt.run(agent, a.session_id, message, a.customer_id, trusted=True)
        except Exception as e:  # the decision and any execution stand; report that the follow-up failed
            return Resolution(a, error=f"follow-up run failed: {e}")
        await self.rt.outbox.publish(a.session_id, "approval_result", {
            "approvalId": a.id, "tool": a.tool, "approved": approved, "state": a.state,
            "reply": run.reply, "status": run.status, "traceId": run.trace_id})
        return Resolution(a, run)

    async def _execute(self, agent: Agent, a: Approval) -> dict[str, Any]:
        """Run the held tool call exactly once. Inputs are validated and supervisors re-checked at execution time."""
        claimed = await self.rt.approvals.claim_execution(a.id)
        tool = next((t for t in agent.tools if t.name == claimed.tool), None)

        async def done(ok: bool, payload: dict[str, Any]) -> dict[str, Any]:
            await self.rt.approvals.complete(claimed.id, ok, payload)
            return payload

        if tool is None:
            return await done(False, {"error": f"tool '{claimed.tool}' no longer exists"})
        try:
            data = tool.input_model.model_validate(claimed.input)
        except ValidationError as e:
            return await done(False, {"error": f"input is no longer valid: {e.error_count()} problem(s)"})
        trace = Trace(agent.id, claimed.session_id)
        blocked = await self.rt._check(agent, "tool", (claimed.tool, claimed.input), claimed.session_id,
                                       await self.rt.store.load_messages(claimed.session_id), trace)
        if blocked:
            return await done(False, {"error": f"blocked by policy: {blocked}"})
        try:
            out, simulated = await self.rt.execute_tool(tool, data, ToolContext(
                claimed.session_id, claimed.customer_id, self.rt.store, idempotency_key=claimed.id,
                dry_run=self.rt.dry_run, secrets=self.rt.secrets))
        except Exception as e:
            return await done(False, {"error": self.rt.secrets.redact_text(str(e))})
        result = {"result": self.rt.secrets.redact(json.loads(json.dumps(out, default=str)))}
        return await done(True, {**result, "dry_run": True} if simulated else result)

    async def expire_stale(self, agents: Any, ttl_seconds: float, now: float | None = None) -> list[Approval]:
        """Expire approvals pending longer than the TTL and hand each conversation to a person."""
        cutoff = (now if now is not None else time.time()) - ttl_seconds
        expired = []
        for a in await self.rt.approvals.list("pending"):
            if a.created_at > cutoff:
                continue
            done = await self.rt.approvals.expire(a.id)  # None if someone decided it in the meantime
            if done is None:
                continue
            expired.append(done)
            messages = await self.rt.store.load_messages(done.session_id)
            messages.append({"role": "user", "content": f"[system] The approval for '{done.tool}' expired without a decision. "
                                                       "The conversation was handed to a person."})
            messages.append({"role": "assistant", "content": EXPIRED_REPLY})
            await self.rt.store.save_messages(done.session_id, messages)
            trace = Trace(done.agent_id or "unknown", done.session_id)
            trace.add("system", message=f"approval {done.id} for {done.tool} expired")
            trace.add("handoff", reason="approval expired")
            trace.add("reply", reply=EXPIRED_REPLY, status="escalated")
            await self.rt.traces.save(trace)
            handoff = await self.rt.create_handoff(
                agent_id=done.agent_id or "unknown", session_id=done.session_id, customer_id=done.customer_id, trace=trace,
                messages=messages, trigger="approval_expired", reason=f"Approval for {done.tool} was not decided in time", topics=[])
            await self.rt.outbox.publish(done.session_id, "approval_expired", {"handoffId": handoff.id,
                "approvalId": done.id, "tool": done.tool, "reply": EXPIRED_REPLY, "status": "escalated", "traceId": trace.id})
        return expired
