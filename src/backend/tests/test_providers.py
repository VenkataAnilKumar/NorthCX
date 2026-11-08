"""WP1.1 and WP1.2: the provider layer, and one conformance suite run over both Claude clients (the SDK and direct HTTPS)."""
import json

import httpx
import pytest

from northcx.llm import AnthropicHttpLLM, AnthropicLLM, ScriptedLLM, text
from northcx.providers import Capabilities, Price, ProviderError, ProviderRegistry, ProviderTimeout, UnknownModel, require_tools
from northcx.reliability import is_transient
from northcx.types import LLMRequest, LLMResponse

KEY = "sk-ant-test-0123456789"


def message(content, stop="end_turn", model="claude-test", usage=(11, 7)):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": content, "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1]}}


def make_sdk(handler):
    """The SDK ships its own HTTP library (httpx2), so the same handlers are adapted to it."""
    import httpx2
    from anthropic import AsyncAnthropic

    def adapted(req):
        res = handler(req)
        return httpx2.Response(res.status_code, content=res.content, headers={"content-type": "application/json"})
    return AnthropicLLM(client=AsyncAnthropic(api_key=KEY, max_retries=0, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(adapted))))


def make_http(handler):
    return AnthropicHttpLLM(KEY, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.fixture(params=["sdk", "http"])
def client(request):
    return make_sdk if request.param == "sdk" else make_http


REQ = LLMRequest(system="Be brief.", messages=[{"role": "user", "content": "hi"}], tools=[{"name": "lookup", "description": "d", "input_schema": {"type": "object", "properties": {}}}],
                 model="claude-test", max_tokens=200)


async def test_a_plain_reply_with_usage_and_the_answering_model(client):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=message([{"type": "text", "text": "Hello"}]))
    res = await client(handler).complete(REQ)
    assert res.content == [{"type": "text", "text": "Hello"}] and res.stop_reason == "end_turn" and res.model == "claude-test"
    assert res.usage == {"input_tokens": 11, "output_tokens": 7}
    sent = seen[0]
    assert sent["model"] == "claude-test" and sent["system"] == "Be brief." and sent["max_tokens"] == 200 and sent["tools"][0]["name"] == "lookup"


async def test_a_tool_call_and_the_tool_result_round_trip(client):
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        if len(bodies) == 1:
            return httpx.Response(200, json=message([{"type": "tool_use", "id": "tu_1", "name": "lookup", "input": {"order": "1042"}}], stop="tool_use"))
        return httpx.Response(200, json=message([{"type": "text", "text": "Order 1042 shipped."}]))
    llm = client(handler)
    first = await llm.complete(REQ)
    assert first.stop_reason == "tool_use" and first.content[0]["name"] == "lookup" and first.content[0]["input"] == {"order": "1042"}
    history = REQ.messages + [{"role": "assistant", "content": first.content}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "shipped"}]}]
    second = await llm.complete(LLMRequest(system=REQ.system, messages=history, tools=REQ.tools, model="claude-test"))
    assert second.content[0]["text"] == "Order 1042 shipped."
    assert bodies[1]["messages"][-1]["content"][0] == {"type": "tool_result", "tool_use_id": "tu_1", "content": "shipped"}


async def test_no_tools_means_none_are_sent(client):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=message([{"type": "text", "text": "ok"}]))
    await client(handler).complete(LLMRequest(system="s", messages=[{"role": "user", "content": "x"}], model="claude-test"))
    assert "tools" not in seen[0]


@pytest.mark.parametrize("status,transient", [(429, True), (500, True), (529, True), (400, False), (401, False), (404, False)])
async def test_errors_carry_the_status_so_retry_decisions_are_right(client, status, transient):
    def handler(req):
        return httpx.Response(status, json={"type": "error", "error": {"type": "x", "message": "nope"}})
    with pytest.raises(Exception) as e:
        await client(handler).complete(REQ)
    assert getattr(e.value, "status_code", None) == status and is_transient(e.value) is transient
    assert KEY not in str(e.value) and KEY not in repr(e.value)  # a key never appears in an error


async def test_a_timeout_or_dropped_connection_is_transient():
    def slow(req):
        raise httpx.ReadTimeout("slow", request=req)

    def dropped(req):
        raise httpx.ConnectError("refused", request=req)
    with pytest.raises(ProviderTimeout) as t:
        await make_http(slow).complete(REQ)
    assert is_transient(t.value)
    with pytest.raises(ConnectionError) as c:
        await make_http(dropped).complete(REQ)
    assert is_transient(c.value) and "refused" not in str(c.value)


def test_the_http_client_refuses_a_plain_http_address_and_a_missing_key():
    with pytest.raises(ValueError, match="https"):
        AnthropicHttpLLM(KEY, base_url="http://example.com")
    with pytest.raises(ValueError, match="API key"):
        AnthropicHttpLLM("")
    AnthropicHttpLLM(KEY, base_url="http://localhost:9999")  # allowed for local testing


async def test_the_key_goes_in_a_header_not_the_body_or_url():
    seen = []

    def handler(req):
        seen.append((str(req.url), req.headers.get("x-api-key"), req.headers.get("anthropic-version"), req.content))
        return httpx.Response(200, json=message([{"type": "text", "text": "ok"}]))
    await make_http(handler).complete(REQ)
    url, key, version, body = seen[0]
    assert url == "https://api.anthropic.com/v1/messages" and key == KEY and version and KEY.encode() not in body and KEY not in url


# ---------- registry ----------
class Fake:
    def __init__(self, name, model="m1", tools=True, answer="from-fake"):
        self.name, self.default_model, self.capabilities, self.prices, self.answer, self.seen = name, model, Capabilities(tools=tools), {model: Price(1.0, 2.0)}, answer, []

    async def complete(self, req):
        self.seen.append(req.model)
        return LLMResponse(content=[{"type": "text", "text": self.answer}], model=req.model or self.default_model)


async def test_qualified_names_pick_the_provider_and_bare_names_use_the_default():
    a, b = Fake("alpha", answer="A"), Fake("beta", answer="B")
    reg = ProviderRegistry()
    reg.register(a, default=True)
    reg.register(b)
    req = lambda m: LLMRequest(system="", messages=[], model=m)  # noqa: E731
    assert (await reg.complete(req("beta:big-model"))).content[0]["text"] == "B" and b.seen == ["big-model"]
    r = await reg.complete(req("plain-model"))
    assert r.content[0]["text"] == "A" and a.seen == ["plain-model"] and r.provider == "alpha"  # a bare name goes to the default provider, unchanged
    assert (await reg.complete(req(None))).provider == "alpha" and a.seen[-1] is None  # no model: the provider's own default
    assert (await reg.complete(req("llama3:8b"))).provider == "alpha" and a.seen[-1] == "llama3:8b"  # a colon in a model name is not a provider prefix
    assert reg.qualify("beta:x") == "beta:x" and reg.qualify("plain") == "alpha:plain" and reg.qualify(None) == "alpha:m1"
    with pytest.raises(UnknownModel):
        reg.resolve("beta:")


def test_registration_rules_and_capability_checks():
    reg = ProviderRegistry()
    with pytest.raises(UnknownModel):
        reg.default  # noqa: B018
    reg.register(Fake("alpha"))
    with pytest.raises(ValueError, match="already"):
        reg.register(Fake("alpha"))
    for bad in ("", "a:b", "has space"):
        with pytest.raises(ValueError):
            reg.register(Fake(bad))
    reg.register(Fake("notools", tools=False))
    require_tools(reg, "alpha:x", True)
    require_tools(reg, "notools:x", False)
    with pytest.raises(ProviderError, match="cannot call tools"):
        require_tools(reg, "notools:x", True)
    info = reg.info("alpha:m1")
    assert info.provider == "alpha" and info.price == Price(1.0, 2.0) and info.price.cost(1_000_000, 500_000) == 2.0


async def test_the_registry_is_a_drop_in_for_any_llm_user():
    from northcx.reliability import ReliableLLM
    reg = ProviderRegistry()
    reg.register(Fake("alpha"), default=True)
    rel = ReliableLLM(reg, ["alpha:m1"], retries=0)
    assert (await rel.complete(LLMRequest(system="", messages=[], model=None))).content[0]["text"] == "from-fake"
    assert ScriptedLLM([text("x")]) is not None  # the scripted model still satisfies the same interface
