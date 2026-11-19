"""The MCP client wrapper (Phase 2, WP 2.1): what it refuses before connecting, how it treats a misbehaving server, and that failures read plainly."""
import json

import httpx2
import pytest

from northcx.access import RateLimiter
from northcx.mcp_client import McpClient, McpError
from northcx.secrets import SecretStore
from tests.mcp_fake import SECRET, URL, FakeMcp

HOSTS = {"localhost"}
SECRETS = SecretStore({"orders": SECRET})


@pytest.fixture
def fake():
    return FakeMcp()  # each test enters `async with fake.running():` (the server's task group must start and stop in the test's own task)


def client(fake, **kw):
    kw.setdefault("secret", "orders")
    return McpClient("orders", URL, HOSTS, transport=fake.transport(), **kw)


async def test_lists_tools_with_their_schema_and_the_servers_read_only_claim(fake):
    async with fake.running():
        tools = {t.name: t for t in await client(fake).list_tools(SECRETS)}
        assert set(tools) == {"orders_lookup", "orders_refund", "asks_a_question"}
        assert tools["orders_lookup"].read_only_hint is True and tools["orders_refund"].read_only_hint is None
        assert tools["orders_refund"].input_schema["properties"]["amount"]["type"] == "number" and tools["orders_refund"].description == "Refund an order."


async def test_a_call_returns_the_servers_answer(fake):
    async with fake.running():
        out = await client(fake).call_tool("orders_lookup", {"order_id": "A-1"}, SECRETS)
        assert json.loads(out["text"]) == {"id": "A-1", "note": "fine"}  # a tool with no declared output shape answers in text


async def test_the_credential_is_looked_up_when_the_call_is_made_and_sent_as_a_bearer_token(fake):
    async with fake.running():
        await client(fake).call_tool("orders_lookup", {"order_id": "A-1"}, SECRETS)
        assert {auth for _, _, auth in fake.requests} == {f"Bearer {SECRET}"}


async def test_a_missing_credential_fails_before_any_request_and_never_shows_a_value(fake):
    async with fake.running():
        with pytest.raises(McpError) as e:
            await client(fake).call_tool("orders_lookup", {"order_id": "A-1"}, SecretStore())
        assert "not configured" in str(e.value) and fake.requests == []


async def test_a_server_that_refuses_the_credential_gives_a_plain_message_without_the_address_or_token(fake):
    async with fake.running():
        fake.token = "another-token-0123456789"
        with pytest.raises(McpError) as e:
            await client(fake).list_tools(SECRETS)
        text = str(e.value)
        assert "orders" in text and SECRET not in text and "localhost" not in text and "http" not in text


@pytest.mark.parametrize("url, why", [("https://other.example.com/mcp", "allowed list"), ("http://orders.example.com/mcp", "https"),
                                     ("https://user:pw@localhost/mcp", "user name or password"), ("ftp://localhost/mcp", "https")])
def test_an_address_that_breaks_the_operators_rules_is_refused_before_connecting(url, why):
    with pytest.raises(McpError) as e:
        McpClient("orders", url, {"localhost", "orders.example.com"} if "orders.example" in url else HOSTS)
    assert why in str(e.value)


async def test_a_redirect_is_never_followed(fake):
    async with fake.running():
        fake.mode = "redirect"
        with pytest.raises(McpError) as e:
            await client(fake).list_tools(SECRETS)
        assert "redirect" in str(e.value) and {p for _, p, _ in fake.requests} == {"/mcp"}  # the target of the redirect was never requested


async def test_a_slow_server_times_out_with_a_message_for_the_reader(fake):
    async with fake.running():
        fake.mode = "slow"
        with pytest.raises(McpError) as e:
            await client(fake, timeout=0.2).call_tool("orders_lookup", {"order_id": "A-1"}, SECRETS)
        assert "did not answer in time" in str(e.value)


async def test_an_answer_over_the_size_cap_is_refused_not_cut(fake):
    async with fake.running():
        fake.big = 5000
        with pytest.raises(McpError) as e:
            await client(fake, max_result_bytes=1000).call_tool("orders_lookup", {"order_id": "A-1"}, SECRETS)
        assert "larger than" in str(e.value)


async def test_calls_over_the_rate_limit_are_refused_with_when_to_retry(fake):
    async with fake.running():
        c = client(fake, calls_per_minute=2, limiter=RateLimiter())
        for _ in range(2):
            await c.call_tool("orders_lookup", {"order_id": "A-1"}, SECRETS)
        with pytest.raises(McpError) as e:
            await c.call_tool("orders_lookup", {"order_id": "A-1"}, SECRETS)
        assert "Too many calls" in str(e.value) and "seconds" in str(e.value)
        assert [m for m, _, _ in fake.requests].count("POST") < 8


async def test_a_server_that_cannot_be_reached_gives_a_plain_message_without_the_address():
    def down(request):
        raise httpx2.ConnectError("refused", request=request)
    c = McpClient("orders", URL, HOSTS, transport=httpx2.MockTransport(down))
    with pytest.raises(McpError) as e:
        await c.list_tools()
    assert "could not be reached" in str(e.value) and "localhost" not in str(e.value)


async def test_a_server_that_wants_the_user_to_answer_something_is_a_failure_not_a_hang(fake):
    async with fake.running():
        with pytest.raises(McpError):
            await client(fake).call_tool("asks_a_question", {}, SECRETS)


@pytest.mark.parametrize("mode, server_mode", [("auto", "normal"), ("legacy", "normal"), ("auto", "legacy_only")])
async def test_both_protocol_eras_work(fake, mode, server_mode):
    async with fake.running():
        fake.mode = server_mode
        out = await client(fake, mode=mode).call_tool("orders_lookup", {"order_id": "A-1"}, SECRETS)
        assert json.loads(out["text"])["id"] == "A-1"
