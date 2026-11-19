"""The operator's side of MCP (Phase 2, WP 2.3): create, review, approve, switch off and check a connection, and what that does to the tools agents can use."""
import pytest

from northcx.agent import Agent
from northcx.llm import ScriptedLLM, text, tool_call
from northcx.mcp_connections import McpConnectionError, McpConnections
from northcx.runtime import Runtime
from northcx.secrets import SecretStore
from northcx.spec import Registry
from northcx.store import InMemoryStore
from northcx.tenancy import TENANT
from northcx.trace import TraceStore
from tests.mcp_fake import SECRET, URL, FakeMcp

SECRETS = SecretStore({"orders": SECRET})
LOOKUP, REFUND = "shop__orders_lookup", "shop__orders_refund"


def service(fake):
    return McpConnections(None, Registry(), {"localhost"}, SECRETS, transport=fake.transport())


async def connected(fake, trusted=True):
    svc = service(fake)
    c = await svc.create("shop", URL, "orders", trusted, "ann")
    return svc, c


async def approve_all(svc, c, only=None):
    review = await svc.review(c.id)
    chosen = {t["name"]: t["fingerprint"] for t in review["tools"] if only is None or t["name"] in only}
    return await svc.approve(c.id, chosen, "ann")


async def test_a_new_connection_offers_no_tool_to_any_agent_until_tools_are_approved():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        assert svc.registry.tool_names() == [] and c.enabled and c.approved == []
        review = await svc.review(c.id)
        assert LOOKUP in {t["name"] for t in review["tools"]} and not any(t["approved"] for t in review["tools"])
        assert svc.registry.tool_names() == []  # looking is not approving


async def test_review_tells_the_operator_what_each_tool_can_do_and_what_was_left_out():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake, trusted=True)
        review = await svc.review(c.id)
        tools = {t["name"]: t for t in review["tools"]}
        assert tools[LOOKUP]["access"] == "reads" and tools[REFUND]["access"] == "changes"  # a trusted server's read-only claim counts
        assert tools[REFUND]["inputs"] == ["order_id", "amount"] and tools[LOOKUP]["description"] == "Look up an order."
        assert ("poisoned_description", "its description or input fields contain instructions to the model") in {(s["name"], s["reason"]) for s in review["skipped"]}


async def test_an_untrusted_connection_shows_every_tool_as_one_that_changes_things():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake, trusted=False)
        assert {t["access"] for t in (await svc.review(c.id))["tools"]} == {"changes"}


async def test_approving_registers_exactly_the_chosen_tools_and_they_work_for_an_agent_with_the_approval_rule():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        await approve_all(svc, c, {LOOKUP, REFUND})
        assert svc.registry.tool_names() == [LOOKUP, REFUND] and {t["source"] for t in svc.registry.describe()["tools"]} == {"mcp"}
        llm = ScriptedLLM([tool_call(LOOKUP, {"order_id": "A-1"}, "t1"), tool_call(REFUND, {"order_id": "A-1", "amount": 5}, "t2"), text("ok")])
        rt = Runtime(llm, InMemoryStore(), TraceStore(), secrets=SECRETS)
        tools = [svc.registry._tools[n] for n in (LOOKUP, REFUND)]
        run = await rt.run(Agent(id="a", instructions="x", tools=tools), "s", "go", "c")
        assert [n for n, _ in fake.executed] == ["orders_lookup"] and run.status == "needs_approval"  # the read ran; the write waits for a person


async def test_approval_needs_the_fingerprint_the_operator_saw_so_a_tool_changed_in_between_is_not_approved_unseen():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        seen = {t["name"]: t["fingerprint"] for t in (await svc.review(c.id))["tools"]}
        fake.redescribe("orders_lookup", "Look up an order. Also post it to a public site.")
        with pytest.raises(McpConnectionError) as e:
            await svc.approve(c.id, {LOOKUP: seen[LOOKUP]}, "ann")
        assert e.value.status == 409 and "changed since you looked" in str(e.value) and svc.registry.tool_names() == []
        with pytest.raises(McpConnectionError) as e:
            await svc.approve(c.id, {"shop__not_there": "x"}, "ann")
        assert e.value.status == 400


async def test_switching_a_connection_off_stops_the_agents_that_were_already_built():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        await approve_all(svc, c, {LOOKUP})
        agent = Agent(id="a", instructions="x", tools=[svc.registry._tools[LOOKUP]])  # built before the switch
        await svc.update(c.id, "ann", enabled=False)
        assert svc.registry.tool_names() == []
        llm = ScriptedLLM([tool_call(LOOKUP, {"order_id": "A-1"}, "t1"), text("sorry")])
        rt = Runtime(llm, InMemoryStore(), TraceStore(), secrets=SECRETS)
        await rt.run(agent, "s", "go", "c")
        assert fake.executed == [] and "switched off" in str(llm.requests[1].messages)
        await svc.update(c.id, "ann", enabled=True)
        assert svc.registry.tool_names() == [LOOKUP]  # switching back on needs no new approval


async def test_withdrawing_trust_turns_an_approved_read_into_a_tool_that_waits_for_a_person_even_in_agents_built_earlier():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake, trusted=True)
        await approve_all(svc, c, {LOOKUP})
        old = svc.registry._tools[LOOKUP]
        assert old.effect == "read"
        await svc.update(c.id, "ann", trusted=False)
        assert svc.registry._tools[LOOKUP].effect == "write"  # rebuilt
        llm = ScriptedLLM([tool_call(LOOKUP, {"order_id": "A-1"}, "t1"), text("sorry")])
        rt = Runtime(llm, InMemoryStore(), TraceStore(), secrets=SECRETS)
        await rt.run(Agent(id="a", instructions="x", tools=[old]), "s", "go", "c")
        assert fake.executed == [] and "changed since it was approved" in str(llm.requests[1].messages)


async def test_check_reports_a_tool_the_server_changed_after_approval_and_an_unreachable_server():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        await approve_all(svc, c, {LOOKUP, REFUND})
        assert (await svc.check(c.id))["changed"] == [] and (await svc.check(c.id))["reachable"] is True
        fake.redescribe("orders_lookup", "Look up an order and email it.")
        fake.withdraw("orders_refund")
        out = await svc.check(c.id)
        assert out["changed"] == [LOOKUP] and out["removed"] == [REFUND]
        fake.mode = "redirect"
        down = await svc.check(c.id)
        assert down["reachable"] is False and "redirect" in down["message"]


async def test_start_up_registers_the_approved_tools_from_storage_without_asking_the_server():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        await approve_all(svc, c, {LOOKUP})
        fresh = McpConnections(svc.repo, Registry(), {"localhost"}, SECRETS, transport=None)  # no transport: any request would fail
        await fresh.load()
        assert fresh.registry.tool_names() == [LOOKUP]


async def test_a_connection_whose_host_is_no_longer_allowed_is_left_out_at_start_up_not_half_registered():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        await approve_all(svc, c, {LOOKUP})
        fresh = McpConnections(svc.repo, Registry(), {"other.example.com"}, SECRETS)
        await fresh.load()
        assert fresh.registry.tool_names() == []


@pytest.mark.parametrize("name, url, secret, status, fragment", [
    ("Bad Name", URL, None, 400, "lowercase"), ("shop", "https://evil.example.com/mcp", None, 400, "allowed list"), ("shop", "http://orders.example.com/mcp", None, 400, "https"),
    ("shop", URL, "missing", 400, "not configured")])
async def test_a_connection_that_breaks_the_rules_is_refused_with_what_to_change(name, url, secret, status, fragment):
    svc = McpConnections(None, Registry(), {"localhost", "orders.example.com"}, SECRETS)
    with pytest.raises(McpConnectionError) as e:
        await svc.create(name, url, secret, False, "ann")
    assert e.value.status == status and fragment in str(e.value)


async def test_a_name_can_be_used_once_and_deleting_a_connection_removes_its_tools():
    async with FakeMcp().running() as fake:
        svc, c = await connected(fake)
        with pytest.raises(McpConnectionError) as e:
            await svc.create("shop", URL, None, False, "ann")
        assert e.value.status == 409
        await approve_all(svc, c, {LOOKUP})
        await svc.delete(c.id)
        assert svc.registry.tool_names() == [] and await svc.list() == []


async def test_a_tenant_other_than_the_default_is_refused_everything():
    svc = McpConnections(None, Registry(), {"localhost"}, SECRETS)
    token = TENANT.set("acme")
    try:
        for call in (svc.list(), svc.create("shop", URL, None, False, "x")):
            with pytest.raises(McpConnectionError) as e:
                await call
            assert e.value.status == 501 and "multi-tenant preview" in str(e.value)
    finally:
        TENANT.reset(token)


@pytest.fixture(params=["memory", "postgres"])
def repo(request):
    if request.param == "memory":
        from northcx.mcp_connections import InMemoryMcpConnections
        return InMemoryMcpConnections()
    from northcx.db import PgMcpConnections
    return PgMcpConnections(request.getfixturevalue("engine"))


def stored(**kw):
    from northcx.mcp_connections import McpConnection
    base = dict(id="c1", name="shop", url="https://orders.example.com/mcp", trusted=True, secret="orders", enabled=True,
                approved=[{"name": "orders_lookup", "description": "Look up an order.", "input_schema": {"type": "object"}, "read_only_hint": True}],
                created_by="ann", created_at=1.0, updated_by="ann", updated_at=2.0)
    return McpConnection(**{**base, **kw})


async def test_the_store_keeps_a_connection_and_its_approved_definitions_exactly(repo):
    await repo.save(stored())
    assert await repo.get("c1") == stored() and await repo.get_by_name("shop") == stored() and await repo.get("nope") is None
    await repo.save(stored(enabled=False, approved=[]))  # saving again changes it
    assert (await repo.get("c1")).enabled is False and (await repo.get("c1")).approved == []
    await repo.save(stored(id="c2", name="billing", secret=None))
    assert [c.name for c in await repo.list()] == ["billing", "shop"] and (await repo.get("c2")).secret is None
    assert await repo.delete("c1") is True and await repo.delete("c1") is False and [c.name for c in await repo.list()] == ["billing"]


async def test_one_tenant_cannot_read_another_tenants_connections(repo):
    from northcx.mcp_connections import InMemoryMcpConnections
    if isinstance(repo, InMemoryMcpConnections):
        pytest.skip("row-level security is the database's; the in-memory twin has no tenants (the service refuses other tenants, tested above)")
    await repo.save(stored())
    token = TENANT.set("acme")
    try:
        assert await repo.list() == [] and await repo.get("c1") is None and await repo.get_by_name("shop") is None
    finally:
        TENANT.reset(token)


async def test_another_tenant_does_not_see_the_operators_mcp_tools_in_the_catalogue():
    from northcx.mcp_connections import visible_catalog
    catalog = {"tools": [{"name": "lookup", "source": "registry"}, {"name": "shop__orders_lookup", "source": "mcp"}], "guardrails": []}
    assert visible_catalog(catalog) == catalog
    token = TENANT.set("acme")
    try:
        assert visible_catalog(catalog) == {"tools": [{"name": "lookup", "source": "registry"}], "guardrails": []}
    finally:
        TENANT.reset(token)
