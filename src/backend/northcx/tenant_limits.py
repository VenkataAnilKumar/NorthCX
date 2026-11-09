"""Per-tenant limits and configuration (WP2.5 and WP2.7).

The platform operator, not the tenant, sets these: a tenant's own administrator can read them but not raise them. Resolution order for each value is
the tenant's own setting, then the platform default from the environment, then no limit, so a single-company deployment with nothing set behaves as before.
    requestsPerMinute  a ceiling on all requests from one tenant together (each key still has its own limit)
    maxOutputs         the most saved Outputs a tenant may hold
    retentionDays      how long idle conversations are kept before they are erased (overrides NORTHCX_RETENTION_DAYS for this tenant)
"""
from __future__ import annotations

import time
from typing import Any

from .budget_settings import InMemorySettings, SettingsRepo
from .tenancy import TENANT

KEY = "tenant_limits"
CACHE_SECONDS = 5.0
FIELDS = {"requestsPerMinute": (1, 1_000_000), "maxOutputs": (1, 10_000_000), "retentionDays": (1, 3650)}


class LimitError(ValueError):
    pass


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LimitError("Limits are a mapping")
    unknown = set(data) - set(FIELDS)
    if unknown:
        raise LimitError(f"Unknown limit(s): {', '.join(sorted(unknown))} (limits: {', '.join(FIELDS)})")
    out: dict[str, Any] = {}
    for k, v in data.items():
        if v is None:
            continue
        lo, hi = FIELDS[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise LimitError(f"{k} must be a number from {lo} to {hi} (leave it out for no limit)")
        out[k] = v if k == "retentionDays" else int(v)
    return out


class TenantLimits:
    def __init__(self, repo: SettingsRepo | None = None, defaults: dict[str, Any] | None = None):
        self.repo = repo or InMemorySettings()
        self.defaults = {k: v for k, v in (defaults or {}).items() if v}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def _own(self, tenant: str) -> dict[str, Any]:
        hit = self._cache.get(tenant)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        token = TENANT.set(tenant)
        try:
            v = await self.repo.get(KEY) or {}
        except Exception:  # noqa: BLE001 - keep the last known limits rather than dropping them (or inventing new ones) when the setting cannot be read
            return hit[1] if hit else {}
        finally:
            TENANT.reset(token)
        self._cache[tenant] = (time.monotonic(), v)
        return v

    async def effective(self, tenant: str) -> dict[str, Any]:
        """{name: {value, source}} for every limit; source is tenant, platform or none."""
        own = await self._own(tenant)
        out = {}
        for k in FIELDS:
            if k in own:
                out[k] = {"value": own[k], "source": "tenant"}
            elif k in self.defaults:
                out[k] = {"value": self.defaults[k], "source": "platform"}
            else:
                out[k] = {"value": None, "source": "none"}
        return out

    async def value(self, tenant: str, name: str) -> Any:
        return (await self.effective(tenant))[name]["value"]

    async def put(self, tenant: str, data: dict[str, Any], by: str) -> dict[str, Any]:
        clean = validate(data)
        token = TENANT.set(tenant)
        try:
            await self.repo.put(KEY, clean, by)
        finally:
            TENANT.reset(token)
        self._cache.pop(tenant, None)
        return await self.effective(tenant)

    async def clear(self, tenant: str) -> None:
        token = TENANT.set(tenant)
        try:
            await self.repo.delete(KEY)
        finally:
            TENANT.reset(token)
        self._cache.pop(tenant, None)
