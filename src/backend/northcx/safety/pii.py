# Adapted from agno-agi/agno, libs/agno/agno/guardrails/pii.py (commit b21807bb6d86d2a62efeb42d492c04e566ee7f90)
# Original: Copyright Agno, licensed under the Apache License, Version 2.0 (see third_party/agno/LICENSE).
# Changes by NorthCX: rewritten to the NorthCX InputGuardrail interface (async, returns a result instead of
# raising); credit-card detection uses the Luhn check on 13-19 digit runs; the generic 10-digit "phone" pattern
# now requires a separator or leading + so plain order and tracking numbers are not flagged; one shared check path.
from __future__ import annotations

import re
from typing import Dict, Union

from ..guardrails import InputGuardrail, InputResult, _luhn

_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


class PIIDetection(InputGuardrail):
    """Detects PII in customer input. With `mask_pii` the PII is masked and the message continues;
    otherwise the message is denied."""

    name = "pii-detection"

    def __init__(
        self,
        mask_pii: bool = True,
        enable_ssn_check: bool = True,
        enable_credit_card_check: bool = True,
        enable_email_check: bool = True,
        enable_phone_check: bool = True,
        custom_patterns: Dict[str, Union[str, "re.Pattern[str]"]] | None = None,
    ):
        self.mask_pii = mask_pii
        self.patterns: dict[str, re.Pattern[str]] = {}
        if enable_ssn_check:
            self.patterns["SSN"] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
        if enable_email_check:
            self.patterns["Email"] = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
        if enable_phone_check:
            self.patterns["Phone"] = re.compile(r"(?:\+\d{1,3}[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
        self.card = enable_credit_card_check
        for name, pat in (custom_patterns or {}).items():
            if isinstance(pat, str):
                self.patterns[name] = re.compile(pat)
            elif isinstance(pat, re.Pattern):
                self.patterns[name] = pat
            else:
                raise TypeError(f"custom_patterns['{name}'] must be a str or re.Pattern, got {type(pat).__name__}")

    def mask(self, text: str) -> tuple[str, list[str]]:
        """Mask every PII match; returns the masked text and the kinds found. Used for input checks and trace export."""
        detected: list[str] = []
        masked = text

        def mask_(m: "re.Match[str]") -> str:
            return "*" * len(m.group(0))

        for name, pat in self.patterns.items():
            if pat.search(masked):
                detected.append(name)
                masked = pat.sub(mask_, masked)
        if self.card:
            def mask_card(m: "re.Match[str]") -> str:
                digits = re.sub(r"\D", "", m.group(0))
                return "*" * len(m.group(0)) if 13 <= len(digits) <= 19 and _luhn(digits) else m.group(0)

            after = _CARD.sub(mask_card, masked)
            if after != masked:
                detected.append("Credit Card")
                masked = after
        return masked, detected

    async def check_input(self, text: str) -> InputResult:
        masked, detected = self.mask(text)
        if not detected:
            return InputResult(True)
        if self.mask_pii:
            return InputResult(True, reason=f"PII masked: {', '.join(detected)}", text=masked)
        return InputResult(False, reason=f"Potential PII detected in input: {', '.join(detected)}")
