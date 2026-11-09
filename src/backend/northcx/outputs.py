"""Outputs and Spaces for the Workspace (E6).

An output is a result someone kept: an answer, a report, a table, a note. Each edit adds a version. Customer personal data is masked before
anything is stored, outputs expire (90 days unless set otherwise), and an export is audited. A space is one piece of work: instructions the
assistant follows in it, and the outputs that belong to it. Both are private to their owner unless shared with everyone who uses the Workspace.
"""
from __future__ import annotations

import csv
import html
import io
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .safety.pii import PIIDetection
from .tenancy import current_tenant

_MASK = PIIDetection()
KINDS = ("note", "answer", "report", "table", "digest")
VISIBILITY = ("private", "shared")
MAX_BODY = 100_000
MAX_VERSIONS = 20
DEFAULT_DAYS, MAX_DAYS = 90, 365
MAX_PER_OWNER = 500


class ContentError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def clean(text: str) -> str:
    return _MASK.mask(text)[0]


@dataclass
class Output:
    owner: str
    title: str
    kind: str
    visibility: str
    versions: list[dict[str, Any]]            # newest last: {n, body, at, by}
    space_id: str | None = None
    source: str = "manual"                     # manual, pilot, automation:<id>
    id: str = field(default_factory=lambda: "out-" + uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def visible_to(self, who: str, admin: bool) -> bool:
        return self.owner == who or self.visibility == "shared" or admin

    def to_dict(self, full: bool = False) -> dict[str, Any]:
        cur = self.versions[-1]
        out = {"id": self.id, "title": self.title, "kind": self.kind, "visibility": self.visibility, "owner": self.owner, "spaceId": self.space_id, "source": self.source,
               "version": cur["n"], "versions": len(self.versions), "createdAt": self.created_at, "updatedAt": self.updated_at, "expiresAt": self.expires_at, "size": len(cur["body"])}
        if full:
            out.update({"body": cur["body"], "history": [{"n": v["n"], "at": v["at"], "by": v["by"], "size": len(v["body"])} for v in self.versions]})
        return out


@dataclass
class Space:
    owner: str
    name: str
    visibility: str
    description: str = ""
    instructions: str = ""
    id: str = field(default_factory=lambda: "spc-" + uuid.uuid4().hex[:10])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def visible_to(self, who: str, admin: bool) -> bool:
        return self.owner == who or self.visibility == "shared" or admin

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "description": self.description, "instructions": self.instructions, "visibility": self.visibility, "owner": self.owner,
                "createdAt": self.created_at, "updatedAt": self.updated_at}


class ContentRepo(Protocol):
    async def put_output(self, o: Output) -> None: ...
    async def get_output(self, output_id: str) -> Output | None: ...
    async def list_outputs(self, space_id: str | None, kind: str | None, now: float) -> list[Output]: ...
    async def delete_output(self, output_id: str) -> bool: ...
    async def purge_expired(self, now: float) -> int: ...
    async def count_outputs(self, owner: str) -> int: ...
    async def put_space(self, s: Space) -> None: ...
    async def get_space(self, space_id: str) -> Space | None: ...
    async def list_spaces(self) -> list[Space]: ...
    async def delete_space(self, space_id: str) -> bool: ...


class InMemoryContent:
    def __init__(self) -> None:
        self._o: dict[tuple[str, str], Output] = {}
        self._s: dict[tuple[str, str], Space] = {}

    async def put_output(self, o: Output) -> None:
        o.updated_at = time.time()
        self._o[(current_tenant(), o.id)] = o

    async def get_output(self, output_id: str) -> Output | None:
        return self._o.get((current_tenant(), output_id))

    async def list_outputs(self, space_id: str | None, kind: str | None, now: float) -> list[Output]:
        t = current_tenant()
        rows = [o for (tt, _), o in self._o.items() if tt == t and o.expires_at > now and (space_id is None or o.space_id == space_id) and (kind is None or o.kind == kind)]
        return sorted(rows, key=lambda o: -o.updated_at)

    async def delete_output(self, output_id: str) -> bool:
        return self._o.pop((current_tenant(), output_id), None) is not None

    async def purge_expired(self, now: float) -> int:
        t = current_tenant()
        gone = [k for k, o in self._o.items() if k[0] == t and o.expires_at <= now]
        for k in gone:
            del self._o[k]
        return len(gone)

    async def count_outputs(self, owner: str) -> int:
        t = current_tenant()
        return sum(1 for (tt, _), o in self._o.items() if tt == t and o.owner == owner)

    async def put_space(self, s: Space) -> None:
        s.updated_at = time.time()
        self._s[(current_tenant(), s.id)] = s

    async def get_space(self, space_id: str) -> Space | None:
        return self._s.get((current_tenant(), space_id))

    async def list_spaces(self) -> list[Space]:
        t = current_tenant()
        return sorted((s for (tt, _), s in self._s.items() if tt == t), key=lambda s: s.name.lower())

    async def delete_space(self, space_id: str) -> bool:
        t = current_tenant()
        for k in [k for k, o in self._o.items() if k[0] == t and o.space_id == space_id]:
            self._o[k].space_id = None                       # outputs outlive their space
        return self._s.pop((t, space_id), None) is not None


def _check_text(body: str) -> str:
    if not isinstance(body, str) or not body.strip():
        raise ContentError(400, "The content cannot be empty")
    if len(body) > MAX_BODY:
        raise ContentError(400, f"The content is too large (at most {MAX_BODY:,} characters)")
    return clean(body)


def _check_table(body: str) -> None:
    try:
        rows = list(csv.reader(io.StringIO(body)))
    except csv.Error as e:
        raise ContentError(400, f"A table must be valid CSV: {e}") from e
    if len(rows) < 1 or len({len(r) for r in rows}) != 1:
        raise ContentError(400, "A table must be CSV with the same number of columns in every row")


class ContentService:
    def __init__(self, repo: ContentRepo | None = None):
        self.repo = repo or InMemoryContent()

    # ---- outputs ----
    async def create_output(self, owner: str, title: str, body: str, kind: str = "note", visibility: str = "private", space_id: str | None = None,
                            source: str = "manual", days: int = DEFAULT_DAYS, admin: bool = False) -> Output:
        if kind not in KINDS or visibility not in VISIBILITY:
            raise ContentError(400, f"kind must be one of {', '.join(KINDS)} and visibility private or shared")
        if not isinstance(title, str) or not 2 <= len(title.strip()) <= 120:
            raise ContentError(400, "The title must be 2 to 120 characters")
        if not 1 <= days <= MAX_DAYS:
            raise ContentError(400, f"days must be between 1 and {MAX_DAYS}")
        text = _check_text(body)
        if kind == "table":
            _check_table(text)
        if space_id is not None:
            await self._space_for(space_id, owner, admin)
        if await self.repo.count_outputs(owner) >= MAX_PER_OWNER:
            raise ContentError(429, f"You have {MAX_PER_OWNER} saved outputs; delete some first")
        now = time.time()
        o = Output(owner, clean(title.strip()), kind, visibility, [{"n": 1, "body": text, "at": now, "by": owner}], space_id, source, created_at=now, expires_at=now + days * 86400)
        await self.repo.put_output(o)
        return o

    async def get_output(self, output_id: str, who: str, admin: bool) -> Output:
        o = await self.repo.get_output(output_id)
        if o is None or o.expires_at <= time.time() or not o.visible_to(who, admin):
            raise ContentError(404, "Unknown output")                     # a private output of someone else looks the same as a missing one
        return o

    async def edit_output(self, output_id: str, who: str, admin: bool, body: str | None = None, title: str | None = None, visibility: str | None = None) -> Output:
        o = await self.get_output(output_id, who, admin)
        if o.owner != who and not admin:
            raise ContentError(403, "Only the owner can change an output")
        if visibility is not None:
            if visibility not in VISIBILITY:
                raise ContentError(400, "visibility must be private or shared")
            o.visibility = visibility
        if title is not None:
            if not 2 <= len(title.strip()) <= 120:
                raise ContentError(400, "The title must be 2 to 120 characters")
            o.title = clean(title.strip())
        if body is not None:
            text = _check_text(body)
            if o.kind == "table":
                _check_table(text)
            if text != o.versions[-1]["body"]:
                o.versions.append({"n": o.versions[-1]["n"] + 1, "body": text, "at": time.time(), "by": who})
                o.versions = o.versions[-MAX_VERSIONS:]
        await self.repo.put_output(o)
        return o

    async def delete_output(self, output_id: str, who: str, admin: bool) -> None:
        o = await self.get_output(output_id, who, admin)
        if o.owner != who and not admin:
            raise ContentError(403, "Only the owner can delete an output")
        await self.repo.delete_output(output_id)

    async def list_outputs(self, who: str, admin: bool, space_id: str | None = None, kind: str | None = None, mine: bool = False) -> list[Output]:
        now = time.time()
        await self.repo.purge_expired(now)
        return [o for o in await self.repo.list_outputs(space_id, kind, now) if o.visible_to(who, admin) and (not mine or o.owner == who)]

    @staticmethod
    def export(o: Output, fmt: str, version: int | None = None) -> tuple[str, str, str]:
        """(content, media type, file extension) of one version. Markdown and text are the content as kept; HTML is escaped; CSV only for tables."""
        v = next((x for x in o.versions if version is None or x["n"] == version), None)
        if v is None:
            raise ContentError(404, "Unknown version")
        body = clean(v["body"])                                           # masked again on the way out
        if fmt == "md":
            return body, "text/markdown; charset=utf-8", "md"
        if fmt == "txt":
            return body, "text/plain; charset=utf-8", "txt"
        if fmt == "html":
            return f"<!doctype html><meta charset=\"utf-8\"><title>{html.escape(o.title)}</title><h1>{html.escape(o.title)}</h1><pre style=\"white-space:pre-wrap\">{html.escape(body)}</pre>", "text/html; charset=utf-8", "html"
        if fmt == "csv" and o.kind == "table":
            return body, "text/csv; charset=utf-8", "csv"
        raise ContentError(400, "format must be md, txt or html (csv for tables)")

    # ---- spaces ----
    async def _space_for(self, space_id: str, who: str, admin: bool) -> Space:
        s = await self.repo.get_space(space_id)
        if s is None or not s.visible_to(who, admin):
            raise ContentError(404, "Unknown space")
        return s

    async def get_space(self, space_id: str, who: str, admin: bool) -> Space:
        return await self._space_for(space_id, who, admin)

    async def create_space(self, owner: str, name: str, description: str = "", instructions: str = "", visibility: str = "private") -> Space:
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 80 or visibility not in VISIBILITY:
            raise ContentError(400, "The name must be 2 to 80 characters and visibility private or shared")
        if len(description) > 500 or len(instructions) > 2000:
            raise ContentError(400, "The description is at most 500 characters and the instructions at most 2,000")
        if len(await self.repo.list_spaces()) >= 500:
            raise ContentError(429, "There are too many spaces; delete some first")
        s = Space(owner, name.strip(), visibility, clean(description.strip()), clean(instructions.strip()))
        await self.repo.put_space(s)
        return s

    async def edit_space(self, space_id: str, who: str, admin: bool, **fields: Any) -> Space:
        s = await self._space_for(space_id, who, admin)
        if s.owner != who and not admin:
            raise ContentError(403, "Only the owner can change a space")
        if (n := fields.get("name")) is not None:
            if not 2 <= len(n.strip()) <= 80:
                raise ContentError(400, "The name must be 2 to 80 characters")
            s.name = n.strip()
        if (d := fields.get("description")) is not None:
            if len(d) > 500:
                raise ContentError(400, "The description is at most 500 characters")
            s.description = clean(d.strip())
        if (i := fields.get("instructions")) is not None:
            if len(i) > 2000:
                raise ContentError(400, "The instructions are at most 2,000 characters")
            s.instructions = clean(i.strip())
        if (v := fields.get("visibility")) is not None:
            if v not in VISIBILITY:
                raise ContentError(400, "visibility must be private or shared")
            s.visibility = v
        await self.repo.put_space(s)
        return s

    async def delete_space(self, space_id: str, who: str, admin: bool) -> None:
        s = await self._space_for(space_id, who, admin)
        if s.owner != who and not admin:
            raise ContentError(403, "Only the owner can delete a space")
        await self.repo.delete_space(space_id)

    async def list_spaces(self, who: str, admin: bool) -> list[Space]:
        return [s for s in await self.repo.list_spaces() if s.visible_to(who, admin)]
