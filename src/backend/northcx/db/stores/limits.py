"""Postgres-backed rate limiter and daily token ledger, shared by every server process.

If the database cannot be reached the limiter and ledger fall back to this process's own in-memory counters and log a
warning: a database outage makes limits per process again, never absent."""
from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import BigInteger, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from northcx.access import RateLimiter
from northcx.db.models import RateCounterRow, UsageDimRow, UsageLedgerRow
from northcx.db.stores._base import _Base
from northcx.reliability import UsageLedger
from northcx.tenancy import current_tenant

log = logging.getLogger("northcx.limits")
KEEP_SECONDS = 7200  # windows older than this are deleted (the longest window is 10 minutes)
WARN_EVERY = 60.0
LEDGER_REFRESH = 5.0  # the shared daily total is re-read at most this often per process


class _Warn:
    def __init__(self) -> None:
        self._last = 0.0

    def once_a_minute(self, what: str, err: Exception) -> None:
        now = time.monotonic()
        if now - self._last >= WARN_EVERY:
            self._last = now
            log.warning("%s: database unreachable (%s); using this process's own counters until it is back", what, type(err).__name__)


class PgLimiter(_Base):
    """Fixed windows: at most `limit` per window. A burst straddling two windows can pass up to twice the limit, which is
    the price of one cheap atomic statement per check (the in-memory limiter is a smoother token bucket)."""

    def __init__(self, engine: AsyncEngine, fallback: RateLimiter | None = None, cleanup_every: float = 300.0) -> None:
        super().__init__(engine)
        self.fallback = fallback or RateLimiter()
        self._cleanup_every, self._next_cleanup, self._warn = cleanup_every, 0.0, _Warn()

    async def _bump(self, key: str, window: int) -> tuple[int, int]:
        """Count one hit in the current window of `window` seconds; returns (count, window_start)."""
        start = cast(func.floor(func.extract("epoch", func.clock_timestamp()) / window) * window, BigInteger)
        stmt = pg_insert(RateCounterRow).values(key=f"{key}|{window}"[:300], window_start=start, count=1)
        stmt = stmt.on_conflict_do_update(index_elements=[RateCounterRow.key, RateCounterRow.window_start],
                                          set_={"count": RateCounterRow.count + 1}).returning(RateCounterRow.count, RateCounterRow.window_start)
        async with self._sm.begin() as s:
            count, began = (await s.execute(stmt)).one()
            if time.monotonic() >= self._next_cleanup:
                self._next_cleanup = time.monotonic() + self._cleanup_every
                await s.execute(delete(RateCounterRow).where(RateCounterRow.window_start < began - KEEP_SECONDS))
        return int(count), int(began)

    async def hit(self, key: str, limit_per_minute: float) -> tuple[bool, float]:
        """Returns (allowed, seconds until a retry could succeed)."""
        try:
            count, began = await self._bump(key, 60)
        except Exception as e:  # noqa: BLE001 - any database failure degrades to the local counters
            self._warn.once_a_minute("rate limits", e)
            return await self.fallback.hit(key, limit_per_minute)
        if count <= int(limit_per_minute):
            return True, 0.0
        return False, max(1.0, began + 60 - time.time())

    async def count(self, key: str, window_seconds: float) -> int:
        """Count one event for `key` and return how many fell in the current window."""
        try:
            return (await self._bump(key, max(1, int(window_seconds))))[0]
        except Exception as e:  # noqa: BLE001
            self._warn.once_a_minute("rate counters", e)
            return await self.fallback.count(key, window_seconds)


class PgUsageLedger(_Base):
    """Tokens used per day (UTC) per agent, in the database. `daily_limit` of None means no daily budget."""

    def __init__(self, engine: AsyncEngine, daily_limit: int | None = None, money_limit: float | None = None, currency: str = "USD") -> None:
        super().__init__(engine)
        self.daily_limit, self.money_limit, self.currency = daily_limit, money_limit, currency
        self.local = UsageLedger(daily_limit, money_limit, currency)  # used while the database is unreachable
        self._cache: dict[str, list[float]] = {}  # per tenant: [tokens, micros, time read]; one tenant's total is never another's
        self._warn = _Warn()

    @staticmethod
    def _today():
        return func.to_char(func.timezone("UTC", func.now()), "YYYY-MM-DD")

    settings: Any = None  # northcx.budget_settings.BudgetSettings

    async def limits(self) -> tuple[int | None, float | None, str]:
        if self.settings is None:
            return self.daily_limit, self.money_limit, self.currency
        return await self.settings.effective(self.daily_limit, self.money_limit, self.currency)

    async def usage_dims(self, days: int) -> list[dict]:
        cutoff = func.to_char(func.timezone("UTC", func.now()) - func.make_interval(0, 0, 0, days - 1), "YYYY-MM-DD")
        q = select(UsageDimRow.kind, UsageDimRow.key, UsageDimRow.day, UsageDimRow.tokens, UsageDimRow.cost_micros).where(UsageDimRow.day >= cutoff).order_by(UsageDimRow.day, UsageDimRow.kind, UsageDimRow.key)
        try:
            async with self._ro() as s:
                return [{"kind": r.kind, "key": r.key, "day": r.day, "tokens": int(r.tokens), "cost": int(r.cost_micros) / 1_000_000} for r in (await s.execute(q)).all()]
        except Exception as e:  # noqa: BLE001
            self._warn.once_a_minute("usage", e)
            return await self.local.usage_dims(days)

    async def charge(self, agent_id: str, tokens: int, cost: float = 0.0, model: str | None = None, team: str | None = None) -> None:
        tokens = max(0, int(tokens))
        micros = max(0, round(cost * 1_000_000))
        self.local.add(agent_id, tokens)
        if model:
            self.local._dim("model", model, tokens, cost)
        if team:
            self.local._dim("team", team, tokens, cost)
        if micros:
            self.local.add_money(agent_id, cost)
        c = self._cache.setdefault(current_tenant(), [0, 0, -1e9])
        c[0] += tokens
        c[1] += micros
        if not tokens and not micros:
            return
        stmt = pg_insert(UsageLedgerRow).values(agent_id=agent_id, day=self._today(), tokens=tokens, cost_micros=micros)
        stmt = stmt.on_conflict_do_update(index_elements=[UsageLedgerRow.tenant_id, UsageLedgerRow.agent_id, UsageLedgerRow.day],
                                          set_={"tokens": UsageLedgerRow.tokens + tokens, "cost_micros": UsageLedgerRow.cost_micros + micros})
        try:
            async with self._sm.begin() as s:
                await s.execute(stmt)
                for kind, key in (("model", model), ("team", team)):
                    if key:
                        d = pg_insert(UsageDimRow).values(day=self._today(), kind=kind, key=key[:200], tokens=tokens, cost_micros=micros)
                        await s.execute(d.on_conflict_do_update(index_elements=[UsageDimRow.tenant_id, UsageDimRow.day, UsageDimRow.kind, UsageDimRow.key],
                                                                set_={"tokens": UsageDimRow.tokens + tokens, "cost_micros": UsageDimRow.cost_micros + micros}))
        except Exception as e:  # noqa: BLE001
            self._warn.once_a_minute("token budget", e)

    async def spent(self, agent_id: str | None = None) -> int:
        q = select(func.coalesce(func.sum(UsageLedgerRow.tokens), 0)).where(UsageLedgerRow.day == self._today())
        if agent_id is not None:
            q = q.where(UsageLedgerRow.agent_id == agent_id)
        try:
            async with self._ro() as s:
                return int((await s.execute(q)).scalar_one())
        except Exception as e:  # noqa: BLE001
            self._warn.once_a_minute("token budget", e)
            return self.local.used_today(agent_id)

    async def money_spent(self, agent_id: str | None = None) -> float:
        q = select(func.coalesce(func.sum(UsageLedgerRow.cost_micros), 0)).where(UsageLedgerRow.day == self._today())
        if agent_id is not None:
            q = q.where(UsageLedgerRow.agent_id == agent_id)
        try:
            async with self._ro() as s:
                return int((await s.execute(q)).scalar_one()) / 1_000_000
        except Exception as e:  # noqa: BLE001
            self._warn.once_a_minute("money budget", e)
            return self.local.money_today(agent_id)

    async def usage_rows(self, days: int) -> list[dict]:
        """Tokens and money per agent per UTC day for the last `days` days, for the caller's tenant (row-level security)."""
        cutoff = func.to_char(func.timezone("UTC", func.now()) - func.make_interval(0, 0, 0, days - 1), "YYYY-MM-DD")
        q = select(UsageLedgerRow.agent_id, UsageLedgerRow.day, UsageLedgerRow.tokens, UsageLedgerRow.cost_micros).where(UsageLedgerRow.day >= cutoff).order_by(UsageLedgerRow.day, UsageLedgerRow.agent_id)
        try:
            async with self._ro() as s:
                return [{"agent": r.agent_id, "day": r.day, "tokens": int(r.tokens), "cost": int(r.cost_micros) / 1_000_000} for r in (await s.execute(q)).all()]
        except Exception as e:  # noqa: BLE001
            self._warn.once_a_minute("usage", e)
            return await self.local.usage_rows(days)

    async def over_budget(self) -> bool:
        tokens_limit, money_limit, _ = await self.limits()
        if tokens_limit is None and money_limit is None:
            return False
        c = self._cache.setdefault(current_tenant(), [0, 0, -1e9])
        if time.monotonic() - c[2] >= LEDGER_REFRESH:  # one shared read every few seconds, plus this process's own additions in between
            c[0], c[2] = await self.spent(None), time.monotonic()
            c[1] = round(await self.money_spent(None) * 1_000_000)
        return (tokens_limit is not None and c[0] >= tokens_limit) or \
               (money_limit is not None and c[1] >= round(money_limit * 1_000_000))
