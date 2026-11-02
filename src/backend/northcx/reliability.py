"""Keeping conversations alive when the model provider is slow or down: retries, fallback models, and token budgets."""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field, replace
from typing import Awaitable, Callable

from .types import LLM, LLMRequest, LLMResponse


def is_transient(e: BaseException) -> bool:
    """Worth retrying: timeouts, dropped connections, rate limits, provider overload and 5xx. Not bad requests or auth."""
    if isinstance(e, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    status = getattr(e, "status_code", None)
    if isinstance(status, int):
        return status in (408, 409, 425, 429) or status >= 500
    return type(e).__name__ in ("APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError", "OverloadedError")


class ModelUnavailable(RuntimeError):
    """Every model in the chain failed."""


@dataclass
class _Circuit:
    failures: int = 0
    open_until: float = 0.0


class ReliableLLM:
    """Wraps a model backend with retries (exponential back-off with jitter), a per-call timeout, ordered fallback
    models and a simple circuit breaker, so a provider outage costs a fast fallback rather than a slow failure each turn.

    `models` is the ordered chain; a request naming a model tries that one first, then the rest of the chain.
    Non-transient errors (bad request, authentication) are raised immediately: another model will not fix them.
    """

    def __init__(self, inner: LLM, models: list[str] | None = None, retries: int = 2, base_delay: float = 0.5,
                 max_delay: float = 8.0, timeout: float | None = 60.0, breaker_failures: int = 3, breaker_cooldown: float = 30.0,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, clock: Callable[[], float] = time.monotonic,
                 jitter: Callable[[], float] = random.random):
        self.inner, self.models = inner, list(models or [])
        self.retries, self.base, self.cap, self.timeout = retries, base_delay, max_delay, timeout
        self.breaker_failures, self.breaker_cooldown = breaker_failures, breaker_cooldown
        self._sleep, self._clock, self._jitter = sleep, clock, jitter
        self._circuits: dict[str | None, _Circuit] = {}
        self.events: list[dict] = []  # recent attempts for diagnostics (bounded)

    def _note(self, **e: object) -> None:
        self.events.append(e)
        del self.events[:-200]

    def _chain(self, requested: str | None) -> list[str | None]:
        if not self.models:
            return [requested]
        chain = ([requested] if requested else []) + [m for m in self.models if m != requested]
        return chain

    async def complete(self, req: LLMRequest) -> LLMResponse:
        last: BaseException | None = None
        chain = self._chain(req.model)
        for i, model in enumerate(chain):
            c = self._circuits.setdefault(model, _Circuit())
            if c.open_until > self._clock() and i < len(chain) - 1:
                self._note(model=model, skipped="circuit_open")
                continue
            for attempt in range(self.retries + 1):
                try:
                    coro = self.inner.complete(replace(req, model=model) if model != req.model else req)
                    res = await (asyncio.wait_for(coro, self.timeout) if self.timeout else coro)
                    c.failures = 0
                    if not res.model:
                        res.model = model
                    if i > 0:
                        res.fallback = True
                    return res
                except Exception as e:
                    last = e
                    self._note(model=model, attempt=attempt, error=type(e).__name__)
                    if not is_transient(e):
                        raise
                    c.failures += 1
                    if c.failures >= self.breaker_failures:
                        c.open_until = self._clock() + self.breaker_cooldown
                        break
                    if attempt < self.retries:
                        await self._sleep(min(self.cap, self.base * 2 ** attempt) * (0.5 + self._jitter() / 2))
        raise ModelUnavailable(f"No model could answer: {type(last).__name__ if last else 'all circuits open'}") from last


@dataclass
class UsageLedger:
    """Tokens used per day (UTC), per agent. Per process: with several servers each keeps its own count."""
    daily_limit: int | None = None
    _days: dict[tuple[str, str], int] = field(default_factory=dict)

    @staticmethod
    def _day(at: float | None = None) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(at if at is not None else time.time()))

    def add(self, agent_id: str, tokens: int, at: float | None = None) -> None:
        now = at if at is not None else time.time()
        k = (agent_id, self._day(now))
        self._days[k] = self._days.get(k, 0) + max(0, int(tokens))
        for old in [d for d in self._days if d[1] < self._day(now - 3 * 86400)]:
            del self._days[old]

    def used_today(self, agent_id: str | None = None, at: float | None = None) -> int:
        day = self._day(at)
        return sum(n for (a, d), n in self._days.items() if d == day and (agent_id is None or a == agent_id))

    def exhausted(self, at: float | None = None) -> bool:
        return self.daily_limit is not None and self.used_today(None, at) >= self.daily_limit
