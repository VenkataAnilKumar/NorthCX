"""Personal-data detection for customer input and exported traces. Written for NorthCX; no third-party code."""
from __future__ import annotations

import re
from typing import Mapping

from ..guardrails import InputGuardrail, InputResult, _luhn

_CARD_RUN = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
_BUILTIN = {
    "SSN": ("enable_ssn_check", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    "Email": ("enable_email_check", re.compile(r"\b[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    # A phone number needs structure (separators or a leading +) so plain ten-digit order numbers are not flagged.
    "Phone": ("enable_phone_check", re.compile(r"(?:\+\d{1,3}[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")),
}


class PIIDetection(InputGuardrail):
    """Finds social security numbers, emails, phone numbers and payment card numbers (Luhn-checked) plus any custom patterns.
    With `mask_pii` the matches are replaced by asterisks and the message continues; otherwise the message is refused."""

    name = "pii-detection"

    def __init__(self, mask_pii: bool = True, enable_ssn_check: bool = True, enable_credit_card_check: bool = True,
                 enable_email_check: bool = True, enable_phone_check: bool = True,
                 custom_patterns: Mapping[str, "str | re.Pattern[str]"] | None = None):
        self.mask_pii = mask_pii
        switches = {"enable_ssn_check": enable_ssn_check, "enable_email_check": enable_email_check, "enable_phone_check": enable_phone_check}
        self.patterns: dict[str, re.Pattern[str]] = {kind: rx for kind, (flag, rx) in _BUILTIN.items() if switches[flag]}
        self.card = enable_credit_card_check
        for kind, pat in (custom_patterns or {}).items():
            if isinstance(pat, str):
                pat = re.compile(pat)
            if not isinstance(pat, re.Pattern):
                raise TypeError(f"custom pattern '{kind}' must be a string or a compiled expression, not {type(pat).__name__}")
            self.patterns[kind] = pat

    def mask(self, text: str) -> tuple[str, list[str]]:
        """The text with every match replaced by asterisks, and the kinds of personal data that were found."""
        found: list[str] = []
        for kind, rx in self.patterns.items():
            text, n = rx.subn(lambda m: "*" * len(m.group(0)), text)
            if n:
                found.append(kind)
        if self.card:
            hit = False

            def hide(m: "re.Match[str]") -> str:
                nonlocal hit
                digits = re.sub(r"\D", "", m.group(0))
                if 13 <= len(digits) <= 19 and _luhn(digits):
                    hit = True
                    return "*" * len(m.group(0))
                return m.group(0)

            text = _CARD_RUN.sub(hide, text)
            if hit:
                found.append("Credit Card")
        return text, found

    async def check_input(self, text: str) -> InputResult:
        masked, found = self.mask(text)
        if not found:
            return InputResult(True)
        if self.mask_pii:
            return InputResult(True, reason=f"PII masked: {', '.join(found)}", text=masked)
        return InputResult(False, reason=f"Potential PII detected in input: {', '.join(found)}")
