from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class TraceEvent:
    t: float
    type: str  # user|llm|tool_call|tool_result|guardrail|approval|handoff|reply|error
    data: dict[str, Any]


@dataclass
class Trace:
    agent_id: str
    session_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    events: list[TraceEvent] = field(default_factory=list)
    agent_version: int | None = None
    environment: str = "production"

    def add(self, type: str, **data: Any) -> None:
        self.events.append(TraceEvent(time.time(), type, data))

    def status(self) -> str:
        for e in reversed(self.events):
            if e.type == "reply":
                return str(e.data.get("status", "completed"))
        return "unknown"

    def tools_called(self) -> list[str]:
        return [e.data["name"] for e in self.events if e.type == "tool_call"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceSummary:
    id: str
    agent_id: str
    session_id: str
    events: int
    status: str
    started_at: float | None
    tools: list[str]
    agent_version: int | None = None
    environment: str = "production"


def summarize(t: Trace) -> TraceSummary:
    return TraceSummary(t.id, t.agent_id, t.session_id, len(t.events), t.status(),
                        t.events[0].t if t.events else None, t.tools_called(), t.agent_version, t.environment)


class TraceRepo(Protocol):
    async def save(self, trace: Trace) -> None: ...
    async def get(self, trace_id: str) -> Trace | None: ...
    async def summaries(self, session_id: str | None = None, limit: int = 200) -> list[TraceSummary]: ...


class TraceStore:
    """In-memory trace repository (optionally mirrored to a JSONL file)."""

    def __init__(self, directory: str | None = None) -> None:
        self._traces: dict[str, Trace] = {}
        self._dir = Path(directory) if directory else None
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, trace: Trace) -> None:
        self._traces[trace.id] = trace
        if self._dir:
            with open(self._dir / "traces.jsonl", "a") as f:
                f.write(json.dumps(trace.to_dict(), default=str) + "\n")

    async def get(self, trace_id: str) -> Trace | None:
        return self._traces.get(trace_id)

    async def summaries(self, session_id: str | None = None, limit: int = 200) -> list[TraceSummary]:
        items = [summarize(t) for t in self._traces.values() if not session_id or t.session_id == session_id]
        items.sort(key=lambda x: x.started_at or 0, reverse=True)
        return items[:limit]
