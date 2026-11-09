"""Customers: one view of a person across every channel, kept narrow because it carries the most privacy risk (decision 158).

Found only by the identifier the company already uses for the customer (never by browsing or free text). Personal data is masked; showing
the identifier needs a written reason that is logged. Everything shown says where it came from. Staff notes are the only thing stored here;
the rest is read from conversations, memories and ratings, and goes when the customer is erased.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .budget_settings import InMemorySettings, SettingsRepo
from .insights import mask
from .privacy import customer_ref
from .tenancy import current_tenant

KEY = "customers"
CACHE_SECONDS = 5.0
WINDOW_DAYS = 180
MAX_SESSIONS = 50


class CustomerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class CustomerNote:
    customer_id: str
    note: str
    author: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "note": self.note, "author": self.author, "createdAt": self.created_at}


class NotesRepo(Protocol):
    async def add(self, n: CustomerNote) -> None: ...
    async def list(self, customer_id: str) -> list[CustomerNote]: ...
    async def delete(self, customer_id: str, note_id: str) -> bool: ...
    async def erase_customer(self, customer_id: str) -> int: ...


class InMemoryNotes:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], CustomerNote] = {}

    async def add(self, n: CustomerNote) -> None:
        self._items[(current_tenant(), n.id)] = n

    async def list(self, customer_id: str) -> list[CustomerNote]:
        t = current_tenant()
        return sorted((n for (tt, _), n in self._items.items() if tt == t and n.customer_id == customer_id), key=lambda n: -n.created_at)

    async def delete(self, customer_id: str, note_id: str) -> bool:
        n = self._items.get((current_tenant(), note_id))
        return n is not None and n.customer_id == customer_id and self._items.pop((current_tenant(), note_id)) is not None

    async def erase_customer(self, customer_id: str) -> int:
        t = current_tenant()
        gone = [k for k, n in self._items.items() if k[0] == t and n.customer_id == customer_id]
        for k in gone:
            del self._items[k]
        return len(gone)


class CustomerService:
    def __init__(self, notes: NotesRepo | None = None, settings: SettingsRepo | None = None):
        self.notes = notes or InMemoryNotes()
        self.settings = settings or InMemorySettings()
        self._cache: dict[str, tuple[float, bool]] = {}

    async def enabled(self) -> bool:
        t = current_tenant()
        hit = self._cache.get(t)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        try:
            v = await self.settings.get(KEY)
            on = True if v is None else bool(v.get("enabled", True))
        except Exception:  # noqa: BLE001 - an unreadable setting must not switch the tab on or off by accident; keep what we last knew
            return hit[1] if hit else True
        self._cache[t] = (time.monotonic(), on)
        return on

    async def set_enabled(self, on: bool, by: str) -> None:
        await self.settings.put(KEY, {"enabled": on}, by)
        self._cache.pop(current_tenant(), None)

    async def profile(self, customer_id: str, sessions: list[str], turns: list[Any], handoffs: list[Any], feedback: list[Any], reviews: dict[str, Any], facts: list[Any]) -> dict[str, Any]:
        want = set(sessions)
        by: dict[str, list[Any]] = {}
        for t in turns:
            if t.session_id in want:
                by.setdefault(t.session_id, []).append(t)
        hands: dict[str, list[Any]] = {}
        for h in handoffs:
            if h.session_id in want:
                hands.setdefault(h.session_id, []).append(h)
        rating = {f.session_id: f.rating for f in feedback if f.session_id in want}
        rows = []
        for sid, ts in by.items():
            ts.sort(key=lambda t: t.started_at)
            rv = reviews.get(sid)
            rows.append({"sessionId": sid, "agentId": ts[0].agent_id, "channel": next((t.channel for t in ts if t.channel), None), "startedAt": ts[0].started_at,
                         "endedAt": ts[-1].started_at + ts[-1].duration, "turns": len(ts), "lastStatus": ts[-1].status, "firstMessage": mask(ts[0].first_message, 160),
                         "handedOff": sid in hands, "handoffReasons": [h.trigger for h in hands.get(sid, [])], "rating": rating.get(sid), "review": rv.verdict if rv else None})
        rows.sort(key=lambda r: -r["startedAt"])
        rated = [v for v in rating.values()]
        shown = mask(customer_id, 80)
        return {"ref": customer_ref(customer_id), "idMasked": shown != customer_id, "id": shown, "sessions": len(sessions), "windowDays": WINDOW_DAYS,
                "timeline": rows[:MAX_SESSIONS], "truncated": len(rows) > MAX_SESSIONS,
                "satisfaction": {"rated": len(rated), "average": round(sum(rated) / len(rated), 2) if rated else None, "handedOff": sum(r["handedOff"] for r in rows),
                                 "counts": "Ratings customers gave in the conversations listed; conversations nobody rated are not counted"},
                "facts": [{**m.to_dict(), "text": mask(m.text, 300), "addedBy": "the agent" if m.source_session else "staff or import"} for m in facts],
                "notes": [n.to_dict() for n in await self.notes.list(customer_id)],
                "note": f"Only the last {WINDOW_DAYS} days of conversations are listed. Personal data is masked."}
