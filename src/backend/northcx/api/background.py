"""The server's background jobs, started according to the process role.

NORTHCX_ROLE: `all` (default) serves requests and runs the jobs; `api` only serves requests; `worker` runs the jobs (and answers
health checks, but should not be given customer traffic). Each pass of a job takes a lease first (northcx/leases.py), so
several workers never repeat one another's work."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from northcx.audit import AuditEntry
from northcx.leases import Leases, run_leased
from northcx.tenancy import for_each_tenant

log = logging.getLogger("northcx.server")
ROLES = ("all", "api", "worker")
LEASE_SECONDS = 120.0  # longer than any one pass should take; if a worker dies mid-pass the lease runs out and another takes over


def runs_jobs(role: str) -> bool:
    return role in ("all", "worker")


def _every(seconds: float, name: str, job: Callable[[], Awaitable[Any]], leases: Leases | None, lease_seconds: float = LEASE_SECONDS, message: str | None = None,
           tenants: Any = None) -> asyncio.Task:
    async def per_tenant() -> None:
        await for_each_tenant(tenants, job, log)  # each pass runs once per tenant, as that tenant

    async def loop() -> None:
        while True:
            await asyncio.sleep(seconds)
            try:
                await run_leased(leases, name, lease_seconds, per_tenant)
            except Exception:  # keep going; a failed pass is retried on the next tick
                log.exception(message or f"{name} pass failed")

    return asyncio.create_task(loop())


def start_background(role: str, leases: Leases | None, *, runtime: Any, traces: Any, flow: Any, agents: Any, approval_ttl_seconds: float | None,
                     alerts: Any, privacy: Any, audit: Any, retention_days: float | None, kb: Any, crawl_scheduler: Any,
                     tenants: Any = None, automations: Any = None) -> Callable[[], Awaitable[None]]:
    """Start the jobs this role runs. Returns a coroutine function that stops them."""
    tasks: list[asyncio.Task] = []
    indexer = getattr(kb, "indexer", None)
    if not runs_jobs(role):
        async def nothing() -> None:
            return None
        return nothing
    if runtime.outbox.notifier is not None:  # retry deliveries that failed (email, webhooks) with back-off
        tasks.append(_every(15, "outbox", runtime.outbox.flush, leases, message="outbox flush failed", tenants=tenants))
    if approval_ttl_seconds:  # periodically expire stale approvals and hand those conversations to a person
        tasks.append(_every(max(1.0, min(60.0, approval_ttl_seconds / 2)), "approvals",
                            lambda: flow.expire_stale(agents, approval_ttl_seconds), leases, message="approval expiry pass failed", tenants=tenants))
    if runtime.exports is not None:
        tasks.append(_every(10, "trace-export", lambda: runtime.exports.flush(traces), leases, message="trace export pass failed", tenants=tenants))
    if alerts is not None:
        tasks.append(_every(60, "alerts", alerts.evaluate, leases, message="alert evaluation failed", tenants=tenants))
    if runtime.inbox is not None:
        tasks.append(_every(10, "inbox", lambda: runtime.inbox.flush(runtime.handoffs), leases, message="inbox delivery pass failed", tenants=tenants))
    if retention_days or getattr(runtime, "tenant_limits", None) is not None:  # age out old conversations once an hour, as long as this tenant (or the platform) keeps them for a set time
        async def retain() -> None:
            from northcx.tenancy import current_tenant
            days = retention_days
            if getattr(runtime, "tenant_limits", None) is not None:      # this tenant's own period, else the platform's
                days = await runtime.tenant_limits.value(current_tenant(), "retentionDays") or retention_days
            if not days:
                return
            r = await privacy.purge_idle(days)
            if r["sessions"]:
                await audit.append(AuditEntry(actor="system", role="system", key_id=None, action="privacy.retention", target=f"older than {days:g} days",
                                              outcome="success", detail=r))

        tasks.append(_every(3600, "retention", retain, leases, 600.0, "retention sweep failed", tenants=tenants))
    if indexer is not None:
        indexer.tenants = tenants
        indexer.start()
    if crawl_scheduler is not None:
        crawl_scheduler.tenants = tenants
        crawl_scheduler.start()
    if automations is not None:
        tasks.append(_every(30, "automations", automations.tick, leases, lease_seconds=60, tenants=tenants))

    async def stop() -> None:
        if indexer is not None:
            await indexer.stop()
        if crawl_scheduler is not None:
            await crawl_scheduler.stop()
        for t in tasks:
            t.cancel()

    return stop
