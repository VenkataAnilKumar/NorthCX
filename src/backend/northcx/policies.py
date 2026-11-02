"""Policy library: ready-made, configurable guardrails, each shipped with cases that prove what it allows and blocks.

Every policy here is deterministic (no model call). `CASES` is the proof: the test suite runs each case against the
policy built with the given config, so a change that weakens a policy fails a test.
"""
from __future__ import annotations

import re
from typing import Any

from .guardrails import Guardrail, GuardrailContext, Verdict


def _words(value: Any, what: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(x, str) and x.strip() for x in value):
        raise ValueError(f"{what} needs a non-empty list of strings")
    return [x.strip() for x in value]


class ToolLimit(Guardrail):
    """Denies a call to `tool` when numeric field `field` is above `max` (or below `min`), or is missing/not a number."""

    name = "tool-limit"

    def __init__(self, tool: str, field: str, max: float | None = None, min: float | None = None):
        if not tool or not field or (max is None and min is None):
            raise ValueError("tool_limit needs 'tool', 'field' and 'max' and/or 'min'")
        self.tool, self.field, self.max, self.min = tool, field, max, min

    async def check_tool_call(self, name: str, input: dict[str, Any], ctx: GuardrailContext) -> Verdict:
        if name != self.tool:
            return Verdict.ok()
        v = input.get(self.field)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            return Verdict.deny(f"{self.tool}.{self.field} must be a number")
        if self.max is not None and v > self.max:
            return Verdict.deny(f"{self.tool}.{self.field} is above the limit of {self.max:g}")
        if self.min is not None and v < self.min:
            return Verdict.deny(f"{self.tool}.{self.field} is below the minimum of {self.min:g}")
        return Verdict.ok()


class ForbiddenPhrases(Guardrail):
    """Denies replies containing any of the phrases (whole words, any case)."""

    name = "forbidden-phrases"

    def __init__(self, phrases: list[str], reason: str = "Reply contains wording that is not allowed."):
        self.reason = reason
        self.patterns = [re.compile(r"(?<!\w)" + re.escape(p) + r"(?!\w)", re.I) for p in _words(phrases, "forbidden_phrases")]

    async def check_reply(self, reply: str, ctx: GuardrailContext) -> Verdict:
        return Verdict.deny(self.reason) if any(p.search(reply) for p in self.patterns) else Verdict.ok()


class RequiredPhrase(Guardrail):
    """When the reply mentions a trigger, it must also contain the required text (for example a disclaimer)."""

    name = "required-phrase"

    def __init__(self, when_mentions: list[str], must_include: str):
        if not must_include.strip():
            raise ValueError("required_phrase needs 'must_include'")
        self.trigger = ForbiddenPhrases(when_mentions, "")
        self.must = must_include.strip().lower()

    async def check_reply(self, reply: str, ctx: GuardrailContext) -> Verdict:
        if any(p.search(reply) for p in self.trigger.patterns) and self.must not in reply.lower():
            return Verdict.deny("Reply is missing required wording.")
        return Verdict.ok()


class NoPersonalDataInReply(Guardrail):
    """Denies replies that contain an email address, SSN or phone number (the agent should refer to data, not repeat it)."""

    name = "no-personal-data-in-reply"
    _patterns = {
        "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "phone number": re.compile(r"(?:\+\d{1,3}[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),
    }

    def __init__(self, allow: list[str] | None = None):
        self.allow = {a.lower() for a in (allow or [])}  # exact strings that may appear, such as the company's support address

    async def check_reply(self, reply: str, ctx: GuardrailContext) -> Verdict:
        for label, pat in self._patterns.items():
            for m in pat.finditer(reply):
                if m.group(0).lower() not in self.allow:
                    return Verdict.deny(f"Reply contains a {label}.")
        return Verdict.ok()


class MaxReplyLength(Guardrail):
    """Denies replies longer than `max_chars` (the agent is asked to rewrite shorter)."""

    name = "max-reply-length"

    def __init__(self, max_chars: int):
        if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 20:
            raise ValueError("max_reply_length needs 'max_chars' of at least 20")
        self.max = max_chars

    async def check_reply(self, reply: str, ctx: GuardrailContext) -> Verdict:
        return Verdict.deny(f"Reply is longer than {self.max} characters.") if len(reply) > self.max else Verdict.ok()


FACTORIES = {
    "tool_limit": lambda cfg, ctx: ToolLimit(**cfg),
    "forbidden_phrases": lambda cfg, ctx: ForbiddenPhrases(**cfg),
    "required_phrase": lambda cfg, ctx: RequiredPhrase(**cfg),
    "no_personal_data_in_reply": lambda cfg, ctx: NoPersonalDataInReply(**cfg),
    "max_reply_length": lambda cfg, ctx: MaxReplyLength(**cfg),
}

DESCRIPTIONS = {
    "tool_limit": "Blocks a tool call whose numeric field is above a maximum or below a minimum (for example refunds above 500).",
    "forbidden_phrases": "Blocks replies containing listed wording (promises, guarantees, legal or medical claims).",
    "required_phrase": "Requires a disclaimer whenever the reply mentions listed topics.",
    "no_personal_data_in_reply": "Blocks replies that repeat emails, SSNs or phone numbers.",
    "max_reply_length": "Blocks replies longer than a limit.",
}

# (policy, config, kind, subject, expected_allow). kind "tool" -> subject is (name, input); kind "reply" -> subject is text.
CASES: list[tuple[str, dict[str, Any], str, Any, bool]] = [
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "max": 100}, "tool", ("issue_refund", {"amount": 100}), True),
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "max": 100}, "tool", ("issue_refund", {"amount": 100.01}), False),
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "max": 100}, "tool", ("issue_refund", {"amount": "50"}), False),
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "max": 100}, "tool", ("issue_refund", {}), False),
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "max": 100}, "tool", ("issue_refund", {"amount": True}), False),
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "max": 100}, "tool", ("issue_refund", {"amount": float("nan")}), False),
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "max": 100}, "tool", ("lookup_order", {"amount": 9999}), True),
    ("tool_limit", {"tool": "issue_refund", "field": "amount", "min": 1}, "tool", ("issue_refund", {"amount": -5}), False),
    ("forbidden_phrases", {"phrases": ["guarantee", "legal advice"]}, "reply", "I can't give legal advice.", False),
    ("forbidden_phrases", {"phrases": ["guarantee", "legal advice"]}, "reply", "We GUARANTEE delivery tomorrow.", False),
    ("forbidden_phrases", {"phrases": ["guarantee", "legal advice"]}, "reply", "Your order ships tomorrow.", True),
    ("forbidden_phrases", {"phrases": ["guarantee"]}, "reply", "A guaranteed-look finish", True),  # whole words only
    ("required_phrase", {"when_mentions": ["refund"], "must_include": "subject to approval"}, "reply", "A refund is on its way.", False),
    ("required_phrase", {"when_mentions": ["refund"], "must_include": "subject to approval"}, "reply", "Refund, Subject To Approval.", True),
    ("required_phrase", {"when_mentions": ["refund"], "must_include": "subject to approval"}, "reply", "Your order shipped.", True),
    ("no_personal_data_in_reply", {}, "reply", "Your email a@b.com is on file.", False),
    ("no_personal_data_in_reply", {}, "reply", "SSN 123-45-6789", False),
    ("no_personal_data_in_reply", {}, "reply", "Call 415-555-0199", False),
    ("no_personal_data_in_reply", {}, "reply", "Order 2077123456 has shipped.", True),
    ("no_personal_data_in_reply", {"allow": ["help@shop.test"]}, "reply", "Write to HELP@shop.test", True),
    ("no_personal_data_in_reply", {"allow": ["help@shop.test"]}, "reply", "Write to help@shop.test or a@b.com", False),
    ("max_reply_length", {"max_chars": 50}, "reply", "x" * 50, True),
    ("max_reply_length", {"max_chars": 50}, "reply", "x" * 51, False),
]

BAD_CONFIGS = [
    ("tool_limit", {}), ("tool_limit", {"tool": "t", "field": "f"}), ("forbidden_phrases", {"phrases": []}),
    ("forbidden_phrases", {"phrases": [""]}), ("forbidden_phrases", {"phrases": "guarantee"}), ("required_phrase", {"when_mentions": ["x"], "must_include": " "}),
    ("max_reply_length", {"max_chars": 5}), ("max_reply_length", {"max_chars": True}), ("no_personal_data_in_reply", {"nope": 1}),
]
