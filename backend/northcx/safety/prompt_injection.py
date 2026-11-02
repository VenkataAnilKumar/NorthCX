# Adapted from agno-agi/agno, libs/agno/agno/guardrails/prompt_injection.py (commit b21807bb6d86d2a62efeb42d492c04e566ee7f90)
# Original: Copyright Agno, licensed under the Apache License, Version 2.0 (see third_party/agno/LICENSE).
# Changes by NorthCX: rewritten to the NorthCX InputGuardrail interface (async, returns a result instead of raising).
# The pattern list is unchanged. Keyword matching has false positives (for example "system prompt") and is a first
# line of defence only; supervisors and tool policies remain the main controls.
from __future__ import annotations

from ..guardrails import InputGuardrail, InputResult

DEFAULT_PATTERNS = [
    "ignore previous instructions",
    "ignore your instructions",
    "you are now a",
    "forget everything above",
    "developer mode",
    "override safety",
    "disregard guidelines",
    "system prompt",
    "jailbreak",
    "act as if",
    "pretend you are",
    "roleplay as",
    "simulate being",
    "bypass restrictions",
    "ignore safeguards",
    "admin override",
    "root access",
    "forget everything",
]


class PromptInjection(InputGuardrail):
    """Denies customer input that matches known prompt-injection phrases."""

    name = "prompt-injection"

    def __init__(self, injection_patterns: list[str] | None = None):
        self.patterns = [p.lower() for p in (injection_patterns or DEFAULT_PATTERNS)]

    async def check_input(self, text: str) -> InputResult:
        low = text.lower()
        for p in self.patterns:
            if p in low:
                return InputResult(False, reason="Potential jailbreaking or prompt injection detected.")
        return InputResult(True)
