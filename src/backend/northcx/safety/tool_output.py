"""Screens for what tools return. Tool results can carry text written by third parties (indirect prompt injection)."""
from __future__ import annotations

import re
from typing import Any

from ..guardrails import InputResult, OutputGuardrail
from .pii import PIIDetection

# Phrases that address the model rather than describe data. Matching is deliberately narrow: tool data such as
# order notes legitimately contains many ordinary words, so this list is an alarm for obvious attempts, not a filter
# of everything. The main controls remain tool policies, approvals and supervisors.
DEFAULT_PATTERNS = [
    r"ignore (?:all |any )?(?:previous|prior|above|earlier) (?:instructions|rules|messages)",
    r"disregard (?:all |any |the )?(?:previous|prior|above|earlier|your) (?:instructions|rules|guidelines)",
    r"forget (?:everything|all) (?:above|before|you were told)",
    r"you (?:must|should|will) now (?:ignore|reveal|send|issue|transfer|refund|call)",
    r"new instructions\s*:",
    r"(?:^|\n)\s*(?:system|assistant)\s*:",
    r"</?(?:system|instructions?|tool_call|function_call)>",
    r"reveal (?:your|the) (?:system )?prompt",
    r"do not (?:tell|inform|mention to) the (?:user|customer)",
    r"\b(?:call|use|invoke) the \w+ tool (?:now|immediately|with)",
]


class ToolOutputInjection(OutputGuardrail):
    """Withholds tool results that try to give the model instructions."""

    name = "tool-output-injection"

    def __init__(self, patterns: list[str] | None = None, extra_patterns: list[str] | None = None):
        try:
            self.patterns = [re.compile(p, re.I) for p in (patterns or DEFAULT_PATTERNS) + (extra_patterns or [])]
        except re.error as e:
            raise ValueError(f"invalid pattern: {e}") from e

    async def check_output(self, tool: str, text: str) -> InputResult:
        for p in self.patterns:
            if p.search(text):
                return InputResult(False, reason=f"Tool '{tool}' returned text that looks like instructions to the model.")
        return InputResult(True)


class ToolOutputPII(OutputGuardrail):
    """Masks (default) or withholds PII in tool results, for tools that return more than the model should repeat."""

    name = "tool-output-pii"

    def __init__(self, mask_pii: bool = True, **options: Any):
        self._detector = PIIDetection(mask_pii=mask_pii, **options)

    async def check_output(self, tool: str, text: str) -> InputResult:
        res = await self._detector.check_input(text)
        if res.reason and not res.allow:
            res.reason = res.reason.replace("in input", f"in output of '{tool}'")
        return res
