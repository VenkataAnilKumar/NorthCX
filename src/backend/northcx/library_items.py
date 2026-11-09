"""Library items for staff (E6, 6.1): prompts, macros, playbooks and canned answers people keep and reuse.

A macro or canned answer is reply text for a common situation; the Inbox suggests the ones that fit a conversation. A playbook is steps to follow, a prompt
is something to ask the Pilot. Each has an owner, is private or shared with everyone who uses the Workspace, keeps its last 20 versions, and counts how often it is used.
Text is masked for customer personal data before it is stored, because a reusable answer must never carry one customer's details to the next.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .outputs import MAX_VERSIONS, clean
from .tenancy import current_tenant

KINDS = ("prompt", "macro", "playbook", "canned")
VISIBILITY = ("private", "shared")
MAX_BODY = 20_000
MAX_ITEMS = 1000
WORD = re.compile(r"[a-z0-9]{3,}")
STOP = frozenset("the and for you your with that this have from are was but not can will our out has get how why what when where who please thanks thank hello dear hi".split())


class LibraryError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Item:
    owner: str
    title: str
    kind: str
    visibility: str
    versions: list[dict[str, Any]]
    tags: list[str] = field(default_factory=list)
    uses: int = 0
    id: str = field(default_factory=lambda: "lib-" + uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def visible_to(self, who: str, admin: bool) -> bool:
        return self.owner == who or self.visibility == "shared" or admin

    def to_dict(self, full: bool = False) -> dict[str, Any]:
        cur = self.versions[-1]
        out = {"id": self.id, "title": self.title, "kind": self.kind, "visibility": self.visibility, "owner": self.owner, "tags": self.tags, "uses": self.uses,
               "version": cur["n"], "createdAt": self.created_at, "updatedAt": self.updated_at, "preview": cur["body"][:160]}
        if full:
            out.update({"body": cur["body"], "history": [{"n": v["n"], "at": v["at"], "by": v["by"]} for v in self.versions]})
        return out


class LibraryRepo(Protocol):
    async def put(self, i: Item) -> None: ...
    async def get(self, item_id: str) -> Item | None: ...
    async def list(self) -> list[Item]: ...
    async def delete(self, item_id: str) -> bool: ...
    async def bump(self, item_id: str) -> int: ...          # one more use; returns the new count


class InMemoryLibrary:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Item] = {}

    async def put(self, i: Item) -> None:
        i.updated_at = time.time()
        self._items[(current_tenant(), i.id)] = i

    async def get(self, item_id: str) -> Item | None:
        return self._items.get((current_tenant(), item_id))

    async def list(self) -> list[Item]:
        t = current_tenant()
        return sorted((i for (tt, _), i in self._items.items() if tt == t), key=lambda i: i.title.lower())

    async def delete(self, item_id: str) -> bool:
        return self._items.pop((current_tenant(), item_id), None) is not None

    async def bump(self, item_id: str) -> int:
        i = self._items.get((current_tenant(), item_id))
        if i is None:
            return 0
        i.uses += 1
        return i.uses


def words(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOP}


def score(query: set[str], item: Item) -> float:
    """How well an item fits some text: shared words, title and tags counting more than the body. 0 means it does not fit."""
    if not query:
        return 0.0
    body = words(item.versions[-1]["body"])
    head = words(item.title) | {t for tag in item.tags for t in words(tag)}
    return (3 * len(query & head) + len(query & body)) / (len(query) ** 0.5)


def _tags(tags: list[str] | None) -> list[str]:
    out = []
    for t in tags or []:
        t = t.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9 _-]{0,29}", t):
            raise LibraryError(400, "A tag is up to 30 lowercase letters, digits, spaces, - or _")
        if t not in out:
            out.append(t)
    if len(out) > 8:
        raise LibraryError(400, "At most 8 tags")
    return out


class LibraryService:
    def __init__(self, repo: LibraryRepo | None = None):
        self.repo = repo or InMemoryLibrary()

    @staticmethod
    def _body(body: str) -> str:
        if not isinstance(body, str) or not body.strip():
            raise LibraryError(400, "The text cannot be empty")
        if len(body) > MAX_BODY:
            raise LibraryError(400, f"The text is too long (at most {MAX_BODY:,} characters)")
        return clean(body)

    @staticmethod
    def _title(title: str) -> str:
        if not isinstance(title, str) or not 2 <= len(title.strip()) <= 120:
            raise LibraryError(400, "The title must be 2 to 120 characters")
        return clean(title.strip())

    async def create(self, owner: str, title: str, body: str, kind: str, visibility: str = "private", tags: list[str] | None = None) -> Item:
        if kind not in KINDS or visibility not in VISIBILITY:
            raise LibraryError(400, f"kind must be one of {', '.join(KINDS)} and visibility private or shared")
        if len(await self.repo.list()) >= MAX_ITEMS:
            raise LibraryError(429, "The library is full; delete some items first")
        now = time.time()
        i = Item(owner, self._title(title), kind, visibility, [{"n": 1, "body": self._body(body), "at": now, "by": owner}], _tags(tags), created_at=now)
        await self.repo.put(i)
        return i

    async def get(self, item_id: str, who: str, admin: bool) -> Item:
        i = await self.repo.get(item_id)
        if i is None or not i.visible_to(who, admin):
            raise LibraryError(404, "Unknown item")                      # someone else's private item looks the same as a missing one
        return i

    async def edit(self, item_id: str, who: str, admin: bool, title: str | None = None, body: str | None = None, visibility: str | None = None, tags: list[str] | None = None) -> Item:
        i = await self.get(item_id, who, admin)
        if i.owner != who and not admin:
            raise LibraryError(403, "Only the owner can change an item")
        if title is not None:
            i.title = self._title(title)
        if visibility is not None:
            if visibility not in VISIBILITY:
                raise LibraryError(400, "visibility must be private or shared")
            i.visibility = visibility
        if tags is not None:
            i.tags = _tags(tags)
        if body is not None:
            text = self._body(body)
            if text != i.versions[-1]["body"]:
                i.versions = [*i.versions, {"n": i.versions[-1]["n"] + 1, "body": text, "at": time.time(), "by": who}][-MAX_VERSIONS:]
        await self.repo.put(i)
        return i

    async def delete(self, item_id: str, who: str, admin: bool) -> None:
        i = await self.get(item_id, who, admin)
        if i.owner != who and not admin:
            raise LibraryError(403, "Only the owner can delete an item")
        await self.repo.delete(item_id)

    async def list(self, who: str, admin: bool, kind: str | None = None, q: str | None = None, mine: bool = False) -> list[Item]:
        rows = [i for i in await self.repo.list() if i.visible_to(who, admin) and (kind is None or i.kind == kind) and (not mine or i.owner == who)]
        if q and q.strip():
            qw = words(q)
            ranked = [(score(qw, i), i) for i in rows]
            rows = [i for s, i in sorted(ranked, key=lambda x: -x[0]) if s > 0]
        return rows

    async def suggest(self, who: str, admin: bool, text: str, limit: int = 5) -> list[Item]:
        """Macros and canned answers that fit some text (the customer's message), best first, shared ones and the person's own."""
        qw = words(text)
        ranked = [(score(qw, i), i) for i in await self.repo.list() if i.kind in ("macro", "canned") and i.visible_to(who, False)]
        return [i for s, i in sorted(ranked, key=lambda x: (-x[0], -x[1].uses)) if s > 0][:limit]

    async def use(self, item_id: str, who: str, admin: bool) -> tuple[Item, int]:
        i = await self.get(item_id, who, admin)
        return i, await self.repo.bump(item_id)
