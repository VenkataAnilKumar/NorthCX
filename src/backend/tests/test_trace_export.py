"""Trace export: conversion, redaction, Langfuse and OTLP payloads, queued delivery, privacy and the API."""
import asyncio
import base64
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.privacy import PrivacyService
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import Trace, TraceStore
from northcx.trace_export import (ExportJob, ExportService, InMemoryExports, LangfuseExporter, OtlpExporter, Redactor, convert, iso)


def sample_trace():
    t = Trace("support", "s1", agent_version=3)
    t.add("user", message="Hi, I'm jane@example.com, call me on 415-555-0199. Where is order 1042?")
    t.add("llm", step=0, stop_reason="tool_use", tokens=120, model="claude-x")
    t.add("tool_call", name="lookup_order", input={"order_id": "1042", "note": "ssn 123-45-6789"})
    t.add("tool_result", name="lookup_order", output={"status": "delivered", "email": "jane@example.com"})
    t.add("guardrail", guardrail="no-card-numbers", reason="Reply contains a payment-card number.", stage="reply")
    t.add("llm", step=1, stop_reason="end_turn", tokens=80, model="claude-x", fallback=True)
    t.add("error", tool="issue_refund", error="boom for jane@example.com")
    t.add("reply", reply="Order 1042 was delivered. Write to jane@example.com.", status="completed")
    return t


# ---- redaction ----
def test_masked_mode_hides_personal_data_everywhere_text_can_appear():
    ex = convert(sample_trace(), Redactor("masked"))
    blob = json.dumps(ex, default=lambda o: o.__dict__)
    for secret in ["jane@example.com", "415-555-0199", "123-45-6789"]:
        assert secret not in blob
    assert "order 1042" in ex.input.lower() and "Order 1042 was delivered" in ex.output


def test_none_mode_sends_structure_only():
    ex = convert(sample_trace(), Redactor("none"))
    blob = json.dumps(ex, default=lambda o: o.__dict__)
    for leaked in ["jane", "order_id", "1042", "delivered", "boom", "payment-card", "Where is"]:
        assert leaked not in blob, leaked
    assert ex.input is None and ex.output is None and ex.status == "completed"
    names = [(o.kind, o.name) for o in ex.observations]
    assert ("tool", "lookup_order") in names and ("event", "guardrail") in names
    gen = [o for o in ex.observations if o.kind == "generation"]
    assert [g.tokens for g in gen] == [120, 80] and gen[0].model == "claude-x"


def test_full_mode_keeps_text_but_still_truncates():
    t = Trace("a", "s")
    t.add("user", message="x" * 50_000)
    t.add("reply", reply="ok jane@example.com", status="completed")
    ex = convert(t, Redactor("full"))
    assert len(ex.input) < 20_100 and ex.input.endswith("[truncated]") and "jane@example.com" in ex.output
    with pytest.raises(ValueError):
        Redactor("everything")


def test_conversion_structure():
    ex = convert(sample_trace(), Redactor("masked"), "staging")
    assert (ex.name, ex.session_id, ex.version, ex.environment) == ("support", "s1", 3, "staging")
    kinds = [(o.kind, o.name, o.level) for o in ex.observations]
    assert kinds == [("generation", "model call", "DEFAULT"), ("tool", "lookup_order", "DEFAULT"), ("event", "guardrail", "WARNING"),
                     ("generation", "model call", "DEFAULT"), ("event", "error", "ERROR")]
    tool = ex.observations[1]
    assert tool.output["status"] == "delivered" and tool.end >= tool.start
    assert ex.observations[3].metadata["fallback"] is True
    empty = convert(Trace("a", "s"), Redactor())
    assert empty.observations == [] and empty.status == "unknown" and empty.input is None


# ---- Langfuse ----
async def test_langfuse_batch_shape_and_auth():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(207, json={"successes": [], "errors": []})

    lf = LangfuseExporter("https://lf.example.com/", "pk-1", "sk-1", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await lf.export(convert(sample_trace(), Redactor("masked")))
    assert seen["url"] == "https://lf.example.com/api/public/ingestion" and base64.b64decode(seen["auth"].split()[1]) == b"pk-1:sk-1"
    batch = seen["body"]["batch"]
    assert [e["type"] for e in batch] == ["trace-create", "generation-create", "span-create", "event-create", "generation-create", "event-create"]
    trace = batch[0]["body"]
    assert trace["name"] == "support" and trace["sessionId"] == "s1" and trace["version"] == "3" and trace["environment"] == "production"
    assert all(e["body"].get("traceId") == trace["id"] for e in batch[1:]) and len({e["id"] for e in batch}) == len(batch)
    gen = batch[1]["body"]
    assert gen["model"] == "claude-x" and gen["usageDetails"] == {"total": 120} and gen["startTime"].endswith("Z") and "endTime" in gen
    assert "endTime" not in batch[3]["body"] and batch[3]["body"]["level"] == "WARNING" and batch[2]["body"]["input"]["order_id"] == "1042"
    assert None not in batch[2]["body"].values()
    assert iso(0) == "1970-01-01T00:00:00.000Z"


async def test_langfuse_failures_are_reported_without_secrets():
    for resp in [httpx.Response(401, text="bad sk-1"), httpx.Response(500), httpx.Response(207, json={"errors": [{"id": "x"}]})]:
        lf = LangfuseExporter("https://lf.example.com", "pk-1", "sk-1", client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r, resp=resp: resp)))
        with pytest.raises(RuntimeError) as e:
            await lf.export(convert(sample_trace(), Redactor()))
        assert "sk-1" not in str(e.value) and "lf.example.com" not in str(e.value)

    def boom(req):
        raise httpx.ConnectError("no route to lf.example.com")

    with pytest.raises(RuntimeError, match="ConnectError"):
        await LangfuseExporter("https://lf.example.com", "p", "s", client=httpx.AsyncClient(transport=httpx.MockTransport(boom))).export(convert(sample_trace(), Redactor()))
    for args in [("ftp://x", "p", "s"), ("https://x", "", "s"), ("https://x", "p", "")]:
        with pytest.raises(ValueError):
            LangfuseExporter(*args)


# ---- OTLP ----
async def test_otlp_payload_is_a_valid_span_tree_with_custom_headers():
    seen = {}

    def handler(req):
        seen["url"], seen["h"], seen["body"] = str(req.url), dict(req.headers), json.loads(req.content)
        return httpx.Response(200, json={})

    ex = OtlpExporter("https://otel.example.com", {"x-honeycomb-team": "abc"}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await ex.export(convert(sample_trace(), Redactor("masked")))
    assert seen["url"] == "https://otel.example.com/v1/traces" and seen["h"]["x-honeycomb-team"] == "abc"
    spans = seen["body"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    root, kids = spans[0], spans[1:]
    assert len(root["traceId"]) == 32 and len(root["spanId"]) == 16 and "parentSpanId" not in root and len(kids) == 5
    assert all(k["traceId"] == root["traceId"] and k["parentSpanId"] == root["spanId"] and len(k["spanId"]) == 16 for k in kids)
    assert len({s["spanId"] for s in spans}) == len(spans)
    assert all(int(s["endTimeUnixNano"]) >= int(s["startTimeUnixNano"]) for s in spans)
    attrs = {a["key"]: a["value"] for a in root["attributes"]}
    assert attrs["northcx.status"] == {"stringValue": "completed"} and attrs["northcx.agent_version"] == {"intValue": "3"}
    assert kids[-1]["status"]["code"] == 2 and kids[0]["status"]["code"] == 1
    gen = {a["key"]: a["value"] for a in kids[0]["attributes"]}
    assert gen["gen_ai.usage.total_tokens"] == {"intValue": "120"} and gen["gen_ai.request.model"] == {"stringValue": "claude-x"}
    assert seen["body"]["resourceSpans"][0]["resource"]["attributes"][0]["value"] == {"stringValue": "northcx"}
    other = ex.payload(convert(sample_trace(), Redactor()))  # a different conversation gets different ids
    assert other["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] != root["traceId"]


def test_otlp_endpoint_and_header_parsing():
    assert OtlpExporter("https://o.example.com/v1/traces").url == "https://o.example.com/v1/traces" and OtlpExporter("https://o.example.com/").url == "https://o.example.com/v1/traces"
    assert OtlpExporter.parse_headers("a=1, b = two=2 ,") == {"a": "1", "b": "two=2"} and OtlpExporter.parse_headers("") == {}
    for bad in ["novalue", "=x"]:
        with pytest.raises(ValueError):
            OtlpExporter.parse_headers(bad)
    with pytest.raises(ValueError):
        OtlpExporter("otel.example.com")


# ---- queue and service ----
class Fake:
    def __init__(self, name="fake", fail=0):
        self.name, self.fail, self.sent = name, fail, []

    async def export(self, trace):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("fake export: returned 503")
        self.sent.append(trace)


class Traces:
    def __init__(self, *ts):
        self.items = {t.id: t for t in ts}

    async def get(self, i):
        return self.items.get(i)


async def test_delivery_is_queued_retried_with_back_off_and_sent_once():
    t, repo, fake = sample_trace(), InMemoryExports(), Fake(fail=2)
    svc = ExportService(repo, [fake])
    assert await svc.enqueue(t) is True
    t0 = time.time()
    assert await svc.flush(Traces(t), t0) == 0 and (await repo.for_trace(t.id))[0].error == "fake export: returned 503"
    assert await svc.flush(Traces(t), t0 + 5) == 0 and (await repo.for_trace(t.id))[0].attempts == 1
    assert await svc.flush(Traces(t), t0 + 31) == 0
    assert await svc.flush(Traces(t), t0 + 100) == 1 and len(fake.sent) == 1
    assert await svc.flush(Traces(t), t0 + 10_000) == 0 and await repo.counts() == {"pending": 0, "delivered": 1, "failed": 0}


async def test_each_exporter_is_independent_and_failures_are_counted():
    t, repo = sample_trace(), InMemoryExports()
    good, bad = Fake("good"), Fake("bad", fail=999)
    svc = ExportService(repo, [good, bad])
    await svc.enqueue(t)
    for i in range(15):
        await svc.flush(Traces(t), time.time() + i * 4000)
    assert len(good.sent) == 1 and await repo.counts() == {"pending": 0, "delivered": 1, "failed": 1}


async def test_sampling_is_deterministic_per_trace_and_validated():
    svc = ExportService(InMemoryExports(), [Fake()], sample=0.3)
    ids = [Trace("a", "s").id for _ in range(400)]
    chosen = [svc.sampled(i) for i in ids]
    assert 0.15 < sum(chosen) / 400 < 0.45 and chosen == [svc.sampled(i) for i in ids]
    assert ExportService(InMemoryExports(), [Fake()], sample=0).sampled(ids[0]) is False and ExportService(InMemoryExports(), [Fake()]).sampled(ids[0])
    for bad in (-0.1, 1.5):
        with pytest.raises(ValueError):
            ExportService(InMemoryExports(), [Fake()], sample=bad)


async def test_traces_erased_after_queueing_are_dropped():
    t, repo, fake = sample_trace(), InMemoryExports(), Fake()
    svc = ExportService(repo, [fake])
    await svc.enqueue(t)
    assert await svc.flush(Traces(), time.time()) == 0 and fake.sent == [] and await repo.pending() == []


# ---- runtime, privacy and API ----
async def test_finished_conversations_are_queued_but_simulations_are_not():
    repo = InMemoryExports()
    svc = ExportService(repo, [Fake()])
    rt = Runtime(ScriptedLLM([text("hi"), text("hello")]), InMemoryStore(), TraceStore(), exports=svc)
    r = await rt.run(support_agent(), "s1", "hello", "jane")
    assert [j.trace_id for j in await repo.pending()] == [r.trace_id]
    dry = Runtime(ScriptedLLM([text("x")]), InMemoryStore(), TraceStore(), exports=svc, dry_run=True)
    await dry.run(support_agent(), "s2", "hello")
    assert len(await repo.pending()) == 1

    class Broken(InMemoryExports):
        async def enqueue(self, jobs):
            raise OSError("db down")

    ok = Runtime(ScriptedLLM([text("fine")]), InMemoryStore(), TraceStore(), exports=ExportService(Broken(), [Fake()]))
    assert (await ok.run(support_agent(), "s3", "hello")).reply == "fine"


async def test_erasing_a_customer_removes_their_queued_exports():
    repo = InMemoryExports()
    rt = Runtime(ScriptedLLM([text("hi")]), InMemoryStore(), TraceStore(), exports=ExportService(repo, [Fake()]))
    r = await rt.run(support_agent(), "s1", "hello", "jane")
    assert (await PrivacyService(rt.privacy).erase_customer("jane"))["removed"]["exports"] == 1 and await repo.for_trace(r.trace_id) == []


def test_api_status_and_per_trace_deliveries():
    repo = InMemoryExports()
    rt = Runtime(ScriptedLLM([text("hi")]), InMemoryStore(), TraceStore(), exports=ExportService(repo, [Fake("langfuse"), Fake("otlp")], Redactor("none"), 0.5, "staging"))
    ac = AccessControl(bootstrap_key="boot" * 10)
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=ac))
    H = {"authorization": "Bearer " + "boot" * 10}
    tid = c.post("/v1/agents/support/chat", json={"sessionId": "s1", "message": "hello"}, headers=H).json()["traceId"]
    s = c.get("/v1/trace-export", headers=H).json()
    assert s["configured"] and s["exporters"] == ["langfuse", "otlp"] and s["content"] == "none" and s["sample"] == 0.5 and s["environment"] == "staging" and "pending" in s
    d = c.get(f"/v1/traces/{tid}/exports", headers=H).json()
    assert d["configured"] and len(d["deliveries"]) in (0, 2)
    assert c.get("/v1/traces/nope/exports", headers=H).status_code == 404
    chan = asyncio.new_event_loop().run_until_complete(ac.issue("c", "channel", "root"))[1]
    assert c.get("/v1/trace-export", headers={"authorization": f"Bearer {chan}"}).status_code == 403
    off = TestClient(create_app(Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore()), TraceStore(), {"support": support_agent()}))
    assert off.get("/v1/trace-export").json() == {"configured": False}


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        return InMemoryExports()
    from northcx.db import PgExports
    return PgExports(request.getfixturevalue("engine"))


async def test_export_repository_contract(store):
    a, b, c = ExportJob("t1", "langfuse", created_at=1), ExportJob("t1", "otlp", created_at=2), ExportJob("t2", "otlp", created_at=3)
    await store.enqueue([a, b, c])
    await store.enqueue([])
    assert [j.id for j in await store.pending()] == [a.id, b.id, c.id]
    await store.record(a.id, False, "boom", 10.0)
    await store.record(b.id, True, None, 11.0)
    got = {j.id: j for j in await store.for_trace("t1")}
    assert got[a.id].attempts == 1 and got[a.id].error == "boom" and got[b.id].delivered_at == 11.0
    assert await store.counts() == {"pending": 2, "delivered": 1, "failed": 0}
    for _ in range(12):
        await store.record(c.id, False, "x", 20.0)
    assert await store.counts() == {"pending": 1, "delivered": 1, "failed": 1}
    assert await store.erase_traces(["t1"]) == 2 and await store.for_trace("t1") == [] and await store.erase_traces([]) == 0
