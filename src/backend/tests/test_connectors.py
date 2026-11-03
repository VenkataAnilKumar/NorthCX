"""Connector library: tools defined as data, and the limits that keep them safe."""
import glob
import json
import urllib.parse

import httpx
import pytest
import yaml

from northcx.agent import Agent, ToolContext
from northcx.connectors import CallFailed, Connector, ConnectorError, MAX_RESPONSE, allowed_hosts_from, load_connectors
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.runtime import Runtime
from northcx.secrets import SecretStore
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

HOSTS = {"api.shop.example.com"}


def cfg(**kw):
    base = {"name": "orders", "base_url": "https://api.shop.example.com/v1", "auth": {"type": "bearer", "secret": "TOKEN"},
            "tools": [{"name": "orders_lookup", "path": "/orders/{order_id}", "inputs": {"order_id": {"type": "string", "pattern": "^[A-Za-z0-9-]{3,20}$"}},
                       "response": {"fields": ["id", "status", "customer.email"]}},
                      {"name": "orders_refund", "description": "Refund an order.", "method": "POST", "path": "/orders/{order_id}/refunds",
                       "inputs": {"order_id": {"type": "string"}, "amount": {"type": "number", "min": 0.01, "max": 1000}, "reason": {"type": "string", "required": False}},
                       "body": {"amount": "{amount}", "reason": "{reason}"}, "requires_approval": {"input": "amount", "above": 100, "reason": "big"},
                       "dry_run_result": {"id": "sim"}}]}
    base.update(kw)
    return base


def conn(handler, **kw):
    return Connector(cfg(**kw), HOSTS, "t.yaml", httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False))


def ctx(secrets=None, key="idem-123"):
    return ToolContext("s", "jane", InMemoryStore(), idempotency_key=key, secrets=secrets or SecretStore({"token": "tok-SECRET"}))


def tool(c, name):
    return next(t for t in c.tools if t.name == name)


# ---- calls ----
async def test_a_read_call_is_built_from_the_file_and_returns_only_listed_fields():
    seen = {}

    def handler(req):
        seen["req"] = req
        return httpx.Response(200, json={"id": "A-1", "status": "delivered", "customer": {"email": "jane@example.com", "ssn": "123"}, "internal_notes": "secret"})

    t = tool(conn(handler), "orders_lookup")
    out = await t.execute(t.input_model(order_id="A-1042"), ctx())
    assert out == {"id": "A-1", "status": "delivered", "customer.email": "jane@example.com"}  # nothing else the system returned
    r = seen["req"]
    assert str(r.url) == "https://api.shop.example.com/v1/orders/A-1042" and r.method == "GET" and r.headers["authorization"] == "Bearer tok-SECRET"
    assert "idempotency-key" not in r.headers and t.effect == "read"


async def test_a_write_call_carries_the_idempotency_key_and_a_json_body_without_empty_values():
    seen = {}

    def handler(req):
        seen["req"], seen["body"] = req, json.loads(req.content)
        return httpx.Response(201, json={"id": "R-9", "status": "ok"})

    t = tool(conn(handler), "orders_refund")
    await t.execute(t.input_model(order_id="A-1", amount=12.5), ctx(key="K-1"))
    assert seen["req"].method == "POST" and seen["req"].headers["idempotency-key"] == "K-1" and seen["body"] == {"amount": 12.5}  # reason was not given
    await t.execute(t.input_model(order_id="A-1", amount=12.5, reason="late"), ctx(key="K-2"))
    assert seen["body"] == {"amount": 12.5, "reason": "late"} and t.effect == "write"
    assert t.simulate(t.input_model(order_id="A-1", amount=5), None) == {"id": "sim"}


async def test_values_cannot_escape_the_path_and_inputs_are_validated_before_any_call():
    calls = []
    t = tool(conn(lambda r: (calls.append(r), httpx.Response(200, json={}))[1]), "orders_lookup")
    for bad in ["../admin", "a/b", "A-1?x=1", "a b c", "A", "x" * 30]:
        with pytest.raises(Exception):
            t.input_model(order_id=bad)
    refund = tool(conn(lambda r: httpx.Response(200)), "orders_refund")
    for bad in [{"order_id": "1", "amount": 0}, {"order_id": "1", "amount": 99999}, {"order_id": "1", "amount": "lots"}, {"amount": 5}]:
        with pytest.raises(Exception):
            refund.input_model(**bad)
    c2 = conn(lambda r: (calls.append(r), httpx.Response(200, json={}))[1], tools=[{"name": "plain_get", "path": "/things/{key}", "inputs": {"key": {"type": "string"}}}])
    t2 = c2.tools[0]
    await t2.execute(t2.input_model(key="a/b c?d#e"), ctx())
    assert calls[-1].url.raw_path == b"/v1/things/a%2Fb%20c%3Fd%23e"  # a path value is data, never structure


async def test_failures_are_reported_without_urls_secrets_or_bodies():
    for resp, frag in [(httpx.Response(500, text="boom tok-SECRET"), "returned 500"), (httpx.Response(401, json={"echo": "tok-SECRET"}), "returned 401"),
                       (httpx.Response(302, headers={"location": "https://evil.test/"}), "returned 302"), (httpx.Response(200, content=b"<html>"), "not JSON"),
                       (httpx.Response(200, content=b"x" * (MAX_RESPONSE + 1)), "too large")]:
        t = tool(conn(lambda r, resp=resp: resp), "orders_lookup")
        with pytest.raises(CallFailed, match=frag) as e:
            await t.execute(t.input_model(order_id="A-1"), ctx())
        assert "tok-SECRET" not in str(e.value) and "shop.example.com" not in str(e.value) and "evil" not in str(e.value)

    def boom(req):
        raise httpx.ConnectError("no route to api.shop.example.com with tok-SECRET")

    t = tool(conn(boom), "orders_lookup")
    with pytest.raises(CallFailed, match="ConnectError") as e:
        await t.execute(t.input_model(order_id="A-1"), ctx())
    assert "tok-SECRET" not in str(e.value) and "shop" not in str(e.value)


async def test_a_missing_order_is_a_normal_answer_and_empty_responses_are_ok():
    t = tool(conn(lambda r: httpx.Response(404)), "orders_lookup")
    assert await t.execute(t.input_model(order_id="A-1"), ctx()) == {"found": False}
    w = tool(conn(lambda r: httpx.Response(204)), "orders_refund")
    assert await w.execute(w.input_model(order_id="1", amount=5), ctx()) == {"ok": True}
    w404 = tool(conn(lambda r: httpx.Response(404)), "orders_refund")
    with pytest.raises(CallFailed, match="404"):
        await w404.execute(w404.input_model(order_id="1", amount=5), ctx())  # a write that finds nothing is an error, not "not found"


@pytest.mark.parametrize("auth,expect", [
    ({"type": "header", "header": "X-Api-Key", "secret": "TOKEN"}, lambda h: h["x-api-key"] == "tok-SECRET" and "authorization" not in h),
    ({"type": "basic", "user": "bot", "secret": "TOKEN"}, lambda h: h["authorization"].startswith("Basic ")),
    ({"type": "none"}, lambda h: "authorization" not in h and "x-api-key" not in h)])
async def test_authentication_styles(auth, expect):
    seen = {}

    def handler(req):
        seen.update(req.headers)
        return httpx.Response(200, json={})

    t = tool(conn(handler, auth=auth), "orders_lookup")
    await t.execute(t.input_model(order_id="A-1"), ctx())
    assert expect(seen)


async def test_a_missing_secret_fails_loudly_without_calling_the_system():
    called = []
    t = tool(conn(lambda r: (called.append(1), httpx.Response(200, json={}))[1]), "orders_lookup")
    with pytest.raises(Exception):
        await t.execute(t.input_model(order_id="A-1"), ctx(secrets=SecretStore({})))
    assert called == []


def test_approval_rules():
    t = tool(conn(lambda r: httpx.Response(200)), "orders_refund")
    assert t.requires_approval(t.input_model(order_id="1", amount=250)) == "big" and t.requires_approval(t.input_model(order_id="1", amount=100)) is None
    c = conn(lambda r: httpx.Response(200), tools=[{"name": "danger", "description": "x", "method": "DELETE", "path": "/x", "requires_approval": {"always": True, "reason": "careful"}}])
    assert c.tools[0].requires_approval(c.tools[0].input_model()) == "careful"


# ---- configuration is checked ----
@pytest.mark.parametrize("change,frag", [
    ({"base_url": "https://evil.example.org"}, "NORTHCX_CONNECTOR_HOSTS"), ({"base_url": "http://api.shop.example.com"}, "https"),
    ({"base_url": "https://user:pw@api.shop.example.com"}, "base_url"), ({"base_url": "https://api.shop.example.com?x=1"}, "base_url"),
    ({"base_url": "ftp://api.shop.example.com"}, "base_url"), ({"name": "Bad Name"}, "name"), ({"colour": "red"}, "unknown setting"),
    ({"auth": {"type": "bearer"}}, "secret"), ({"auth": {"type": "oauth"}}, "auth needs"), ({"auth": {"type": "header", "secret": "S"}}, "header name"),
    ({"tools": [{"name": "a_b", "path": "orders"}]}, "path must start"), ({"tools": [{"name": "a_b", "path": "/x/../y"}]}, "path must start"),
    ({"tools": [{"name": "a_b", "path": "/x/{missing}"}]}, "undeclared input"), ({"tools": [{"name": "a_b", "path": "/x", "method": "TRACE"}]}, "method must be"),
    ({"tools": [{"name": "a_b", "path": "/x", "method": "POST", "effect": "read"}]}, "changes things"), ({"tools": [{"name": "a_b", "path": "/x", "method": "POST"}]}, "need a description"),
    ({"tools": [{"name": "a_b", "path": "/x", "inputs": {"q": {"type": "list"}}}]}, "type must be"), ({"tools": [{"name": "a_b", "path": "/x", "inputs": {"q": {"pattern": "("}}}]}, "valid expression"),
    ({"tools": [{"name": "a_b", "path": "/x", "requires_approval": {"input": "nope", "above": 1}}]}, "requires_approval"),
    ({"tools": [{"name": "a_b", "path": "/x", "body": {"a": 1}}]}, "no body"), ({"tools": [{"name": "a_b", "path": "/x", "wat": 1}]}, "unknown or missing"),
    ({"tools": [{"name": "a_b", "path": "/x"}, {"name": "a_b", "path": "/y"}]}, "unique")])
def test_bad_connector_files_are_refused_with_a_reason(change, frag):
    with pytest.raises(ConnectorError, match=frag):
        Connector(cfg(**change), HOSTS, "bad.yaml")


def test_localhost_may_use_plain_http_and_hosts_parse():
    assert Connector(cfg(base_url="http://127.0.0.1:8080/api"), {"127.0.0.1"}, "t").base == "http://127.0.0.1:8080/api"
    assert allowed_hosts_from("a.example.com, B.example.com:8443") == {"a.example.com", "b.example.com:8443"} and allowed_hosts_from(None) == set()
    with pytest.raises(ConnectorError, match="not a host name"):
        allowed_hosts_from("https://a.example.com")


def test_directory_loading_skips_examples_and_rejects_name_clashes(tmp_path):
    (tmp_path / "orders.yaml").write_text(yaml.safe_dump(cfg()))
    (tmp_path / "ignored.example.yaml").write_text("this is not even valid: [")
    assert sorted(t.name for t in load_connectors(tmp_path, HOSTS)) == ["orders_lookup", "orders_refund"]
    (tmp_path / "more.yaml").write_text(yaml.safe_dump(cfg(name="other")))
    with pytest.raises(ConnectorError, match="used by another connector"):
        load_connectors(tmp_path, HOSTS)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "x.yaml").write_text(": : :\n\t")
    with pytest.raises(ConnectorError, match="not valid"):
        load_connectors(bad, HOSTS)
    (bad / "x.yaml").write_text("- a list")
    with pytest.raises(ConnectorError, match="mapping"):
        load_connectors(bad, HOSTS)


def test_the_shipped_example_connectors_are_valid_starting_points():
    files = sorted(glob.glob("examples/connectors/*.example.yaml"))
    assert len(files) == 4
    names = []
    for f in files:
        d = yaml.safe_load(open(f))
        c = Connector(d, {urllib.parse.urlsplit(d["base_url"]).hostname}, f)
        names += [t.name for t in c.tools]
    assert names == sorted(set(names), key=names.index) and {"orders_lookup", "orders_refund", "billing_invoice", "accounts_lookup", "helpdesk_create_ticket"} <= set(names)


# ---- through the runtime ----
async def test_an_agent_uses_a_connector_tool_end_to_end_with_approval_for_large_refunds():
    posted = []

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"id": "A-1042", "status": "delivered"})
        posted.append((json.loads(req.content), req.headers.get("idempotency-key")))
        return httpx.Response(200, json={"id": "R-1", "status": "ok"})

    c = conn(handler)
    agent = Agent(id="a", instructions="i", tools=c.tools)
    llm = ScriptedLLM([tool_call("orders_lookup", {"order_id": "A-1042"}, "t1"), tool_call("orders_refund", {"order_id": "A-1042", "amount": 250}, "t2"), text("Sent for approval.")])
    rt = Runtime(llm, InMemoryStore(), TraceStore(), secrets=SecretStore({"token": "tok-SECRET"}))
    r = await rt.run(agent, "s", "refund my order A-1042, 250", "jane")
    assert r.status == "needs_approval" and posted == []  # the large refund waits for a person
    from northcx.approval_flow import ApprovalFlow
    llm.script = [text("Refunded.")]
    await ApprovalFlow(rt).resolve({"a": agent}, (await rt.approvals.list("pending"))[0].id, True, "rae")
    assert len(posted) == 1 and posted[0][0] == {"amount": 250} and posted[0][1]  # executed once, with the approval's idempotency key
    assert "tok-SECRET" not in json.dumps([e.data for e in r.trace.events], default=str)
