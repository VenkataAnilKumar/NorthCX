"""Customer context from the company's own systems (plan, region, open orders...), fetched at conversation start.

Two ways to supply it: a Python object with an async `fetch(customer_id, session_id)` method (a "hook"), or an HTTPS
endpoint the platform calls with a signed request. Either way the result is cached briefly, size-limited, screened like
any other third-party text and shown to the agent as untrusted data. It is not saved with the customer's facts.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .notify import sign
from .safety.tool_output import DEFAULT_PATTERNS

MAX_KEYS, MAX_VALUE_CHARS, MAX_BODY = 30, 500, 64 * 1024
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_. -]{0,59}$")
_INJECTION = [re.compile(p, re.I) for p in DEFAULT_PATTERNS]


class ContextProvider(Protocol):
    async def fetch(self, customer_id: str, session_id: str) -> dict[str, Any]: ...


def sanitize(raw: Any) -> tuple[dict[str, str], list[str]]:
    """Keep simple, short, harmless values. Returns (facts, names of anything dropped and why)."""
    if not isinstance(raw, dict):
        return {}, ["response was not an object"]
    facts: dict[str, str] = {}
    dropped: list[str] = []
    for k, v in raw.items():
        if len(facts) >= MAX_KEYS:
            dropped.append(f"{str(k)[:60]}: too many keys")
            continue
        if not isinstance(k, str) or not _KEY.match(k):
            dropped.append(f"{str(k)[:60]}: bad name")
        elif isinstance(v, bool):
            facts[k] = "yes" if v else "no"
        elif isinstance(v, (int, float)) and v == v:
            facts[k] = str(v)
        elif isinstance(v, str):
            if any(p.search(v) for p in _INJECTION):
                dropped.append(f"{k}: looks like instructions")
            else:
                facts[k] = v[:MAX_VALUE_CHARS]
        else:
            dropped.append(f"{k}: unsupported value")
    return facts, dropped


@dataclass
class ContextResult:
    facts: dict[str, str] = field(default_factory=dict)
    status: str = "ok"  # ok | cached | error | timeout
    dropped: list[str] = field(default_factory=list)


class CachedContext:
    """Calls the provider at most once per customer per `ttl` seconds, never waits longer than `timeout`, and remembers
    a failure for `error_ttl` seconds so a system that is down is not hammered by every message."""

    def __init__(self, provider: ContextProvider, ttl: float = 300, timeout: float = 3.0, error_ttl: float = 30, max_entries: int = 5000,
                 clock=time.monotonic):
        self.provider, self.ttl, self.timeout, self.error_ttl, self.max = provider, ttl, timeout, error_ttl, max_entries
        self._clock = clock
        self._cache: dict[str, tuple[float, ContextResult]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, customer_id: str, session_id: str) -> ContextResult:
        now = self._clock()
        hit = self._cache.get(customer_id)
        if hit and hit[0] > now:
            return ContextResult(hit[1].facts, "cached" if hit[1].status in ("ok", "cached") else hit[1].status, hit[1].dropped)
        lock = self._locks.setdefault(customer_id, asyncio.Lock())
        async with lock:
            hit = self._cache.get(customer_id)  # another turn may have fetched while this one waited
            if hit and hit[0] > self._clock():
                return ContextResult(hit[1].facts, "cached" if hit[1].status in ("ok", "cached") else hit[1].status, hit[1].dropped)
            try:
                raw = await asyncio.wait_for(self.provider.fetch(customer_id, session_id), self.timeout)
                facts, dropped = sanitize(raw)
                res, ttl = ContextResult(facts, "ok", dropped), self.ttl
            except asyncio.TimeoutError:
                res, ttl = ContextResult({}, "timeout"), self.error_ttl
            except Exception:
                res, ttl = ContextResult({}, "error"), self.error_ttl
            if len(self._cache) >= self.max:
                self._cache = {k: v for k, v in self._cache.items() if v[0] > self._clock()}
                if len(self._cache) >= self.max:
                    self._cache.clear()
                self._locks = {k: v for k, v in self._locks.items() if v.locked()}
            self._cache[customer_id] = (self._clock() + ttl, res)
            return res

    def forget(self, customer_id: str) -> None:
        self._cache.pop(customer_id, None)


class HttpContextProvider:
    """POSTs `{"customerId", "sessionId"}`, signed like webhooks (`x-northcx-timestamp`, `x-northcx-signature`), and expects
    `{"facts": {...}}` (or a plain object) back. Redirects are not followed and large responses are refused."""

    def __init__(self, url: str, secret: str, client: httpx.AsyncClient | None = None, timeout: float = 3.0):
        if not url.startswith(("https://", "http://")):
            raise ValueError("NORTHCX_CONTEXT_URL must start with https:// (or http:// for local testing)")
        if not secret:
            raise ValueError("NORTHCX_CONTEXT_URL needs NORTHCX_CONTEXT_SECRET")
        self.url, self.secret = url, secret
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def fetch(self, customer_id: str, session_id: str) -> dict[str, Any]:
        body = json.dumps({"customerId": customer_id, "sessionId": session_id}, sort_keys=True).encode()
        ts = str(int(time.time()))
        async with self._client.stream("POST", self.url, content=body, headers={
                "content-type": "application/json", "x-northcx-timestamp": ts, "x-northcx-signature": sign(self.secret, ts, body)}) as r:
            if r.status_code != 200:
                raise RuntimeError(f"context endpoint returned {r.status_code}")
            data = b""
            async for chunk in r.aiter_bytes():
                data += chunk
                if len(data) > MAX_BODY:
                    raise RuntimeError("context response too large")
        out = json.loads(data)
        return out["facts"] if isinstance(out, dict) and isinstance(out.get("facts"), dict) else out
