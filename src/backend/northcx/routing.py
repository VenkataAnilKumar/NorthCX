"""Business hours and queue routing for hand-offs.

A routing file says when people are available (per time zone, with holidays), which queue a hand-off belongs to
(by topic or trigger), and what to tell a customer who arrives while the team is offline. With no file, every hand-off
goes to one always-open queue, as before.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_WINDOW = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


class RoutingError(ValueError):
    pass


def _minutes(h: str, m: str) -> int:
    h_, m_ = int(h), int(m)
    if not (0 <= h_ <= 24 and 0 <= m_ < 60) or (h_ == 24 and m_):
        raise RoutingError(f"'{h}:{m}' is not a time of day")
    return h_ * 60 + m_


def parse_days(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.lower().replace(" ", "").split(","):
        a, _, b = part.partition("-")
        if a not in DAYS or (b and b not in DAYS):
            raise RoutingError(f"unknown day in '{spec}' (use mon..sun, ranges like mon-fri, or lists like sat,sun)")
        i, j = DAYS.index(a), DAYS.index(b or a)
        out += list(range(i, j + 1)) if i <= j else list(range(i, 7)) + list(range(0, j + 1))
    return sorted(set(out))


def parse_windows(value: Any) -> list[tuple[int, int]]:
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items:
        raise RoutingError("hours must be a time range like '09:00-17:00' or a list of them")
    out = []
    for w in items:
        m = _WINDOW.match(str(w).strip())
        if not m:
            raise RoutingError(f"'{w}' is not a time range like 09:00-17:00")
        a, b = _minutes(m[1], m[2]), _minutes(m[3], m[4])
        if b <= a:
            raise RoutingError(f"'{w}' must end after it starts (split overnight hours into two ranges)")
        out.append((a, b))
    return sorted(out)


@dataclass
class Schedule:
    days: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # weekday -> windows in minutes
    always: bool = False

    @classmethod
    def from_config(cls, cfg: Any) -> "Schedule":
        if cfg in (None, "always", "24/7"):
            return cls(always=True)
        if not isinstance(cfg, dict):
            raise RoutingError("hours must be 'always' or a map like {mon-fri: '09:00-17:00'}")
        days: dict[int, list[tuple[int, int]]] = {}
        for spec, windows in cfg.items():
            for d in parse_days(str(spec)):
                days.setdefault(d, [])
                days[d] = sorted(days[d] + parse_windows(windows))
        return cls(days)


@dataclass
class Queue:
    name: str
    topics: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    schedule: Schedule | None = None  # None = the default schedule
    description: str = ""


@dataclass
class Route:
    queue: str
    open_now: bool
    next_open: float | None  # epoch seconds, when closed
    message: str | None  # what to tell the customer when closed


class Router:
    def __init__(self, tz: str = "UTC", default: Schedule | None = None, queues: list[Queue] | None = None, default_queue: str = "general",
                 holidays: set[date] | None = None, after_hours_message: str = "Our team is offline right now. A teammate will reply when we reopen{when}.",
                 ) -> None:
        try:
            self.tz = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise RoutingError(f"unknown time zone '{tz}'") from e
        self.tzname, self.default = tz, default or Schedule(always=True)
        self.queues = queues or []
        self.default_queue, self.holidays, self.message = default_queue, holidays or set(), after_hours_message
        names = [q.name for q in self.queues]
        if len(set(names)) != len(names):
            raise RoutingError("queue names must be unique")
        if self.queues and default_queue not in names:
            raise RoutingError(f"default_queue '{default_queue}' is not one of the queues")
        if "{when}" not in after_hours_message and len(after_hours_message) > 500:
            raise RoutingError("after_hours_message is too long")

    def queue_for(self, topics: list[str], trigger: str) -> str:
        for q in self.queues:
            if (set(q.topics) & set(topics)) or trigger in q.triggers:
                return q.name
        return self.default_queue

    def _schedule(self, queue: str) -> Schedule:
        for q in self.queues:
            if q.name == queue and q.schedule is not None:
                return q.schedule
        return self.default

    def is_open(self, queue: str, at: float | None = None) -> bool:
        sch = self._schedule(queue)
        if sch.always:
            return True
        local = datetime.fromtimestamp(time.time() if at is None else at, self.tz)
        if local.date() in self.holidays:
            return False
        minute = local.hour * 60 + local.minute
        return any(a <= minute < b for a, b in sch.days.get(local.weekday(), []))

    def next_open(self, queue: str, at: float | None = None) -> float | None:
        sch = self._schedule(queue)
        if sch.always:
            return None
        now = datetime.fromtimestamp(time.time() if at is None else at, self.tz)
        for offset in range(0, 15):
            day = now.date() + timedelta(days=offset)
            if day in self.holidays:
                continue
            for a, b in sch.days.get(day.weekday(), []):
                start = datetime(day.year, day.month, day.day, tzinfo=self.tz) + timedelta(minutes=a)
                if start > now or (start <= now < start + timedelta(minutes=b - a)):
                    return start.timestamp() if start > now else now.timestamp()
        return None

    def route(self, topics: list[str], trigger: str, at: float | None = None) -> Route:
        queue = self.queue_for(topics, trigger)
        if self.is_open(queue, at):
            return Route(queue, True, None, None)
        nxt = self.next_open(queue, at)
        when = ""
        if nxt is not None:
            local = datetime.fromtimestamp(nxt, self.tz)
            when = f" ({local.strftime('%A %H:%M')} {self.tzname})"
        return Route(queue, False, nxt, self.message.replace("{when}", when))

    def describe(self, at: float | None = None) -> dict[str, Any]:
        names = [q.name for q in self.queues] or [self.default_queue]
        return {"timezone": self.tzname, "defaultQueue": self.default_queue, "holidays": sorted(d.isoformat() for d in self.holidays),
                "queues": [{"name": n, "open": self.is_open(n, at), "nextOpen": None if self.is_open(n, at) else self.next_open(n, at),
                            "topics": next((q.topics for q in self.queues if q.name == n), []),
                            "triggers": next((q.triggers for q in self.queues if q.name == n), [])} for n in names]}


def load_router(path: str | Path) -> Router:
    """Read a routing file. Every problem is reported in one error so it can be fixed in one pass."""
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise RoutingError(f"cannot read routing file {path}: {e}") from e
    if not isinstance(data, dict):
        raise RoutingError("the routing file must be a map")
    unknown = set(data) - {"timezone", "hours", "holidays", "queues", "default_queue", "after_hours_message"}
    problems = [f"unknown setting '{k}'" for k in sorted(unknown)]
    try:
        default = Schedule.from_config(data.get("hours"))
    except RoutingError as e:
        problems.append(f"hours: {e}")
        default = Schedule(always=True)
    holidays: set[date] = set()
    for h in data.get("holidays") or []:
        try:
            holidays.add(date.fromisoformat(str(h)))
        except ValueError:
            problems.append(f"holiday '{h}' is not a date like 2026-12-25")
    queues: list[Queue] = []
    for i, q in enumerate(data.get("queues") or []):
        if not isinstance(q, dict) or not _NAME.match(str(q.get("name", ""))):
            problems.append(f"queue {i + 1}: needs a name of lowercase letters, digits, - or _")
            continue
        try:
            sch = Schedule.from_config(q["hours"]) if "hours" in q else None
        except RoutingError as e:
            problems.append(f"queue '{q['name']}' hours: {e}")
            sch = None
        queues.append(Queue(q["name"], [str(t) for t in q.get("topics") or []], [str(t) for t in q.get("triggers") or []], sch, str(q.get("description", ""))))
    if problems:
        raise RoutingError("; ".join(problems))
    kw: dict[str, Any] = {}
    if data.get("after_hours_message"):
        kw["after_hours_message"] = str(data["after_hours_message"])
    return Router(str(data.get("timezone", "UTC")), default, queues, str(data.get("default_queue", queues[0].name if queues else "general")), holidays, **kw)


DEFAULT_ROUTER = Router()
