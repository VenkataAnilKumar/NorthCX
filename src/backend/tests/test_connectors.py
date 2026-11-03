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
    assert len(files) == 5
    names = []
    for f in files:
        d = yaml.safe_load(open(f))
        hosts = {urllib.parse.urlsplit(d["base_url"]).hostname}
        if isinstance(d.get("auth"), dict) and d["auth"].get("token_url"):
            hosts.add(urllib.parse.urlsplit(d["auth"]["token_url"]).hostname)
        c = Connector(d, hosts, f)
        names += [t.name for t in c.tools]
    assert names == sorted(set(names), key=names.index) and {"orders_lookup", "orders_refund", "billing_invoice", "accounts_lookup", "helpdesk_create_ticket", "crm_recent_cases"} <= set(names)


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


# ---- pagination ----
HOSTS2 = {"api.shop.example.com", "login.shop.example.com"}


def list_cfg(pagination, **extra):
    t = {"name": "orders_list", "path": "/orders", "inputs": {"status": {"type": "string", "required": False}}, "query": {"status": "{status}"},
         "response": {"fields": ["id", "status"]}, "pagination": pagination}
    return cfg(tools=[t], **extra)


def pconn(handler, pagination, **extra):
    return Connector(list_cfg(pagination, **extra), HOSTS2, "t.yaml", httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False))


async def run_list(c, **inputs):
    t = tool(c, "orders_list")
    return await t.execute(t.input_model(**inputs), ctx())


def item(i):
    return {"id": f"O-{i}", "status": "shipped", "internal": "hidden"}


async def test_cursor_pages_are_followed_until_the_system_has_no_more():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        cur = req.url.params.get("cursor")
        nxt = {None: "c2", "c2": "c3", "c3": None}[cur]
        start = {None: 0, "c2": 2, "c3": 4}[cur]
        return httpx.Response(200, json={"data": [item(start), item(start + 1)], "meta": {"next_cursor": nxt}})
    out = await run_list(pconn(handler, {"style": "cursor", "items": "data", "next": "meta.next_cursor", "param": "cursor", "size_param": "limit", "page_size": 2}), status="shipped")
    assert out == {"items": [{"id": f"O-{i}", "status": "shipped"} for i in range(6)], "count": 6, "truncated": False}   # only the listed fields, from every page
    assert seen == [{"status": "shipped", "limit": "2"}, {"status": "shipped", "limit": "2", "cursor": "c2"}, {"status": "shipped", "limit": "2", "cursor": "c3"}]


async def test_paging_stops_at_the_page_and_item_limits_and_says_it_was_cut_short():
    calls = []

    def handler(req):
        calls.append(1)
        n = len(calls)
        return httpx.Response(200, json={"data": [item(n * 10 + k) for k in range(10)], "next": f"c{n}"})
    out = await run_list(pconn(handler, {"style": "cursor", "items": "data", "next": "next", "param": "c", "max_pages": 3, "max_items": 100}))
    assert len(calls) == 3 and out["count"] == 30 and out["truncated"] is True
    calls.clear()
    out = await run_list(pconn(handler, {"style": "cursor", "items": "data", "next": "next", "param": "c", "max_pages": 10, "max_items": 15}))
    assert out["count"] == 15 and out["truncated"] is True and len(calls) == 2


async def test_page_number_and_offset_styles():
    def by_page(req):
        page = int(req.url.params["page"])
        return httpx.Response(200, json=[item(i) for i in range(3)] if page < 3 else [item(99)])
    out = await run_list(pconn(by_page, {"style": "page", "param": "page", "size_param": "per_page", "page_size": 3}))
    assert out["count"] == 7 and out["truncated"] is False                                  # two full pages, then a short one ends it

    offsets = []

    def by_offset(req):
        o = int(req.url.params["offset"])
        offsets.append(o)
        return httpx.Response(200, json={"results": [item(o + k) for k in range(5)] if o < 10 else []})
    out = await run_list(pconn(by_offset, {"style": "offset", "param": "offset", "items": "results", "max_pages": 10}))
    assert offsets == [0, 5, 10] and out["count"] == 10 and out["truncated"] is False       # an empty page ends it


async def test_link_header_pages_stay_on_the_connectors_own_address_and_keep_the_credentials():
    seen = []

    def handler(req):
        seen.append((str(req.url), req.headers.get("authorization")))
        if "page=2" not in str(req.url):
            return httpx.Response(200, json=[item(1), item(2)], headers={"link": '<https://api.shop.example.com/v1/orders?page=2>; rel="next", <https://api.shop.example.com/v1/orders?page=9>; rel="last"'})
        return httpx.Response(200, json=[item(3)])
    out = await run_list(pconn(handler, {"style": "link_header"}))
    assert out["count"] == 3 and seen[1][0] == "https://api.shop.example.com/v1/orders?page=2" and all(a == "Bearer tok-SECRET" for _, a in seen)


@pytest.mark.parametrize("target", ["https://evil.example.net/v1/orders?page=2", "http://api.shop.example.com/v1/orders?page=2", "https://api.shop.example.com/admin/orders",
                                    "https://user:pw@api.shop.example.com/v1/orders", "https://api.shop.example.com:8443/v1/orders"])
async def test_a_link_to_somewhere_else_is_never_followed(target):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json=[item(1)], headers={"link": f'<{target}>; rel="next"'})
    with pytest.raises(CallFailed, match="outside its own address"):
        await run_list(pconn(handler, {"style": "link_header"}))
    assert len(calls) == 1 and "tok-SECRET" not in str(calls)                               # the credentials never went to the other address


async def test_unusable_answers_while_paging_are_reported_safely():
    def not_a_list(req):
        return httpx.Response(200, json={"data": {"oops": 1}})
    with pytest.raises(CallFailed, match="did not contain the list"):
        await run_list(pconn(not_a_list, {"style": "cursor", "items": "data", "next": "n", "param": "c"}))

    def complex_cursor(req):
        return httpx.Response(200, json={"data": [item(1)], "n": {"a": 1}})
    with pytest.raises(CallFailed, match="not a simple value"):
        await run_list(pconn(complex_cursor, {"style": "cursor", "items": "data", "next": "n", "param": "c"}))

    def second_page_fails(req):
        return httpx.Response(500) if req.url.params.get("c") else httpx.Response(200, json={"data": [item(1)], "n": "x"})
    with pytest.raises(CallFailed, match="returned 500"):
        await run_list(pconn(second_page_fails, {"style": "cursor", "items": "data", "next": "n", "param": "c"}))
    assert await run_list(pconn(lambda r: httpx.Response(404), {"style": "page", "param": "p"})) == {"found": False}


async def test_a_huge_page_is_trimmed_not_passed_on():
    big = [{"id": "x" * 2000, "status": "s"} for _ in range(120)]
    out = await run_list(pconn(lambda r: httpx.Response(200, json=big), {"style": "page", "param": "p", "max_items": 500, "max_pages": 1}))
    assert out["truncated"] is True and len(json.dumps(out["items"])) <= MAX_RESPONSE


@pytest.mark.parametrize("pagination,msg", [({"style": "rolling"}, "style must be"), ({"style": "cursor", "param": "c"}, "needs 'next'"), ({"style": "page"}, "needs 'param'"),
                                            ({"style": "page", "param": "status"}, "also set in the tool's own query"), ({"style": "page", "param": "p", "max_pages": 50}, "max_pages must be"),
                                            ({"style": "page", "param": "p", "max_items": 5000}, "max_items 1-500"), ({"style": "page", "param": "p?x=1"}, "must be a query parameter"),
                                            ({"style": "cursor", "param": "c", "next": "a b"}, "dotted field path"), ({"style": "page", "param": "p", "bogus": 1}, "pagination takes")])
def test_pagination_settings_are_checked(pagination, msg):
    with pytest.raises(ConnectorError, match=msg):
        Connector(list_cfg(pagination), HOSTS2, "t.yaml")


def test_only_reads_can_be_paginated():
    c = cfg()
    c["tools"][1]["pagination"] = {"style": "page", "param": "p"}
    with pytest.raises(ConnectorError, match="only GET tools"):
        Connector(c, HOSTS2, "t.yaml")


# ---- OAuth 2 ----
def oauth(**kw):
    a = {"type": "oauth2_client_credentials", "token_url": "https://login.shop.example.com/oauth/token", "client_id": "SHOP_ID", "client_secret": "SHOP_SECRET", "scope": "orders.read"}
    a.update(kw)
    return a


def oconn(api, token, auth=None, **kw):
    def handler(req):
        return token(req) if req.url.host == "login.shop.example.com" else api(req)
    c = Connector(cfg(auth=auth or oauth()), HOSTS2, "t.yaml", httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False))
    c._now = lambda: clock[0]  # type: ignore[method-assign]
    return c


clock = [1000.0]
OSECRETS = SecretStore({"shop_id": "client-123", "shop_secret": "s3cr3t-value", "shop_refresh": "refresh-abc"})


def octx():
    return ctx(secrets=OSECRETS)


async def lookup(c):
    t = tool(c, "orders_lookup")
    return await t.execute(t.input_model(order_id="A-1042"), octx())


async def test_client_credentials_fetch_one_token_and_reuse_it_until_it_is_about_to_expire():
    clock[0] = 1000.0
    forms, bearers = [], []

    def token(req):
        forms.append(urllib.parse.parse_qs(req.content.decode()))
        return httpx.Response(200, json={"access_token": f"at-{len(forms)}", "expires_in": 300, "token_type": "bearer"})

    def api(req):
        bearers.append(req.headers["authorization"])
        return httpx.Response(200, json={"id": "A-1", "status": "ok"})
    c = oconn(api, token)
    await lookup(c)
    await lookup(c)
    assert len(forms) == 1 and forms[0] == {"grant_type": ["client_credentials"], "client_id": ["client-123"], "client_secret": ["s3cr3t-value"], "scope": ["orders.read"]}
    clock[0] += 200
    await lookup(c)
    assert len(forms) == 1                                                                   # still good (more than 30 s left)
    clock[0] += 80
    await lookup(c)
    assert len(forms) == 2 and bearers == ["Bearer at-1", "Bearer at-1", "Bearer at-1", "Bearer at-2"]


async def test_the_client_can_sign_in_with_a_basic_header_instead_of_the_form():
    seen = {}

    def token(req):
        seen["auth"], seen["form"] = req.headers.get("authorization"), urllib.parse.parse_qs(req.content.decode())
        return httpx.Response(200, json={"access_token": "at", "expires_in": 60})
    await lookup(oconn(lambda r: httpx.Response(200, json={"id": "A"}), token, oauth(client_auth="basic")))
    import base64
    assert seen["auth"] == "Basic " + base64.b64encode(b"client-123:s3cr3t-value").decode() and "client_secret" not in seen["form"] and "client_id" not in seen["form"]


async def test_a_refused_token_is_renewed_once_and_then_given_up_on():
    clock[0] = 1000.0
    issued = []

    def token(req):
        issued.append(1)
        return httpx.Response(200, json={"access_token": f"at-{len(issued)}", "expires_in": 3600})
    seen = []

    def api(req):
        seen.append(req.headers["authorization"])
        return httpx.Response(401) if req.headers["authorization"] == "Bearer at-1" else httpx.Response(200, json={"id": "A-1", "status": "ok"})
    out = await lookup(oconn(api, token))
    assert out["id"] == "A-1" and seen == ["Bearer at-1", "Bearer at-2"] and len(issued) == 2
    always = oconn(lambda r: httpx.Response(401), token)
    with pytest.raises(CallFailed, match="returned 401"):
        await lookup(always)


async def test_sign_in_failures_are_reported_without_secrets_or_what_the_system_said():
    def refused(req):
        return httpx.Response(400, json={"error": "invalid_client", "error_description": "client s3cr3t-value is wrong"})
    with pytest.raises(CallFailed) as e:
        await lookup(oconn(lambda r: httpx.Response(200), refused))
    assert "token address returned 400" in str(e.value) and "s3cr3t" not in str(e.value) and "invalid_client" not in str(e.value)

    def down(req):
        raise httpx.ConnectError("boom login.shop.example.com s3cr3t-value")
    with pytest.raises(CallFailed) as e2:
        await lookup(oconn(lambda r: httpx.Response(200), down))
    assert "ConnectError" in str(e2.value) and "s3cr3t" not in str(e2.value) and "login.shop" not in str(e2.value)
    for body in (httpx.Response(200, json={"nope": 1}), httpx.Response(200, content=b"<html>"), httpx.Response(200, json=["x"]), httpx.Response(200, json={"access_token": ""})):
        with pytest.raises(CallFailed, match="usable token"):
            await lookup(oconn(lambda r: httpx.Response(200), lambda r, b=body: b))


async def test_the_token_never_appears_in_what_the_agent_sees():
    c = oconn(lambda r: httpx.Response(200, json={"id": "A-1", "status": "ok", "echo": "Bearer at-secret-token"}), lambda r: httpx.Response(200, json={"access_token": "at-secret-token", "expires_in": 60}))
    out = await lookup(c)
    assert "at-secret-token" not in json.dumps(out)


async def test_a_refresh_token_grant_uses_the_stored_refresh_token_and_remembers_a_new_one():
    clock[0] = 1000.0
    forms = []

    def token(req):
        forms.append(urllib.parse.parse_qs(req.content.decode()))
        return httpx.Response(200, json={"access_token": f"at-{len(forms)}", "expires_in": 31, "refresh_token": "refresh-NEW"})
    c = oconn(lambda r: httpx.Response(200, json={"id": "A"}), token, {"type": "oauth2_refresh_token", "token_url": "https://login.shop.example.com/oauth/token", "client_id": "SHOP_ID", "refresh_token": "SHOP_REFRESH"})
    await lookup(c)
    clock[0] += 5
    await lookup(c)
    assert forms[0]["grant_type"] == ["refresh_token"] and forms[0]["refresh_token"] == ["refresh-abc"] and "client_secret" not in forms[0]
    assert forms[1]["refresh_token"] == ["refresh-NEW"]                                       # providers that rotate refresh tokens are followed while the process runs


async def test_simultaneous_calls_share_one_sign_in():
    import asyncio
    clock[0] = 1000.0
    n = []

    def token(req):
        n.append(1)
        return httpx.Response(200, json={"access_token": "at", "expires_in": 600})
    c = oconn(lambda r: httpx.Response(200, json={"id": "A"}), token)
    await asyncio.gather(*(lookup(c) for _ in range(8)))
    assert len(n) == 1


@pytest.mark.parametrize("auth,msg", [(oauth(token_url="https://login.evil.example.net/t"), "token host 'login.evil.example.net' is not in NORTHCX_CONNECTOR_HOSTS"),
                                      (oauth(token_url="http://login.shop.example.com/t"), "must use https"), (oauth(token_url="https://u:p@login.shop.example.com/t"), "no credentials"),
                                      (oauth(token_url="https://login.shop.example.com/t?x=1"), "no credentials, query or fragment"), (oauth(client_secret=None), "needs client_secret"),
                                      (oauth(client_id="abc-123"), "name of a secret"), (oauth(client_secret="the actual secret value!"), "name of a secret"),
                                      (oauth(client_auth="query"), "client_auth"), (oauth(scope=5), "scope"), (oauth(bogus="x"), "auth needs type"),
                                      ({"type": "oauth2_refresh_token", "token_url": "https://login.shop.example.com/t", "client_id": "SHOP_ID"}, "needs refresh_token")])
def test_oauth_settings_are_checked(auth, msg):
    auth = {k: v for k, v in auth.items() if v is not None}
    with pytest.raises(ConnectorError, match=msg):
        Connector(cfg(auth=auth), HOSTS2, "t.yaml")
