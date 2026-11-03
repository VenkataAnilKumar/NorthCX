"""Scheduled re-crawls (K5): a saved crawl that runs again every so many hours.

A schedule is only a saved crawl request, so everything that limits a crawl still applies on every run: only hosts the operator
allowed, no private addresses, robots.txt, delays, page and size caps, one crawl per source at a time. The interval is at least
one hour. Several server processes can share the database: a run is claimed atomically, so each schedule runs once per interval.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .crawler import CrawlConfig, CrawlRefused, Crawler

log = logging.getLogger("northcx.crawl_schedule")
MIN_HOURS, MAX_HOURS, MAX_SCHEDULES = 1.0, 24.0 * 30, 20
CONFIG_KEYS = ("start_url", "max_pages", "max_depth", "delay", "include_paths", "exclude_paths", "use_sitemap", "prune")


@dataclass
class Schedule:
    source_id: str
    config: dict[str, Any]
    every_hours: float
    next_run: float
    created_by: str
    id: str = field(default_factory=lambda: "cs-" + uuid.uuid4().hex[:16])
    last_run: float | None = None
    last_job_id: str | None = None
    last_result: str | None = None
    enabled: bool = True
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        c = self.config
        return {"id": self.id, "sourceId": self.source_id, "url": c["start_url"], "maxPages": c["max_pages"], "maxDepth": c["max_depth"], "prune": c["prune"],
                "everyHours": self.every_hours, "nextRun": self.next_run, "lastRun": self.last_run, "lastJobId": self.last_job_id, "lastResult": self.last_result,
                "enabled": self.enabled, "createdBy": self.created_by, "createdAt": self.created_at}


class ScheduleRepo(Protocol):
    async def list(self) -> list[Schedule]: ...
    async def add(self, s: Schedule) -> bool: ...
    async def delete(self, schedule_id: str) -> bool: ...
    async def set_enabled(self, schedule_id: str, enabled: bool, now: float) -> bool: ...
    async def claim_due(self, now: float, limit: int = 5) -> list[Schedule]: ...
    async def record(self, schedule_id: str, at: float, job_id: str | None, result: str) -> None: ...


class InMemorySchedules:
    def __init__(self) -> None:
        self.items: dict[str, Schedule] = {}

    async def list(self) -> list[Schedule]:
        return sorted(self.items.values(), key=lambda s: s.created_at)

    async def add(self, s: Schedule) -> bool:
        if len(self.items) >= MAX_SCHEDULES or any(x.source_id == s.source_id and x.config["start_url"] == s.config["start_url"] for x in self.items.values()):
            return False
        self.items[s.id] = s
        return True

    async def delete(self, schedule_id: str) -> bool:
        return self.items.pop(schedule_id, None) is not None

    async def set_enabled(self, schedule_id: str, enabled: bool, now: float) -> bool:
        s = self.items.get(schedule_id)
        if s is None:
            return False
        s.enabled = enabled
        if enabled:
            s.next_run = max(s.next_run, now)
        return True

    async def claim_due(self, now: float, limit: int = 5) -> list[Schedule]:
        due = sorted((s for s in self.items.values() if s.enabled and s.next_run <= now), key=lambda s: s.next_run)[:limit]
        for s in due:
            s.next_run = now + s.every_hours * 3600
        return due

    async def record(self, schedule_id: str, at: float, job_id: str | None, result: str) -> None:
        s = self.items.get(schedule_id)
        if s is not None:
            s.last_run, s.last_job_id, s.last_result = at, job_id, result[:300]

    async def erase_source(self, source_id: str) -> None:
        for k in [k for k, v in self.items.items() if v.source_id == source_id]:
            del self.items[k]


def config_from(cfg: CrawlConfig) -> dict[str, Any]:
    return {"start_url": cfg.start_url, "max_pages": cfg.max_pages, "max_depth": cfg.max_depth, "delay": cfg.delay, "include_paths": list(cfg.include_paths),
            "exclude_paths": list(cfg.exclude_paths), "use_sitemap": cfg.use_sitemap, "prune": cfg.prune}


class CrawlScheduler:
    def __init__(self, crawler: Crawler, repo: ScheduleRepo, interval: float = 60.0):
        self.crawler, self.repo, self.interval = crawler, repo, interval
        self._task: asyncio.Task | None = None

    async def create(self, source_id: str, cfg: CrawlConfig, every_hours: float, by: str, now: float | None = None) -> Schedule:
        """Validates exactly as a crawl would (allowed host, limits, known source), then saves it. The first run is one interval from now."""
        if not MIN_HOURS <= every_hours <= MAX_HOURS:
            raise CrawlRefused(f"A schedule must repeat every {MIN_HOURS:g} hours to {MAX_HOURS:g} hours")
        cfg.check()
        if await self.crawler.store.get_source(source_id) is None:
            raise CrawlRefused("Unknown source")
        await self.crawler.check_url(cfg.start_url)
        now = time.time() if now is None else now
        s = Schedule(source_id, config_from(cfg), every_hours, now + every_hours * 3600, by, created_at=now)
        if not await self.repo.add(s):
            raise CrawlRefused(f"This source already has a schedule for that address, or there are already {MAX_SCHEDULES} schedules")
        return s

    async def tick(self, now: float | None = None) -> int:
        """Starts every schedule that is due. A run that cannot start (another crawl of the source is running, the host is no longer allowed) is recorded and tried again next interval."""
        now = time.time() if now is None else now
        started = 0
        for s in await self.repo.claim_due(now):
            try:
                job = await self.crawler.start(s.source_id, CrawlConfig(**{k: s.config[k] for k in CONFIG_KEYS if k in s.config}))
            except CrawlRefused as e:
                await self.repo.record(s.id, now, None, f"not started: {e}"[:300])
                continue
            except Exception as e:
                log.exception("scheduled crawl failed to start")
                await self.repo.record(s.id, now, None, f"not started: {type(e).__name__}")
                continue
            started += 1
            await self.repo.record(s.id, now, job.id, "started")
        return started

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("crawl scheduler pass failed")
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
