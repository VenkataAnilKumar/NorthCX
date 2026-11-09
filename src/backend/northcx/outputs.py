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
from .decision_teams import NO_TEAM, current_team, team_visible
from .tenancy import current_tenant

_MASK = PIIDetection()
KINDS = ("note", "answer", "report", "table", "digest")
VISIBILITY = ("private", "team", "shared")
MAX_BODY = 100_000
MAX_VERSIONS = 20
DEFAULT_DAYS, MAX_DAYS = 90, 365
MAX_PER_OWNER = 500
FILE_EXT = (".txt", ".md", ".csv", ".json", ".log", ".pdf")
MAX_PDF_BYTES = 5 * 1024 * 1024    # a PDF is read for its text and only the text is kept
MAX_FILE = 200_000                  # characters in one file
MAX_FILES = 10                      # per space
FILE_CONTEXT = 12_000               # most characters of files the Pilot reads in one question


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
    team: str = ""          # the owner's team when it was shared with a team

    def visible_to(self, who: str, admin: bool) -> bool:
        return team_visible(self.owner, self.team, self.visibility, who, admin)

    def to_dict(self, full: bool = False) -> dict[str, Any]:
        cur = self.versions[-1]
        out = {"id": self.id, "title": self.title, "kind": self.kind, "visibility": self.visibility, "owner": self.owner, "spaceId": self.space_id, "source": self.source,
               "team": self.team or None, "version": cur["n"], "versions": len(self.versions), "createdAt": self.created_at, "updatedAt": self.updated_at, "expiresAt": self.expires_at, "size": len(cur["body"])}
        if full:
            out.update({"body": cur["body"], "history": [{"n": v["n"], "at": v["at"], "by": v["by"], "size": len(v["body"])} for v in self.versions]})
        return out


@dataclass
class SpaceFile:
    space_id: str
    name: str
    text: str
    owner: str
    id: str = field(default_factory=lambda: "fil-" + uuid.uuid4().hex[:10])
    created_at: float = field(default_factory=time.time)

    def to_dict(self, full: bool = False) -> dict[str, Any]:
        out = {"id": self.id, "spaceId": self.space_id, "name": self.name, "size": len(self.text), "owner": self.owner, "createdAt": self.created_at}
        if full:
            out["text"] = self.text
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
    team: str = ""

    def visible_to(self, who: str, admin: bool) -> bool:
        return team_visible(self.owner, self.team, self.visibility, who, admin)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "description": self.description, "instructions": self.instructions, "visibility": self.visibility, "team": self.team or None, "owner": self.owner,
                "createdAt": self.created_at, "updatedAt": self.updated_at}


class ContentRepo(Protocol):
    async def put_output(self, o: Output) -> None: ...
    async def get_output(self, output_id: str) -> Output | None: ...
    async def list_outputs(self, space_id: str | None, kind: str | None, now: float) -> list[Output]: ...
    async def delete_output(self, output_id: str) -> bool: ...
    async def purge_expired(self, now: float) -> int: ...
    async def count_outputs(self, owner: str | None) -> int: ...      # None: every output in this tenant
    async def put_space(self, s: Space) -> None: ...
    async def get_space(self, space_id: str) -> Space | None: ...
    async def list_spaces(self) -> list[Space]: ...
    async def delete_space(self, space_id: str) -> bool: ...
    async def put_file(self, f: SpaceFile) -> None: ...
    async def list_files(self, space_id: str) -> list[SpaceFile]: ...
    async def get_file(self, space_id: str, file_id: str) -> SpaceFile | None: ...
    async def delete_file(self, space_id: str, file_id: str) -> bool: ...


class InMemoryContent:
    def __init__(self) -> None:
        self._o: dict[tuple[str, str], Output] = {}
        self._s: dict[tuple[str, str], Space] = {}
        self._f: dict[tuple[str, str], SpaceFile] = {}

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

    async def count_outputs(self, owner: str | None) -> int:
        t = current_tenant()
        return sum(1 for (tt, _), o in self._o.items() if tt == t and (owner is None or o.owner == owner))

    async def put_space(self, s: Space) -> None:
        s.updated_at = time.time()
        self._s[(current_tenant(), s.id)] = s

    async def get_space(self, space_id: str) -> Space | None:
        return self._s.get((current_tenant(), space_id))

    async def list_spaces(self) -> list[Space]:
        t = current_tenant()
        return sorted((s for (tt, _), s in self._s.items() if tt == t), key=lambda s: s.name.lower())

    async def put_file(self, f: SpaceFile) -> None:
        self._f[(current_tenant(), f.id)] = f

    async def list_files(self, space_id: str) -> list[SpaceFile]:
        t = current_tenant()
        return sorted((f for (tt, _), f in self._f.items() if tt == t and f.space_id == space_id), key=lambda f: f.created_at)

    async def get_file(self, space_id: str, file_id: str) -> SpaceFile | None:
        f = self._f.get((current_tenant(), file_id))
        return f if f is not None and f.space_id == space_id else None

    async def delete_file(self, space_id: str, file_id: str) -> bool:
        f = await self.get_file(space_id, file_id)
        return f is not None and self._f.pop((current_tenant(), file_id), None) is not None

    async def delete_space(self, space_id: str) -> bool:
        t = current_tenant()
        for k in [k for k, f in self._f.items() if k[0] == t and f.space_id == space_id]:
            del self._f[k]                                   # a space's files go with it
        for k in [k for k, o in self._o.items() if k[0] == t and o.space_id == space_id]:
            self._o[k].space_id = None                       # outputs outlive their space
        return self._s.pop((t, space_id), None) is not None


def _team_for(visibility: str) -> str:
    """The team to remember when something is shared with a team. Someone in no team cannot share with one, because no one else would see it."""
    if visibility != "team":
        return ""
    team = current_team()
    if team == NO_TEAM:
        raise ContentError(400, "You are not in a team, so you cannot share with a team; share with everyone or keep it private")
    return team


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
        self.total_cap: Any = None                 # async () -> int | None: the most outputs this tenant may hold (set by the server from the tenant's limits)

    # ---- outputs ----
    async def create_output(self, owner: str, title: str, body: str, kind: str = "note", visibility: str = "private", space_id: str | None = None,
                            source: str = "manual", days: int = DEFAULT_DAYS, admin: bool = False) -> Output:
        if kind not in KINDS or visibility not in VISIBILITY:
            raise ContentError(400, f"kind must be one of {', '.join(KINDS)} and visibility private, team or shared")
        if not isinstance(title, str) or not 2 <= len(title.strip()) <= 120:
            raise ContentError(400, "The title must be 2 to 120 characters")
        if not 1 <= days <= MAX_DAYS:
            raise ContentError(400, f"days must be between 1 and {MAX_DAYS}")
        text = _check_text(body)
        if kind == "table":
            _check_table(text)
        if space_id is not None:
            await self._space_for(space_id, owner, admin)
        cap = await self.total_cap() if self.total_cap is not None else None
        if cap and await self.repo.count_outputs(None) >= cap:
            raise ContentError(429, "This organization has reached the number of saved outputs its plan allows; delete some first")
        if await self.repo.count_outputs(owner) >= MAX_PER_OWNER:
            raise ContentError(429, f"You have {MAX_PER_OWNER} saved outputs; delete some first")
        now = time.time()
        o = Output(owner, clean(title.strip()), kind, visibility, [{"n": 1, "body": text, "at": now, "by": owner}], space_id, source, created_at=now, expires_at=now + days * 86400, team=_team_for(visibility))
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
                raise ContentError(400, "visibility must be private, team or shared")
            o.team = _team_for(visibility)
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
            raise ContentError(400, "The name must be 2 to 80 characters and visibility private, team or shared")
        if len(description) > 500 or len(instructions) > 2000:
            raise ContentError(400, "The description is at most 500 characters and the instructions at most 2,000")
        if len(await self.repo.list_spaces()) >= 500:
            raise ContentError(429, "There are too many spaces; delete some first")
        s = Space(owner, name.strip(), visibility, clean(description.strip()), clean(instructions.strip()), team=_team_for(visibility))
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
                raise ContentError(400, "visibility must be private, team or shared")
            s.team = _team_for(v)
            s.visibility = v
        await self.repo.put_space(s)
        return s

    async def delete_space(self, space_id: str, who: str, admin: bool) -> None:
        s = await self._space_for(space_id, who, admin)
        if s.owner != who and not admin:
            raise ContentError(403, "Only the owner can delete a space")
        await self.repo.delete_space(space_id)

    # ---- files in a space: plain text the Pilot may read when working there ----
    async def add_file(self, space_id: str, who: str, admin: bool, name: str, text: str | None = None, pdf: bytes | None = None) -> SpaceFile:
        s = await self._space_for(space_id, who, admin)
        if s.owner != who and not admin:
            raise ContentError(403, "Only the owner can add files to a space")
        base = (name or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
        if not 1 <= len(base) <= 100 or not base.lower().endswith(FILE_EXT):
            raise ContentError(400, f"Files are plain text or PDF: the name must end in {', '.join(FILE_EXT)}")
        if base.lower().endswith(".pdf"):
            if not pdf or len(pdf) > MAX_PDF_BYTES:
                raise ContentError(400, f"Send the PDF itself, up to {MAX_PDF_BYTES // (1024 * 1024)} MB")
            from .ingest import IngestError, from_pdf
            try:
                text = (await from_pdf(pdf, base)).text
            except IngestError as e:
                raise ContentError(400, f"That PDF has no text that can be read ({e}); scans are not supported") from e
        if not isinstance(text, str) or not text.strip() or "\x00" in text:
            raise ContentError(400, "The file must be text, and not empty")
        if len(text) > MAX_FILE:
            raise ContentError(400, f"The file is too large (at most {MAX_FILE:,} characters)")
        existing = await self.repo.list_files(space_id)
        if len(existing) >= MAX_FILES:
            raise ContentError(429, f"A space holds at most {MAX_FILES} files; remove one first")
        if any(f.name.lower() == base.lower() for f in existing):
            raise ContentError(409, "A file with that name is already in the space")
        f = SpaceFile(space_id, clean(base), clean(text), who)
        await self.repo.put_file(f)
        return f

    async def list_files(self, space_id: str, who: str, admin: bool) -> list[SpaceFile]:
        await self._space_for(space_id, who, admin)
        return await self.repo.list_files(space_id)

    async def get_file(self, space_id: str, file_id: str, who: str, admin: bool) -> SpaceFile:
        await self._space_for(space_id, who, admin)
        f = await self.repo.get_file(space_id, file_id)
        if f is None:
            raise ContentError(404, "Unknown file")
        return f

    async def delete_file(self, space_id: str, file_id: str, who: str, admin: bool) -> None:
        s = await self._space_for(space_id, who, admin)
        if s.owner != who and not admin:
            raise ContentError(403, "Only the owner can remove files from a space")
        if not await self.repo.delete_file(space_id, file_id):
            raise ContentError(404, "Unknown file")

    async def file_context(self, space_id: str, who: str, admin: bool) -> str:
        """The space's files as one block for the Pilot, cut to a fixed size. They are data to read, never instructions."""
        files = await self.list_files(space_id, who, admin)
        parts, left = [], FILE_CONTEXT
        for f in files:
            if left <= 0:
                break
            chunk = f.text[:left]
            parts.append(f"--- file: {f.name}{' (cut short)' if len(chunk) < len(f.text) else ''} ---\n{chunk}")
            left -= len(chunk)
        return "\n".join(parts)

    async def list_spaces(self, who: str, admin: bool) -> list[Space]:
        return [s for s in await self.repo.list_spaces() if s.visible_to(who, admin)]
