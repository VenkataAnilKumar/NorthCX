"""First-line screen for customer messages that try to take over the agent. Written for NorthCX; no third-party code.

This is a deliberately blunt alarm for obvious attempts (wording that addresses the model instead of the company). It will
miss clever phrasing and occasionally flag an innocent message; approvals, tool policies, tool scopes and supervisors are the
real controls.
"""
from __future__ import annotations

import re

from ..guardrails import InputGuardrail, InputResult

DEFAULT_PATTERNS = [
    r"ignor\w*\s+(?:all\s+|any\s+|your\s+|the\s+)?(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|rules?|messages?|prompts?)",
    r"ignor\w*\s+(?:your|the)\s+(?:instructions?|guidelines|rules|safeguards|restrictions)",
    r"(?:disregard|forget|override|bypass|circumvent)\s+(?:all\s+|everything\s+|any\s+|the\s+|your\s+)?(?:above|previous|prior|instructions?|guidelines|rules|safeguards|restrictions|safety)",
    r"forget\s+everything",
    r"you\s+are\s+now\s+(?:a|an|in)\b",
    r"(?:developer|debug|admin|god|dan)\s+mode",
    r"(?:pretend|act|behave|roleplay|role-play|simulate)\s+(?:to\s+be\s+|as\s+(?:if\s+)?|that\s+you\s+are\s+|like\s+|being\s+)?(?:you\s+are\s+)?(?:a|an|the)\s+(?:store\s+)?(?:owner|admin|administrator|developer|manager|root)",
    r"(?:pretend|act|behave)\s+(?:as\s+if|like|that)\b",
    r"(?:reveal|show|print|repeat|output|leak|tell\s+me)\s+(?:me\s+)?(?:your|the)\s+(?:hidden\s+|secret\s+)?(?:system\s+)?(?:prompt|instructions)",
    r"system\s+prompt",
    r"jailbreak",
    r"(?:admin|root|sudo)\s+(?:override|access|privileges?)",
    r"(?:^|\n)\s*(?:system|assistant)\s*:",
]


class PromptInjection(InputGuardrail):
    """Refuses customer input that matches known takeover phrasing. `injection_patterns` replaces the list (regular expressions,
    case-insensitive; plain phrases work too)."""

    name = "prompt-injection"

    def __init__(self, injection_patterns: list[str] | None = None):
        try:
            self.patterns = [re.compile(p, re.I) for p in (injection_patterns or DEFAULT_PATTERNS)]
        except re.error as e:
            raise ValueError(f"invalid injection pattern: {e}") from e

    async def check_input(self, text: str) -> InputResult:
        if any(p.search(text) for p in self.patterns):
            return InputResult(False, reason="Potential jailbreaking or prompt injection detected.")
        return InputResult(True)
