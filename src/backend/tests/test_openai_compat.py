"""WP1.3: the OpenAI-compatible provider against a fake server, and the providers file."""
import json

import httpx
import pytest

from northcx.providers import Capabilities, ProviderError, ProviderRegistry, ProviderTimeout, require_tools
from northcx.providers.config import parse_providers
from northcx.providers.openai_compat import OpenAICompatibleLLM
from northcx.reliability import is_transient
from northcx.secrets import ConfigError
from northcx.types import LLMRequest

KEY = "sk-local-test-0123456789"
TOOLS = [{"name": "lookup", "description": "d", "input_schema": {"type": "object", "properties": {"order": {"type": "string"}}}}]
REQ = LLMRequest(system="Be brief.", messages=[{"role": "user", "content": "hi"}], tools=TOOLS, model="m1", max_tokens=200)


def reply(message, finish="stop", usage=(11, 7), model="m1"):
    return {"id": "c1", "object": "chat.completion", "model": model, "choices": [{"index": 0, "message": {"role": "assistant", **message}, "finish_reason": finish}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}


def make(handler, **kw):
    kw.setdefault("api_key", KEY)
    return OpenAICompatibleLLM("local", "https://llm.example.com/v1", "m1", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


async def test_a_plain_reply_with_usage_and_the_answering_model():
    seen = []

    def handler(req):
        seen.append((str(req.url), req.headers.get("authorization"), json.loads(req.content)))
        return httpx.Response(200, json=reply({"content": "Hello"}))
    res = await make(handler).complete(REQ)
    assert res.content == [{"type": "text", "text": "Hello"}] and res.stop_reason == "end_turn" and res.model == "m1"
    assert res.usage == {"input_tokens": 11, "output_tokens": 7}
    url, auth, body = seen[0]
    assert url == "https://llm.example.com/v1/chat/completions" and auth == f"Bearer {KEY}"
    assert body["messages"][0] == {"role": "system", "content": "Be brief."} and body["max_tokens"] == 200 and body["tools"][0]["function"]["name"] == "lookup" and body["tool_choice"] == "auto"
    assert KEY not in json.dumps(body) and KEY not in url


async def test_a_tool_call_and_the_tool_result_round_trip():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        if len(bodies) == 1:
            return httpx.Response(200, json=reply({"content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": '{"order": "1042"}'}}]}, finish="tool_calls"))
        return httpx.Response(200, json=reply({"content": "Order 1042 shipped."}))
    llm = make(handler)
    first = await llm.complete(REQ)
    assert first.stop_reason == "tool_use" and first.content == [{"type": "tool_use", "id": "call_1", "name": "lookup", "input": {"order": "1042"}}]
    history = REQ.messages + [{"role": "assistant", "content": first.content}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "shipped"}]}]
    second = await llm.complete(LLMRequest(system=REQ.system, messages=history, tools=TOOLS, model="m1"))
    assert second.content[0]["text"] == "Order 1042 shipped."
    sent = bodies[1]["messages"]
    assert sent[2]["tool_calls"][0]["function"]["arguments"] == '{"order": "1042"}' and sent[3] == {"role": "tool", "tool_call_id": "call_1", "content": "shipped"}
    assert sent[2]["content"] == ""                   # an assistant turn that only called a tool carries an empty string, not null: llama-cpp-python rejects null (found in the first local-model pass)


async def test_several_tool_results_and_a_stop_reason_of_length():
    def handler(req):
        return httpx.Response(200, json=reply({"content": "cut"}, finish="length"))
    msgs = [{"role": "user", "content": "x"}, {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "lookup", "input": {}}, {"type": "tool_use", "id": "b", "name": "lookup", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": [{"type": "text", "text": "A"}]}, {"type": "tool_result", "tool_use_id": "b", "content": "B"}]}]
    seen = []
    llm = make(lambda r: (seen.append(json.loads(r.content)), handler(r))[1])
    res = await llm.complete(LLMRequest(system="", messages=msgs, tools=TOOLS, model="m1"))
    assert res.stop_reason == "max_tokens"
    roles = [m["role"] for m in seen[0]["messages"]]
    assert roles == ["user", "assistant", "tool", "tool"] and seen[0]["messages"][2]["content"] == "A"


async def test_no_tools_means_none_are_sent_and_a_toolless_model_refuses_tools():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=reply({"content": "ok"}))
    await make(handler).complete(LLMRequest(system="s", messages=[{"role": "user", "content": "x"}], model="m1"))
    assert "tools" not in seen[0] and "tool_choice" not in seen[0]            # with no tools there is nothing to choose
    with pytest.raises(ProviderError, match="cannot call tools"):
        await make(handler, capabilities=Capabilities(tools=False)).complete(REQ)


@pytest.mark.parametrize("status,transient", [(429, True), (500, True), (503, True), (400, False), (401, False), (404, False)])
async def test_errors_carry_the_status_and_never_the_key(status, transient):
    def handler(req):
        return httpx.Response(status, json={"error": {"message": "nope"}})
    with pytest.raises(ProviderError) as e:
        await make(handler).complete(REQ)
    assert e.value.status_code == status and is_transient(e.value) is transient and KEY not in str(e.value)


async def test_timeouts_drops_and_bad_answers():
    def slow(req):
        raise httpx.ReadTimeout("slow", request=req)

    def dropped(req):
        raise httpx.ConnectError("refused", request=req)
    with pytest.raises(ProviderTimeout):
        await make(slow).complete(REQ)
    with pytest.raises(ConnectionError) as c:
        await make(dropped).complete(REQ)
    assert is_transient(c.value) and "refused" not in str(c.value)
    with pytest.raises(ProviderError, match="unexpected"):
        await make(lambda r: httpx.Response(200, json={"nope": 1})).complete(REQ)
    bad = reply({"content": None, "tool_calls": [{"id": "c", "type": "function", "function": {"name": "lookup", "arguments": "{not json"}}]}, finish="tool_calls")
    with pytest.raises(ProviderError, match="not valid JSON"):
        await make(lambda r: httpx.Response(200, json=bad)).complete(REQ)


async def test_images_only_when_the_model_accepts_them():
    msg = [{"role": "user", "content": [{"type": "text", "text": "what is this"}, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}]}]
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=reply({"content": "a dot"}))
    with pytest.raises(ProviderError, match="images"):
        await make(handler).complete(LLMRequest(system="", messages=msg, model="m1"))
    await make(handler, capabilities=Capabilities(images=True)).complete(LLMRequest(system="", messages=msg, model="m1"))
    assert seen[0]["messages"][0]["content"][1]["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_address_rules():
    c = lambda url, **kw: OpenAICompatibleLLM("x", url, "m", **kw)  # noqa: E731
    with pytest.raises(ValueError, match="https"):
        c("http://llm.internal:8000/v1")
    c("http://llm.internal:8000/v1", allow_insecure_http=True)
    c("http://localhost:11434/v1")
    with pytest.raises(ValueError, match="not in the URL"):
        c("https://user:pw@llm.example.com/v1")
    with pytest.raises(ValueError):
        c("ftp://x")


async def test_it_works_inside_the_registry_with_qualified_names():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content)["model"])
        return httpx.Response(200, json=reply({"content": "ok"}))
    reg = ProviderRegistry()
    reg.register(make(handler), default=True)
    r = await reg.complete(LLMRequest(system="", messages=[{"role": "user", "content": "x"}], model="local:llama3.1:8b"))
    assert seen == ["llama3.1:8b"] and r.provider == "local"
    require_tools(reg, "local:llama3.1:8b", True)


# ---------- providers file ----------
GOOD = """
providers:
  - name: local
    type: openai-compatible
    baseUrl: http://ollama:11434/v1
    allowInsecureHttp: true
    apiKeyEnv: LOCAL_KEY
    defaultModel: llama3.1:8b
    default: true
    where: local
    capabilities: {tools: true, images: false, maxContextTokens: 128000}
    prices: {"llama3.1:8b": {inputPerMillion: 0, outputPerMillion: 0, currency: eur}}
"""


def test_the_providers_file_builds_providers_and_never_takes_a_key_inline():
    [e] = parse_providers(GOOD, env={"LOCAL_KEY": KEY})
    assert e.provider.name == "local" and e.default and e.where == "local" and e.provider.capabilities.max_context_tokens == 128000
    assert e.provider.prices["llama3.1:8b"].currency == "EUR"
    with pytest.raises(ConfigError, match="never put a key"):
        parse_providers(GOOD.replace("apiKeyEnv: LOCAL_KEY", "apiKey: sk-x"), env={})
    with pytest.raises(ConfigError, match="LOCAL_KEY is not set"):
        parse_providers(GOOD, env={})


@pytest.mark.parametrize("edit,message", [
    (("where: local", "where: moon"), "where must be"),
    (("type: openai-compatible", "type: other"), "type must be"),
    (("    default: true\n", "    default: true\n    colour: red\n"), "unknown setting"),
    (("    allowInsecureHttp: true\n", ""), "must be https"),
    (("inputPerMillion: 0, ", ""), "inputPerMillion"),
])
def test_the_providers_file_refuses_mistakes_with_a_reason(edit, message):
    with pytest.raises(ConfigError, match=message):
        parse_providers(GOOD.replace(*edit), env={"LOCAL_KEY": KEY})
    with pytest.raises(ConfigError, match="non-empty"):
        parse_providers("providers: []")
    with pytest.raises(ConfigError, match="only one"):
        parse_providers(GOOD + GOOD.split("providers:")[1].replace("name: local", "name: two"), env={"LOCAL_KEY": KEY})
