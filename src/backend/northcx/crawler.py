"""Web crawler for the knowledge base: reads a site's public pages into knowledge documents, politely and safely.

The operator decides which hosts may be crawled (`NORTHCX_CRAWL_HOSTS`); nobody can point it elsewhere. It uses https (http only for localhost), refuses
addresses inside private networks unless the operator allows them, follows redirects only within the same host (re-checking every hop), obeys robots.txt
and its crawl delay, waits between requests, and is bounded in pages, depth, bytes and time. Pages with query strings are skipped (calendars and
searches go on forever), and so are sections excluded by the caller. Each page becomes (or updates) one document, so the usual "unchanged / updated"
bookkeeping and the re-run of regression scenarios after knowledge changes apply. Pages that disappeared from the site can be removed (`prune`).
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from . import __version__
from .ingest import MAX_FILE_BYTES, IngestError, extract, from_html, from_pdf
from .knowledge import KnowledgeError, KnowledgeStore, valid_id

LOCAL = {"localhost", "127.0.0.1", "::1"}
USER_AGENT = f"NorthCXBot/{__version__}"
MAX_PAGES, MAX_DEPTH = 200, 4
MIN_DELAY, MAX_DELAY = 0.25, 10.0
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_SITEMAP_URLS = 1000
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "text/markdown", "text/x-markdown")
_LOC = re.compile(r"<(?:url|sitemap)\b.*?</(?:url|sitemap)>", re.S | re.I)
_LOC_URL = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_LASTMOD = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", re.I)


class CrawlRefused(ValueError):
    """The request is not allowed (host, address or settings). The message is safe to show."""


@dataclass
class CrawlConfig:
    start_url: str
    max_pages: int = 50
    max_depth: int = 2
    delay: float = 1.0
    include_paths: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    use_sitemap: bool = True
    prune: bool = False
    max_minutes: float = 15.0

    def check(self) -> None:
        if not 1 <= self.max_pages <= MAX_PAGES or not 0 <= self.max_depth <= MAX_DEPTH:
            raise CrawlRefused(f"max_pages must be 1-{MAX_PAGES} and max_depth 0-{MAX_DEPTH}")
        if not MIN_DELAY <= self.delay <= MAX_DELAY:
            raise CrawlRefused(f"delay must be between {MIN_DELAY} and {MAX_DELAY} seconds")
        if not 1 <= self.max_minutes <= 60:
            raise CrawlRefused("max_minutes must be between 1 and 60")
        for p in [*self.include_paths, *self.exclude_paths]:
            if not p.startswith("/") or len(p) > 200 or "?" in p or "#" in p:
                raise CrawlRefused("include_paths and exclude_paths are path prefixes that start with / (for example /help/)")
        if len(self.include_paths) > 20 or len(self.exclude_paths) > 50:
            raise CrawlRefused("too many include or exclude paths")


@dataclass
class CrawlJob:
    source_id: str
    host: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = "running"      # running | done | failed | stopped
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    fetched: int = 0
    results: Counter = field(default_factory=Counter)  # created | updated | unchanged
    skipped: Counter = field(default_factory=Counter)  # reason -> count
    pruned: int = 0
    errors: list[str] = field(default_factory=list)
    message: str = ""
    bytes: int = 0
    gone: set[str] = field(default_factory=set)  # addresses the site said no longer exist (404/410)

    def to_dict(self) -> dict[str, Any]:
        return {"jobId": self.id, "sourceId": self.source_id, "host": self.host, "state": self.state, "startedAt": self.started_at, "finishedAt": self.finished_at,
                "fetched": self.fetched, "created": self.results["created"], "updated": self.results["updated"], "unchanged": self.results["unchanged"],
                "skipped": dict(self.skipped), "pruned": self.pruned, "errors": self.errors[:20], "message": self.message}


def hosts_from(value: str | None) -> set[str]:
    out = {h.strip().lower() for h in (value or "").split(",") if h.strip()}
    for h in out:
        if not re.fullmatch(r"[a-z0-9.-]+(:\d+)?", h):
            raise ValueError(f"NORTHCX_CRAWL_HOSTS: '{h}' is not a host name (use names like help.example.com, optionally with :port)")
    return out


def normalise(url: str) -> str:
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    port = f":{u.port}" if u.port and not ((u.scheme == "https" and u.port == 443) or (u.scheme == "http" and u.port == 80)) else ""
    return urlunsplit((u.scheme.lower(), host + port, u.path or "/", u.query, ""))


def document_id(url: str) -> str:
    u = urlsplit(url)
    raw = f"web:{u.netloc}{u.path or '/'}"
    safe = re.sub(r"[^A-Za-z0-9._:/-]", "_", raw)
    if len(safe) > 190 or safe != raw:
        import hashlib
        safe = safe[:170].rstrip("/") + "-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
    return safe if valid_id(safe) else "web:" + safe.lstrip(":/")


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


def private_address(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped  # type: ignore[assignment]
    return a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified


class Crawler:
    def __init__(self, store: KnowledgeStore, allowed_hosts: set[str], allow_private: bool = False, client: httpx.AsyncClient | None = None,
                 resolver: Resolver = system_resolver, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, clock: Callable[[], float] = time.monotonic,
                 on_change: Callable[[str], None] | None = None):
        self.store, self.allowed, self.allow_private = store, allowed_hosts, allow_private
        self._client = client or httpx.AsyncClient(timeout=15.0, follow_redirects=False, headers={"user-agent": USER_AGENT})
        self.resolver, self.sleep, self.clock, self.on_change = resolver, sleep, clock, on_change
        self.jobs: dict[str, CrawlJob] = {}
        self.active: dict[str, str] = {}
        self._tasks: set[asyncio.Task] = set()

    # ---- what may be fetched ----
    async def check_url(self, url: str) -> None:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
        netloc = host + (f":{u.port}" if u.port else "")
        if u.scheme not in ("https", "http") or not host or u.username or u.password:
            raise CrawlRefused("Only plain https addresses are crawled")
        if u.scheme == "http" and host not in LOCAL:
            raise CrawlRefused("Only https addresses are crawled (http is allowed for localhost only)")
        if netloc not in self.allowed and host not in self.allowed:
            raise CrawlRefused(f"'{netloc}' is not in NORTHCX_CRAWL_HOSTS; the operator must allow a host before it can be crawled")
        if not self.allow_private and host not in LOCAL:
            try:
                addrs = await self.resolver(host, u.port or (443 if u.scheme == "https" else 80))
            except OSError:
                raise CrawlRefused(f"'{host}' could not be looked up") from None
            if not addrs or any(private_address(a) for a in addrs):
                raise CrawlRefused(f"'{host}' points inside a private network, which is not crawled unless the operator allows it (NORTHCX_CRAWL_ALLOW_PRIVATE)")

    # ---- starting ----
    def jobs_list(self) -> list[dict[str, Any]]:
        return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: -j.started_at)]

    async def start(self, source_id: str, cfg: CrawlConfig) -> CrawlJob:
        cfg.check()
        if await self.store.get_source(source_id) is None:
            raise CrawlRefused("Unknown source")
        await self.check_url(cfg.start_url)
        if source_id in self.active:
            raise CrawlRefused("A crawl of this source is already running")
        job = CrawlJob(source_id, urlsplit(cfg.start_url).netloc.lower())
        self.jobs[job.id] = job
        for old in sorted(self.jobs.values(), key=lambda j: j.started_at)[:-20]:
            self.jobs.pop(old.id, None)
        self.active[source_id] = job.id
        task = asyncio.ensure_future(self._run(job, cfg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def wait(self) -> None:
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ---- fetching ----
    async def _fetch(self, url: str, start_host: str, cap: int, job: CrawlJob, quiet: bool = False, xml: bool = False) -> tuple[httpx.Response, bytes] | None:
        """One page, following up to three redirects within the same host. None when it is not a usable page (the reason is counted)."""
        for _ in range(4):
            await self.check_url(url)
            if urlsplit(url).netloc.lower() != start_host:
                raise CrawlRefused("redirected to another host")
            async with self._client.stream("GET", url, headers={"accept": "text/html,text/plain,application/pdf;q=0.8", "user-agent": USER_AGENT}) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        return None
                    url = normalise(urljoin(url, loc))
                    continue
                if r.status_code in (404, 410):
                    job.gone.add(url)
                if r.status_code >= 400:
                    if not quiet:
                        job.skipped[f"status {r.status_code}"] += 1
                    return None
                kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind != "application/pdf" and kind not in TEXT_TYPES and kind and not (xml and kind in ("application/xml", "text/xml", "application/octet-stream", "application/gzip-not-supported")):
                    job.skipped["not a page (" + kind[:40] + ")"] += 1
                    return None
                limit = MAX_FILE_BYTES["pdf"] if kind == "application/pdf" else min(cap, MAX_FILE_BYTES["html"])
                body = b""
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > limit:
                        job.skipped["too large"] += 1
                        return None
                job.bytes += len(body)
                return r, body
        job.skipped["too many redirects"] += 1
        return None

    async def _robots(self, origin: str, start_host: str) -> RobotFileParser:
        """The site's robots.txt. Missing means everything is allowed; a server error or an unreachable file means the site is not crawled."""
        url = urljoin(origin, "/robots.txt")
        await self.check_url(url)
        rp = RobotFileParser()
        try:
            async with self._client.stream("GET", url, headers={"user-agent": USER_AGENT}) as r:
                if r.status_code >= 500:
                    raise CrawlRefused("The site's robots.txt returned an error, so the site is not crawled")
                body = b""
                if r.status_code == 200:
                    async for chunk in r.aiter_bytes():
                        body += chunk
                        if len(body) > 256 * 1024:
                            body = body[: 256 * 1024]
                            break
        except httpx.HTTPError:
            raise CrawlRefused("robots.txt could not be fetched, so the site is not crawled") from None
        rp.parse(body.decode("utf-8", "replace").splitlines())
        return rp

    async def _sitemap(self, urls: list[str], start_host: str, job: CrawlJob, depth: int = 0) -> dict[str, float | None]:
        found: dict[str, float | None] = {}
        for sm in urls[:5]:
            try:
                got = await self._fetch(sm, start_host, 2 * 1024 * 1024, job, quiet=True, xml=True)
            except (CrawlRefused, httpx.HTTPError):
                continue
            if got is None:
                continue
            text = got[1].decode("utf-8", "replace")
            for block in _LOC.findall(text):
                m = _LOC_URL.search(block)
                if not m:
                    continue
                loc = m.group(1).replace("&amp;", "&")
                if block.lower().startswith("<sitemap") and depth < 1:
                    found.update(await self._sitemap([loc], start_host, job, depth + 1))
                elif block.lower().startswith("<url"):
                    lm = _LASTMOD.search(block)
                    found[normalise(loc)] = _parse_date(lm.group(1)) if lm else None
                if len(found) >= MAX_SITEMAP_URLS:
                    return found
        return found

    # ---- the crawl ----
    async def _run(self, job: CrawlJob, cfg: CrawlConfig) -> None:
        began = self.clock()
        try:
            start = normalise(cfg.start_url)
            host = job.host
            origin = f"{urlsplit(start).scheme}://{host}"
            rp = await self._robots(origin, host)
            delay = cfg.delay
            if rp is not None and (cd := rp.crawl_delay(USER_AGENT)):
                delay = max(delay, min(float(cd), MAX_DELAY))
            lastmod: dict[str, float | None] = {}
            seeds = [(start, 0)]
            if cfg.use_sitemap:
                sitemaps = list(rp.site_maps() or []) if rp is not None else []
                lastmod = await self._sitemap(sitemaps or [urljoin(origin, "/sitemap.xml")], host, job)
                seeds += [(u, 1) for u in lastmod if u != start]
            seen: set[str] = set()
            queue = list(seeds)
            while queue and job.fetched < cfg.max_pages:
                url, depth = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                reason = self._skip_reason(url, host, cfg, rp)
                if reason:
                    job.skipped[reason] += 1
                    continue
                if self.clock() - began > cfg.max_minutes * 60 or job.bytes > MAX_TOTAL_BYTES:
                    job.message = "Stopped at the time or size limit"
                    job.state = "stopped"
                    break
                if job.fetched:
                    await self.sleep(delay)
                try:
                    got = await self._fetch(url, host, 2 * 1024 * 1024, job)
                except CrawlRefused as e:
                    job.skipped[str(e)[:80]] += 1
                    continue
                except httpx.HTTPError as e:
                    job.skipped[f"could not be fetched ({type(e).__name__})"] += 1
                    continue
                if got is None:
                    continue
                r, body = got
                job.fetched += 1
                final = normalise(str(r.url))  # after any redirects: the page lives (and is stored) at the address it ended on
                seen.add(final)
                url = final
                try:
                    ex = await self._read(r, body, url)
                except IngestError as e:
                    job.skipped[str(e)[:80]] += 1
                    continue
                for link in ex.links:
                    nxt = normalise(urljoin(url, link))
                    if depth < cfg.max_depth and nxt not in seen and len(queue) < 5000 and urlsplit(nxt).scheme in ("http", "https"):
                        queue.append((nxt, depth + 1))
                modified = _parse_date(r.headers.get("last-modified")) or lastmod.get(url)
                try:
                    res = await self.store.upsert(job.source_id, document_id(url), ex.title, url, ex.text, modified)
                    job.results[res.status] += 1
                except KnowledgeError as e:
                    job.skipped[str(e)[:80]] += 1
            if job.state == "running":
                job.state = "done"
                if cfg.prune and not queue:
                    job.pruned = await self._prune(job, host, seen)
                elif cfg.prune:
                    job.message = "Stopped at the page limit, so pages no longer on the site were not removed"
            if (job.results["created"] or job.results["updated"] or job.pruned) and self.on_change:
                self.on_change(f"crawl of {job.host} for source {job.source_id}")
        except CrawlRefused as e:
            job.state, job.message = "failed", str(e)
        except Exception as e:  # a crawl never takes the server down
            job.state, job.message = "failed", f"The crawl failed ({type(e).__name__})"
            job.errors.append(type(e).__name__)
        finally:
            job.finished_at = time.time()
            self.active.pop(job.source_id, None)

    def _skip_reason(self, url: str, host: str, cfg: CrawlConfig, rp: RobotFileParser | None) -> str | None:
        u = urlsplit(url)
        if u.netloc.lower() != host:
            return "another host"
        if u.query:
            return "has a query string"
        if cfg.include_paths and not any(u.path.startswith(p) for p in cfg.include_paths) and url != normalise(cfg.start_url):
            return "outside the included paths"
        if any(u.path.startswith(p) for p in cfg.exclude_paths):
            return "in an excluded path"
        if re.search(r"\.(png|jpe?g|gif|svg|webp|ico|css|js|zip|gz|mp4|mp3|woff2?|exe|dmg|docx?|xlsx?|pptx?)$", u.path, re.I):
            return "not a page"
        if rp is not None and not rp.can_fetch(USER_AGENT, url):
            return "disallowed by robots.txt"
        return None

    async def _read(self, r: httpx.Response, body: bytes, url: str):
        kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
        fallback = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1] or urlsplit(url).netloc
        if kind == "application/pdf":
            return await from_pdf(body, fallback)
        if kind in ("text/html", "application/xhtml+xml") or not kind:
            return from_html(body.decode(r.encoding or "utf-8", "replace"), fallback)
        return await extract(body, fallback, kind)

    async def _prune(self, job: CrawlJob, host: str, seen: set[str]) -> int:
        keep = {document_id(u) for u in seen if u not in job.gone}  # a page that merely failed to load this time is kept; only 404/410 removes it
        n = 0
        for doc, _ in await self.store.documents(job.source_id, limit=10000):
            if doc.external_id.startswith(f"web:{host}/") and doc.external_id not in keep:
                if await self.store.delete(job.source_id, doc.external_id):
                    n += 1
        return n


def _parse_date(value: str | None) -> float | None:
    if not value:
        return None
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        return None
