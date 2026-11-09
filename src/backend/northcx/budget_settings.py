"""Budgets an administrator sets from the Admin app (decision 164): a daily token limit, a daily spending limit and its currency, per tenant.

A value set here replaces the environment default (`NORTHCX_DAILY_TOKEN_BUDGET`, `NORTHCX_DAILY_BUDGET`, `NORTHCX_BUDGET_CURRENCY`) for that tenant only;
clearing it brings the default back. A spending limit is accepted only when every model provider has a price in that currency, because a model with no
price would spend without ever counting against it."""
from __future__ import annotations

import re
import time
from typing import Any, Protocol

from .tenancy import current_tenant

KEY = "budget"
CACHE_SECONDS = 5.0


class SettingsRepo(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def put(self, key: str, data: dict[str, Any], by: str) -> None: ...
    async def delete(self, key: str) -> bool: ...


class InMemorySettings:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self._items.get((current_tenant(), key))

    async def put(self, key: str, data: dict[str, Any], by: str) -> None:
        self._items[(current_tenant(), key)] = dict(data)

    async def delete(self, key: str) -> bool:
        return self._items.pop((current_tenant(), key), None) is not None


class BudgetError(ValueError):
    pass


def validate(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    tokens, money, cur = data.get("dailyTokenLimit"), data.get("dailyMoneyLimit"), data.get("currency")
    if tokens is not None:
        if isinstance(tokens, bool) or not isinstance(tokens, int) or not 1000 <= tokens <= 10_000_000_000:
            raise BudgetError("The daily token limit must be a whole number from 1,000 up (leave it empty for no limit)")
        out["dailyTokenLimit"] = tokens
    if money is not None:
        if isinstance(money, bool) or not isinstance(money, (int, float)) or not 0 < money <= 1e9:
            raise BudgetError("The daily spending limit must be a positive number (leave it empty for no limit)")
        out["dailyMoneyLimit"] = float(money)
    if cur is not None:
        if not isinstance(cur, str) or not re.fullmatch(r"[A-Za-z]{3}", cur):
            raise BudgetError("The currency must be a three-letter code such as USD or EUR")
        out["currency"] = cur.upper()
    return out


class BudgetSettings:
    def __init__(self, repo: SettingsRepo | None = None):
        self.repo = repo or InMemorySettings()
        self._cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

    async def get(self) -> dict[str, Any] | None:
        tenant = current_tenant()
        hit = self._cache.get(tenant)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        try:
            value = await self.repo.get(KEY)
        except Exception:  # noqa: BLE001 - the environment defaults still apply if the setting cannot be read
            return hit[1] if hit else None
        self._cache[tenant] = (time.monotonic(), value)
        return value

    async def put(self, data: dict[str, Any], by: str) -> dict[str, Any]:
        clean = validate(data)
        await self.repo.put(KEY, clean, by)
        self._cache.pop(current_tenant(), None)
        return clean

    async def clear(self) -> bool:
        gone = await self.repo.delete(KEY)
        self._cache.pop(current_tenant(), None)
        return gone

    async def effective(self, default_tokens: int | None, default_money: float | None, default_currency: str) -> tuple[int | None, float | None, str]:
        """(token limit, money limit, currency) for this tenant: its own settings where set, else the environment's."""
        s = await self.get() or {}
        return (s.get("dailyTokenLimit", default_tokens), s.get("dailyMoneyLimit", default_money), s.get("currency", default_currency))
