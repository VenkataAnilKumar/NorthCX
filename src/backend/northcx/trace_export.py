"""Trace export (O3, O4): send finished conversation traces to an external observability backend, redacted.

Conversion is separate from transport: a trace becomes a neutral tree of observations (model calls, tool calls, events),
content is redacted according to a policy, and an exporter (OTLP over HTTP, or Langfuse's ingestion API) sends it.
Delivery is queued and retried so a slow backend never slows or breaks a conversation.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from .safety.pii import PIIDetection
from .trace import Trace

MAX_ATTEMPTS = 12
CONTENT_MODES = ("none", "masked", "full")
LIMITS = {"none": 0, "masked": 2000, "full": 20000}
# With content "none" only these keys survive: names, outcomes and counts, never anything a customer or tool wrote.
SAFE_KEYS = {"name", "tool", "status", "stop_reason", "step", "tokens", "model", "fallback", "guardrail", "stage", "topics", "trigger", "scope",
             "used", "limit", "recalled", "tokens_before", "tokens_after", "turns_summarised", "keys", "dropped", "dry_run", "approvals"}
_PII = PIIDetection(mask_pii=True)


class Redactor:
    def __init__(self, mode: str = "masked"):
        if mode not in CONTENT_MODES:
            raise ValueError(f"content mode must be one of {', '.join(CONTENT_MODES)}")
        self.mode, self.limit = mode, LIMITS[mode]

    def text(self, value: str) -> str:
        if self.mode == "none":
            return ""
        out = _PII.mask(value)[0] if self.mode == "masked" else value
        return out if len(out) <= self.limit else out[: self.limit] + "…[truncated]"

    def value(self, v: Any, key: str | None = None) -> Any:
        if self.mode == "none":
            return v if key in SAFE_KEYS and isinstance(v, (int, float, bool)) else (self._safe(v) if key in SAFE_KEYS else None)
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, dict):
            return {k: self.value(x, k) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [self.value(x) for x in v][:100]
        return v

    def _safe(self, v: Any) -> Any:
        if isinstance(v, str):
            return v[:100]
        if isinstance(v, list):
            return [x if isinstance(x, (int, float, bool)) else str(x)[:60] for x in v[:30]]
        return v if isinstance(v, (int, float, bool)) else None

    def data(self, d: dict[str, Any]) -> dict[str, Any]:
        out = {k: self.value(v, k) for k, v in d.items()}
        return {k: v for k, v in out.items() if v is not None} if self.mode == "none" else out


@dataclass
class Observation:
    id: str
    kind: str  # generation | tool | event
    name: str
    start: float
    end: float
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    level: str = "DEFAULT"  # DEFAULT | WARNING | ERROR
    model: str | None = None
    tokens: int | None = None


@dataclass
class ExportTrace:
    id: str
    name: str
    session_id: str
    start: float
    end: float
    status: str
    version: int | None
    input: Any
    output: Any
    observations: list[Observation]
    environment: str = "production"


WARN = {"guardrail", "handoff", "budget", "forced_topic", "duplicate_call"}


def convert(trace: Trace, redactor: Redactor, environment: str = "production") -> ExportTrace:
    ev = trace.events
    t0 = ev[0].t if ev else time.time()
    obs: list[Observation] = []
    first_in = next((e for e in ev if e.type in ("user", "system")), None)
    last_reply = next((e for e in reversed(ev) if e.type == "reply"), None)
    prev_t, i = t0, 0
    while i < len(ev):
        e = ev[i]
        if e.type == "llm":
            d = redactor.data(e.data)
            obs.append(Observation(uuid.uuid4().hex, "generation", "model call", prev_t, e.t, metadata={"step": d.get("step"), "stop_reason": d.get("stop_reason"), "fallback": d.get("fallback", False)},
                                   model=d.get("model") if isinstance(d.get("model"), str) else None, tokens=d.get("tokens") if isinstance(d.get("tokens"), int) else None))
        elif e.type == "tool_call":
            name = e.data.get("name", "tool")
            nxt = next((x for x in ev[i + 1:] if x.type in ("tool_result", "error", "tool_call", "llm", "reply", "approval", "handoff")), None)
            res = nxt if nxt is not None and nxt.type in ("tool_result", "error") and (nxt.data.get("name") or nxt.data.get("tool")) == name else None
            level = "ERROR" if res is not None and res.type == "error" else "DEFAULT"
            obs.append(Observation(uuid.uuid4().hex, "tool", str(name), e.t, res.t if res is not None else e.t, redactor.value(e.data.get("input"), "input"),
                                   redactor.value(res.data.get("output"), "output") if res is not None and res.type == "tool_result" else None,
                                   {"dry_run": True} if res is not None and res.data.get("dry_run") else {}, level))
        elif e.type in ("tool_result", "user", "system", "reply"):
            pass  # folded into tool spans and the trace's input and output
        else:
            level = "ERROR" if e.type == "error" else "WARNING" if e.type in WARN else "DEFAULT"
            obs.append(Observation(uuid.uuid4().hex, "event", e.type, e.t, e.t, metadata=redactor.data(e.data), level=level))
        prev_t = e.t
        i += 1
    end = ev[-1].t if ev else t0
    environment = trace.environment if trace.environment != "production" else environment
    return ExportTrace(trace.id, trace.agent_id, trace.session_id, t0, end, str(last_reply.data.get("status")) if last_reply else "unknown", trace.agent_version,
                       redactor.value(first_in.data.get("message"), "input") if first_in else None,
                       redactor.value(last_reply.data.get("reply"), "output") if last_reply else None, obs, environment)


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TraceExporter(Protocol):
    name: str

    async def export(self, trace: ExportTrace) -> None: ...


def _fail(what: str, e: Exception | None = None, status: int | None = None) -> RuntimeError:
    return RuntimeError(f"{what}: " + (f"returned {status}" if status is not None else type(e).__name__ if e else "failed"))


class LangfuseExporter:
    """Langfuse's public ingestion API: one trace plus a generation, span or event per observation."""
    name = "langfuse"

    def __init__(self, base_url: str, public_key: str, secret_key: str, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("NORTHCX_LANGFUSE_URL must start with https:// (or http:// for local testing)")
        if not public_key or not secret_key:
            raise ValueError("Langfuse needs NORTHCX_LANGFUSE_PUBLIC_KEY and NORTHCX_LANGFUSE_SECRET_KEY")
        self.url = base_url.rstrip("/") + "/api/public/ingestion"
        self._auth = "Basic " + base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    def batch(self, t: ExportTrace) -> list[dict[str, Any]]:
        now = iso(time.time())
        out: list[dict[str, Any]] = [{"id": uuid.uuid4().hex, "timestamp": now, "type": "trace-create", "body": {
            "id": t.id, "timestamp": iso(t.start), "name": t.name, "sessionId": t.session_id, "input": t.input, "output": t.output,
            "environment": t.environment, "version": str(t.version) if t.version else None, "metadata": {"status": t.status}, "tags": [t.status]}}]
        for o in t.observations:
            body: dict[str, Any] = {"id": o.id, "traceId": t.id, "name": o.name, "startTime": iso(o.start), "endTime": iso(o.end), "input": o.input, "output": o.output,
                                    "metadata": o.metadata or None, "level": o.level, "environment": t.environment}
            kind = "generation-create" if o.kind == "generation" else "span-create" if o.kind == "tool" else "event-create"
            if o.kind == "event":
                body.pop("endTime")
            if o.kind == "generation":
                body["model"] = o.model
                if o.tokens is not None:
                    body["usageDetails"] = {"total": o.tokens}
            out.append({"id": uuid.uuid4().hex, "timestamp": now, "type": kind, "body": {k: v for k, v in body.items() if v is not None}})
        return out

    async def export(self, trace: ExportTrace) -> None:
        try:
            r = await self._client.post(self.url, json={"batch": self.batch(trace), "metadata": {"source": "northcx"}},
                                        headers={"authorization": self._auth})
        except httpx.HTTPError as e:
            raise _fail("langfuse export", e) from e
        if r.status_code >= 300:  # the API answers 207 with per-event errors for partial failures
            raise _fail("langfuse export", status=r.status_code)
        try:
            if r.json().get("errors"):
                raise RuntimeError("langfuse export: some events were rejected")
        except ValueError:
            pass


def _attr(k: str, v: Any) -> dict[str, Any] | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return {"key": k, "value": {"boolValue": v}}
    if isinstance(v, int):
        return {"key": k, "value": {"intValue": str(v)}}
    if isinstance(v, float):
        return {"key": k, "value": {"doubleValue": v}}
    return {"key": k, "value": {"stringValue": v if isinstance(v, str) else json.dumps(v, default=str)[:4000]}}


def _hex(seed: str, n: int) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:n]


class OtlpExporter:
    """OpenTelemetry OTLP/HTTP (JSON): every trace is a span tree, so any OTLP-capable backend can receive it."""
    name = "otlp"

    def __init__(self, endpoint: str, headers: dict[str, str] | None = None, service: str = "northcx", client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("NORTHCX_OTLP_ENDPOINT must start with https:// (or http:// for local testing)")
        self.url = endpoint.rstrip("/") + ("" if endpoint.rstrip("/").endswith("/v1/traces") else "/v1/traces")
        self.headers, self.service = dict(headers or {}), service
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    @staticmethod
    def parse_headers(raw: str) -> dict[str, str]:
        out = {}
        for part in filter(None, (p.strip() for p in raw.split(","))):
            k, sep, v = part.partition("=")
            if not sep or not k.strip():
                raise ValueError("NORTHCX_OTLP_HEADERS must look like 'name=value,name2=value2'")
            out[k.strip()] = v.strip()
        return out

    def payload(self, t: ExportTrace) -> dict[str, Any]:
        trace_id = _hex(t.id, 32)
        root_id = _hex(t.id + "root", 16)
        ns = lambda x: str(int(x * 1e9))  # noqa: E731
        def span(sid: str, parent: str | None, name: str, start: float, end: float, attrs: dict[str, Any], error: bool = False) -> dict[str, Any]:
            return {"traceId": trace_id, "spanId": sid, **({"parentSpanId": parent} if parent else {}), "name": name, "kind": 1,
                    "startTimeUnixNano": ns(start), "endTimeUnixNano": ns(end), "attributes": [a for a in (_attr(k, v) for k, v in attrs.items()) if a],
                    "status": {"code": 2 if error else 1}}
        spans = [span(root_id, None, f"conversation turn {t.name}", t.start, t.end,
                      {"northcx.agent": t.name, "northcx.session": t.session_id, "northcx.status": t.status, "northcx.agent_version": t.version,
                       "northcx.input": t.input, "northcx.output": t.output, "deployment.environment": t.environment})]
        for o in t.observations:
            attrs = {"northcx.kind": o.kind, "northcx.level": o.level, "northcx.input": o.input, "northcx.output": o.output, "gen_ai.request.model": o.model,
                     "gen_ai.usage.total_tokens": o.tokens, **{f"northcx.{k}": v for k, v in o.metadata.items()}}
            spans.append(span(_hex(o.id, 16), root_id, o.name, o.start, o.end, attrs, o.level == "ERROR"))
        return {"resourceSpans": [{"resource": {"attributes": [_attr("service.name", self.service)]},
                                   "scopeSpans": [{"scope": {"name": "northcx"}, "spans": spans}]}]}

    async def export(self, trace: ExportTrace) -> None:
        try:
            r = await self._client.post(self.url, json=self.payload(trace), headers=self.headers)
        except httpx.HTTPError as e:
            raise _fail("otlp export", e) from e
        if r.status_code >= 300:
            raise _fail("otlp export", status=r.status_code)


# ---------------- queue ----------------
@dataclass
class ExportJob:
    trace_id: str
    exporter: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    last_attempt_at: float | None = None
    delivered_at: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"exporter": self.exporter, "attempts": self.attempts, "delivered": self.delivered_at is not None, "deliveredAt": self.delivered_at,
                "lastAttemptAt": self.last_attempt_at, "error": self.error}


class ExportRepo(Protocol):
    async def enqueue(self, jobs: list[ExportJob]) -> None: ...
    async def pending(self, limit: int = 100) -> list[ExportJob]: ...
    async def record(self, job_id: str, delivered: bool, error: str | None, at: float) -> None: ...
    async def for_trace(self, trace_id: str) -> list[ExportJob]: ...
    async def erase_traces(self, trace_ids: list[str]) -> int: ...
    async def counts(self) -> dict[str, int]: ...


class InMemoryExports:
    def __init__(self) -> None:
        self.jobs: list[ExportJob] = []

    async def enqueue(self, jobs) -> None:
        self.jobs.extend(jobs)

    async def pending(self, limit=100) -> list[ExportJob]:
        return [j for j in sorted(self.jobs, key=lambda j: j.created_at) if j.delivered_at is None and j.attempts < MAX_ATTEMPTS][:limit]

    async def record(self, job_id, delivered, error, at) -> None:
        for j in self.jobs:
            if j.id == job_id:
                j.attempts += 1
                j.last_attempt_at, j.error = at, None if delivered else error
                if delivered:
                    j.delivered_at = at
                return

    async def for_trace(self, trace_id) -> list[ExportJob]:
        return [j for j in self.jobs if j.trace_id == trace_id]

    async def erase_traces(self, trace_ids) -> int:
        n = len(self.jobs)
        gone = set(trace_ids)
        self.jobs = [j for j in self.jobs if j.trace_id not in gone]
        return n - len(self.jobs)

    async def counts(self) -> dict[str, int]:
        return {"pending": sum(1 for j in self.jobs if j.delivered_at is None and j.attempts < MAX_ATTEMPTS),
                "delivered": sum(1 for j in self.jobs if j.delivered_at is not None),
                "failed": sum(1 for j in self.jobs if j.delivered_at is None and j.attempts >= MAX_ATTEMPTS)}


class ExportService:
    def __init__(self, repo: ExportRepo, exporters: list[TraceExporter], redactor: Redactor | None = None, sample: float = 1.0, environment: str = "production"):
        if not 0 <= sample <= 1:
            raise ValueError("sample must be between 0 and 1")
        self.repo, self.exporters = repo, {e.name: e for e in exporters}
        self.redactor, self.sample, self.environment = redactor or Redactor(), sample, environment

    def sampled(self, trace_id: str) -> bool:
        return self.sample >= 1 or int(hashlib.sha256(trace_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < self.sample

    async def enqueue(self, trace: Trace) -> bool:
        if not self.sampled(trace.id):
            return False
        await self.repo.enqueue([ExportJob(trace.id, name) for name in self.exporters])
        return True

    async def flush(self, traces: Any, now: float | None = None) -> int:
        now = time.time() if now is None else now
        sent = 0
        for j in await self.repo.pending():
            if j.attempts and j.last_attempt_at is not None and now < j.last_attempt_at + min(30 * 2 ** max(j.attempts - 1, 0), 3600):
                continue
            exporter = self.exporters.get(j.exporter)
            if exporter is None:
                continue
            trace = await traces.get(j.trace_id)
            if trace is None:  # erased since it was queued
                await self.repo.record(j.id, True, None, now)
                continue
            try:
                await exporter.export(convert(trace, self.redactor, self.environment))
                await self.repo.record(j.id, True, None, now)
                sent += 1
            except Exception as e:
                await self.repo.record(j.id, False, str(e)[:300] if isinstance(e, RuntimeError) else type(e).__name__, now)
        return sent
