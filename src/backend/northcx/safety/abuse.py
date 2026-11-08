"""Abuse detection for customer messages (S8). Written for NorthCX; no third-party code.

It looks at the conversation itself, so it needs no storage of its own: abusive language and threats, the same message sent again and
again, and bursts of messages. What happens depends on how bad it is and whether it keeps happening.

* A threat of violence goes to a person at once, without the model.
* Abusive language is answered calmly: the first times the agent is told to stay professional, not to match the tone, and to offer a
  person; from the third abusive message (configurable) the conversation goes to a person.
* Repeating one message is noted for the agent (do not repeat yourself, offer a person) and, past a limit, goes to a person.
* A burst of messages gets a polite slow-down reply without calling the model, and nothing is handed off.

This is a blunt, deterministic screen with a short word list; it will miss subtle abuse and cannot judge tone. Operators can add terms.
Customers are never told they were "flagged", and nothing is shared outside the platform.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque

from ..guardrails import InputGuardrail, InputResult

ABUSIVE = [
    r"f+u+c+k+(?:ing|ed|er|s)?", r"sh[i1]+t(?:ty|head)?", r"b[i1]tch(?:es)?", r"bastards?", r"a(?:ss|rse)holes?", r"dickheads?", r"motherfuck\w*", r"cunts?",
    r"pieces?\s+of\s+shit", r"stupid\s+(?:bot|idiot|cow|moron|fuck\w*)", r"(?:you(?:'|’)?re|you\s+are|u\s+r|ur)\s+(?:an?\s+)?(?:idiots?|morons?|useless|worthless|pathetic|trash|garbage)",
    r"idiots?", r"morons?", r"shut\s+(?:the\s+f\w+\s+)?up", r"go\s+to\s+hell", r"piss\s+off", r"scumbags?", r"retards?", r"whores?", r"sluts?",
]
THREATS = [
    r"i(?:'| a)?m\s+going\s+to\s+(?:kill|hurt|shoot|stab|find|burn)\b", r"i(?:'| wi)ll\s+(?:kill|hurt|shoot|stab|find\s+you|burn)\b", r"(?:kill|hurt|shoot|stab)\s+(?:you|your|them|everyone|myself)\b",
    r"\bbomb\b.{0,20}\b(?:office|store|shop|building|you|there)\b", r"you(?:'| wi)ll\s+(?:pay|regret|die)\b", r"(?:burn|blow)\s+(?:down|up)\s+(?:your|the)\s+\w+", r"i\s+know\s+where\s+you\s+(?:live|work)",
]
NOTE = ("The customer has been rude or abusive. Stay calm, polite and professional; do not match the tone, do not lecture, and do not apologise for things that are not your fault. "
        "Say what you can help with, and offer to connect them with a person.")
REPEAT_NOTE = "The customer has sent the same message several times. Do not repeat your earlier answer word for word: say what you need from them, or offer to connect them with a person."
SLOW_DOWN = "You're sending messages very quickly. Please give me a moment to catch up, then send what you need in one message."
CALM_HANDOFF = "I'm going to pass this conversation to a colleague who can help from here."


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


class AbuseDetection(InputGuardrail):
    name = "abuse-detection"
    needs_context = True

    def __init__(self, max_strikes: int = 3, repeat_limit: int = 3, burst_limit: int = 8, burst_seconds: float = 60.0, extra_terms: list[str] | None = None,
                 hand_off: bool = True, clock=time.time):
        if not (1 <= max_strikes <= 20 and 2 <= repeat_limit <= 20 and 2 <= burst_limit <= 100 and 5 <= burst_seconds <= 600):
            raise ValueError("abuse_detection: max_strikes 1-20, repeat_limit 2-20, burst_limit 2-100, burst_seconds 5-600")
        try:
            self.abusive = re.compile(r"\b(?:" + "|".join(ABUSIVE + [re.escape(t) for t in (extra_terms or [])]) + r")\b", re.I)
            self.threat = re.compile("|".join(THREATS), re.I)
        except re.error as e:
            raise ValueError(f"abuse_detection: invalid term: {e}") from e
        if extra_terms and (len(extra_terms) > 200 or any(not t.strip() or len(t) > 60 for t in extra_terms)):
            raise ValueError("abuse_detection: extra_terms must be at most 200 short words or phrases")
        self.max_strikes, self.repeat_limit, self.burst_limit, self.burst_seconds, self.hand_off, self.clock = max_strikes, repeat_limit, burst_limit, burst_seconds, hand_off, clock
        self._recent: dict[str, deque[float]] = defaultdict(deque)

    def kinds_in(self, text: str) -> list[str]:
        out = []
        if self.threat.search(text):
            out.append("threat")
        if self.abusive.search(text):
            out.append("abusive")
        return out

    async def _bursting(self, session_id: str) -> bool:
        if self.limiter is not None:  # several server processes: count in the shared store so a burst split across them is still seen
            return await self.limiter.count(f"abuse-burst:{session_id}", self.burst_seconds) > self.burst_limit
        now = self.clock()
        q = self._recent[session_id]
        q.append(now)
        while q and now - q[0] > self.burst_seconds:
            q.popleft()
        if len(self._recent) > 5000:  # forget idle conversations
            for k in [k for k, v in self._recent.items() if not v or now - v[-1] > self.burst_seconds]:
                del self._recent[k]
        return len(q) > self.burst_limit

    async def check_input(self, text: str) -> InputResult:
        return await self.check_input_ctx(text, "-", [])

    async def check_input_ctx(self, text: str, session_id: str, earlier: list[str]) -> InputResult:
        """`earlier` is what the customer wrote before in this conversation, oldest first."""
        if await self._bursting(session_id):
            return InputResult(False, reason="Messages are arriving faster than a person could write them", reply=SLOW_DOWN, status="completed", kinds=["burst"])
        kinds = self.kinds_in(text)
        if "threat" in kinds:
            return InputResult(False, reason="Threat of violence", reply=CALM_HANDOFF, status="escalated", trigger="abuse", kinds=kinds, strikes=self.max_strikes) if self.hand_off else InputResult(True, note=NOTE, kinds=kinds)
        strikes = sum(1 for e in earlier[-30:] if self.abusive.search(e) or self.threat.search(e)) + (1 if "abusive" in kinds else 0)
        norm = _norm(text)
        same = 1 + sum(1 for e in reversed(earlier[-self.repeat_limit * 2:]) if _norm(e) == norm) if norm else 0
        if same >= self.repeat_limit:
            kinds.append("repeat")
        if "abusive" in kinds and strikes >= self.max_strikes and self.hand_off:
            return InputResult(False, reason=f"Repeated abusive language ({strikes} messages)", reply=CALM_HANDOFF, status="escalated", trigger="abuse", kinds=kinds, strikes=strikes)
        if "repeat" in kinds and same >= self.repeat_limit * 2 and self.hand_off:
            return InputResult(False, reason=f"The same message sent {same} times", reply=CALM_HANDOFF, status="escalated", trigger="abuse", kinds=kinds, strikes=strikes)
        if kinds:
            note = " ".join(n for n, k in ((NOTE, "abusive"), (REPEAT_NOTE, "repeat")) if k in kinds)
            return InputResult(True, note=note, kinds=kinds, strikes=strikes)
        return InputResult(True)
