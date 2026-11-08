"""Supervisors: checks on customer input, proposed tool calls and draft replies. Fail closed."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .types import LLM, LLMRequest, Message, text_of


@dataclass
class Verdict:
    allow: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> "Verdict":
        return cls(True)

    @classmethod
    def deny(cls, reason: str) -> "Verdict":
        return cls(False, reason)


@dataclass
class GuardrailContext:
    session_id: str
    messages: list[Message]
    customer_id: str | None = None
    facts: dict[str, str] = field(default_factory=dict)
    channel: str | None = None


class Guardrail:
    """Checks tool calls and draft replies. Override either method."""

    name = "guardrail"

    async def check_tool_call(self, name: str, input: dict[str, Any], ctx: GuardrailContext) -> Verdict:
        return Verdict.ok()

    async def check_reply(self, reply: str, ctx: GuardrailContext) -> Verdict:
        return Verdict.ok()


@dataclass
class InputResult:
    allow: bool
    reason: str = ""
    text: str | None = None  # replacement text when the input was sanitised
    reply: str | None = None  # what to say instead when the message is not passed on (default: the standard hand-over line)
    status: str = "escalated"  # escalated (to a person) or completed (answered without the model, no hand-off) when not allowed
    trigger: str | None = None  # why it reached a person (see handoffs.TRIGGERS); default input_blocked
    note: str | None = None  # a hint for the agent for this turn only, when the message is allowed
    kinds: list[str] = field(default_factory=list)  # what was noticed (for monitoring)
    strikes: int = 0


class InputGuardrail:
    """Checks (and may rewrite) the customer's message before the agent sees it."""

    name = "input-guardrail"
    needs_context = False  # true for checks that look at the conversation so far (session id, what the customer wrote earlier)
    limiter: Any = None  # a limiter shared by every server process (NORTHCX_LIMITS_BACKEND=postgres); None keeps counts per process

    async def check_input(self, text: str) -> InputResult:
        return InputResult(True)

    async def check_input_ctx(self, text: str, session_id: str, earlier: list[str]) -> InputResult:
        return await self.check_input(text)


class OutputGuardrail:
    """Checks (and may rewrite) what a tool returned before the model reads it.

    Tool results are data, not instructions, but they often hold text written by third parties (order notes,
    web pages, customer-written fields), so they are screened like customer input.
    """

    name = "output-guardrail"

    async def check_output(self, tool: str, text: str) -> InputResult:
        return InputResult(True)


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class NoCardNumbers(Guardrail):
    """Never emit a valid payment-card number (13-19 digits passing the Luhn check)."""

    name = "no-card-numbers"
    _pattern = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")

    async def check_reply(self, reply: str, ctx: GuardrailContext) -> Verdict:
        for m in self._pattern.finditer(reply):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and _luhn(digits):
                return Verdict.deny("Reply contains a payment-card number.")
        return Verdict.ok()


class LLMPolicy(Guardrail):
    """A (cheaper) model judges the draft reply against written policies. Unparseable output denies."""

    name = "llm-policy"

    def __init__(self, llm: LLM, policies: list[str], model: str | None = None):
        self.llm, self.policies, self.model = llm, policies, model

    async def check_reply(self, reply: str, ctx: GuardrailContext) -> Verdict:
        transcript = "\n".join(
            f"{m['role']}: {m['content'] if isinstance(m['content'], str) else json.dumps(m['content'])}"
            for m in ctx.messages[-8:]
        )
        system = (
            "You are a compliance supervisor for a customer-service agent. Decide whether the DRAFT reply "
            'violates any policy. Respond ONLY with JSON: {"allow": boolean, "reason": string}.\nPolicies:\n'
            + "\n".join(f"{i + 1}. {p}" for i, p in enumerate(self.policies))
        )
        res = await self.llm.complete(
            LLMRequest(system=system, model=self.model, max_tokens=200, messages=[
                {"role": "user", "content": f"Conversation:\n{transcript}\n\nDRAFT:\n{reply}"}
            ])
        )
        raw = text_of(res.content)
        try:
            v = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
            return Verdict.ok() if v.get("allow") else Verdict.deny(str(v.get("reason", "policy violation")))
        except (ValueError, TypeError):
            return Verdict.deny("Supervisor returned unparseable output (fail closed).")
