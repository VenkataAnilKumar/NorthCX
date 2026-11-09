"""Organization templates (WP22.5): an organization's own Hub entries, written here, checked, and published only after a second person approves.

A template here is the same document as a built-in one. It is parsed, rendered with example values, and must carry at least one scenario
before it can be proposed. Published templates appear in the Hub for this organization only, marked with who proposed and who approved them.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import yaml

from .template_signing import content_hash
from .templates import Template, TemplateError, parse_template, render

STATUSES = ("draft", "proposed", "published", "rejected", "superseded", "withdrawn")
CACHE_SECONDS = 5.0
MAX_BYTES = 60_000


class OrgTemplateError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class OrgTemplate:
    id: str
    version: int
    title: str
    data: dict[str, Any]
    status: str = "draft"
    check: dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    proposed_by: str | None = None
    decided_by: str | None = None
    decision_note: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, full: bool = False) -> dict[str, Any]:
        out = {"id": self.id, "version": self.version, "title": self.title, "status": self.status, "check": self.check, "createdBy": self.created_by,
               "proposedBy": self.proposed_by, "decidedBy": self.decided_by, "decisionNote": self.decision_note, "createdAt": self.created_at, "updatedAt": self.updated_at,
               "contentHash": content_hash(self.data), "scenarios": len(self.data.get("scenarios") or []), "audience": self.data.get("audience", "customer")}
        if full:
            out["data"] = self.data
            out["yaml"] = yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True, width=100)
        return out


class OrgTemplateRepo(Protocol):
    async def save(self, t: OrgTemplate) -> None: ...
    async def get(self, template_id: str, version: int | None = None) -> OrgTemplate | None: ...
    async def versions(self, template_id: str) -> list[OrgTemplate]: ...
    async def list(self) -> list[OrgTemplate]: ...
    async def published(self) -> list[OrgTemplate]: ...


class InMemoryOrgTemplates:
    def __init__(self) -> None:
        self._items: dict[tuple[str, int], OrgTemplate] = {}

    async def save(self, t: OrgTemplate) -> None:
        t.updated_at = time.time()
        self._items[(t.id, t.version)] = t

    async def versions(self, template_id: str) -> list[OrgTemplate]:
        return sorted((t for (i, _), t in self._items.items() if i == template_id), key=lambda t: -t.version)

    async def get(self, template_id: str, version: int | None = None) -> OrgTemplate | None:
        return next((t for t in await self.versions(template_id) if version is None or t.version == version), None)

    async def list(self) -> list[OrgTemplate]:
        return sorted([(await self.versions(i))[0] for i in {i for i, _ in self._items}], key=lambda t: t.title.lower())

    async def published(self) -> list[OrgTemplate]:
        return [t for t in self._items.values() if t.status == "published"]


def check_template(data: Any, reserved: set[str]) -> tuple[Template, dict[str, Any]]:
    """Parse and render a template document with example values. Raises OrgTemplateError(400) when it is not usable."""
    if not isinstance(data, dict):
        raise OrgTemplateError(400, "A template is a mapping")
    if len(repr(data)) > MAX_BYTES:
        raise OrgTemplateError(400, "That template is too large")
    try:
        t = parse_template(data, "organization template")
        if t.id in reserved:
            raise OrgTemplateError(400, f"'{t.id}' is the id of a built-in template; pick another id")
        sample = {p.name: (p.default if p.default is not None else "example") for p in t.params}
        r = render(t, "check-agent", sample)
    except TemplateError as e:
        raise OrgTemplateError(400, str(e)) from e
    problems = [] if r.scenarios else ["Add at least one scenario: every Hub entry ships with the tests that prove it"]
    return t, {"ok": not problems, "problems": problems, "scenarios": len(r.scenarios), "checkedAt": time.time()}


class OrgTemplateService:
    def __init__(self, repo: OrgTemplateRepo | None = None, reserved: set[str] | None = None):
        self.repo = repo or InMemoryOrgTemplates()
        self.reserved = reserved or set()
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, dict[str, Template]]] = {}

    def _invalidate(self) -> None:
        self._cache.clear()

    async def create(self, data: dict[str, Any], by: str) -> OrgTemplate:
        t, check = check_template(data, self.reserved)
        if await self.repo.get(t.id) is not None:
            raise OrgTemplateError(409, f"A template '{t.id}' already exists; change it to make a new version")
        o = OrgTemplate(t.id, 1, t.title, data, check=check, created_by=by)
        await self.repo.save(o)
        return o

    async def revise(self, template_id: str, data: dict[str, Any], by: str) -> OrgTemplate:
        """Edit the open draft in place, or start a new version when the latest one is decided. A published version stays published until the new one is approved."""
        cur = await self.repo.get(template_id)
        if cur is None:
            raise OrgTemplateError(404, "Unknown template")
        t, check = check_template(data, self.reserved)
        if t.id != template_id:
            raise OrgTemplateError(400, "The id cannot change; create a new template instead")
        if cur.status == "proposed":
            raise OrgTemplateError(409, "It is waiting for review; reject it first to change it")
        if cur.status == "draft":
            cur.title, cur.data, cur.check = t.title, data, check
            await self.repo.save(cur)
            return cur
        n = OrgTemplate(template_id, cur.version + 1, t.title, data, check=check, created_by=by)
        await self.repo.save(n)
        return n

    async def propose(self, template_id: str, by: str) -> OrgTemplate:
        o = await self.repo.get(template_id)
        if o is None:
            raise OrgTemplateError(404, "Unknown template")
        if o.status != "draft":
            raise OrgTemplateError(409, f"Only a draft can be proposed; this version is {o.status}")
        _, o.check = check_template(o.data, self.reserved)
        if not o.check["ok"]:
            raise OrgTemplateError(409, "It cannot be proposed yet: " + "; ".join(o.check["problems"]))
        o.status, o.proposed_by = "proposed", by
        await self.repo.save(o)
        return o

    async def decide(self, template_id: str, approve: bool, by: str, note: str | None) -> OrgTemplate:
        async with self._lock:
            o = await self.repo.get(template_id)
            if o is None:
                raise OrgTemplateError(404, "Unknown template")
            if o.status != "proposed":
                raise OrgTemplateError(409, f"This version is {o.status}; only a proposed one can be decided")
            if approve and by == o.proposed_by:
                raise OrgTemplateError(403, "A template needs a second person: the person who proposed it cannot approve it")
            if approve:
                _, o.check = check_template(o.data, self.reserved)
                if not o.check["ok"]:
                    raise OrgTemplateError(409, "It no longer passes its checks: " + "; ".join(o.check["problems"]))
                for old in await self.repo.versions(template_id):
                    if old.status == "published":
                        old.status = "superseded"
                        await self.repo.save(old)
            o.status, o.decided_by, o.decision_note = ("published" if approve else "rejected"), by, note
            await self.repo.save(o)
            self._invalidate()
            return o

    async def withdraw(self, template_id: str, by: str, note: str | None) -> OrgTemplate:
        o = next((v for v in await self.repo.versions(template_id) if v.status == "published"), None)
        if o is None:
            raise OrgTemplateError(404, "That template is not published")
        o.status, o.decided_by, o.decision_note = "withdrawn", by, note or "withdrawn"
        await self.repo.save(o)
        self._invalidate()
        return o

    async def published(self) -> dict[str, Template]:
        """The templates this organization has approved, as Hub entries. Cached for a few seconds per tenant."""
        from .tenancy import current_tenant
        key = current_tenant()
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        out: dict[str, Template] = {}
        for o in await self.repo.published():
            try:
                t = parse_template(o.data, "organization template")
            except TemplateError:
                continue
            t.version = str(o.version)
            t.provenance = {"source": "organization", "signed": False, "verified": False, "status": f"approved by {o.decided_by}", "proposedBy": o.proposed_by,
                            "approvedBy": o.decided_by, "contentHash": t.content_hash, "orgVersion": o.version}
            out[t.id] = t
        self._cache[key] = (time.time(), out)
        return out
