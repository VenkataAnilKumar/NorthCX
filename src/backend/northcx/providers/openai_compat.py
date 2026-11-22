"""Any server that speaks the OpenAI chat-completions protocol: hosted services, vLLM, Ollama, llama.cpp, LM Studio and gateways.

Claude-style blocks go in and come out (northcx/types.py); this adapter translates at its edge. The API key goes in a header, never the
URL or body, and never appears in an error. Plain http is refused unless the operator says the address is on a trusted network."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx

from northcx.providers.base import Capabilities, Price, ProviderError, ProviderTimeout, ProviderUnreachable
from northcx.types import LLMRequest, LLMResponse

_FINISH = {"stop": "end_turn", "tool_calls": "tool_use", "function_call": "tool_use", "length": "max_tokens"}


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def _tool_result_text(content: Any) -> str:
    return _text_of(content) if not isinstance(content, str) else content


def to_openai_messages(system: str, messages: list[dict[str, Any]], images: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})}}
                     for b in content if b.get("type") == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": _text_of(content)}      # an empty string, not null: the API allows either, and some local servers (llama-cpp-python) refuse null
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        parts: list[dict[str, Any]] = []
        for b in content:
            kind = b.get("type")
            if kind == "tool_result":  # each result is its own `tool` message, placed before any new user text
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": _tool_result_text(b.get("content", ""))})
            elif kind == "text":
                parts.append({"type": "text", "text": b.get("text", "")})
            elif kind == "image":
                if not images:
                    raise ProviderError("this model does not accept images")
                src = b.get("source", {})
                if src.get("type") != "base64":
                    raise ProviderError("only base64 images can be sent to this model")
                parts.append({"type": "image_url", "image_url": {"url": f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}"}})
        if parts:
            out.append({"role": "user", "content": parts if any(p["type"] != "text" for p in parts) else "".join(p["text"] for p in parts)})
    return out


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}}
            for t in tools]


class OpenAICompatibleLLM:
    """A model reached through `POST {base_url}/chat/completions`."""

    def __init__(self, name: str, base_url: str, default_model: str | None = None, api_key: str | None = None,
                 capabilities: Capabilities | None = None, prices: dict[str, Price] | None = None, timeout: float = 60.0,
                 allow_insecure_http: bool = False, max_tokens_param: str = "max_tokens", client: httpx.AsyncClient | None = None):
        base = base_url.rstrip("/")
        u = urlsplit(base)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("the base URL must be an http or https address")
        if u.scheme == "http" and not allow_insecure_http and u.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("the base URL must be https (set allowInsecureHttp only for a trusted private network)")
        if u.username or u.password:
            raise ValueError("put the key in api_key_env or api_key_file, not in the URL")
        self.name, self.default_model = name, default_model
        self.capabilities = capabilities or Capabilities(tools=True, parallel_tools=True, images=False)
        self.prices = dict(prices or {})
        self._url, self._key, self._max_param = f"{base}/chat/completions", api_key, max_tokens_param
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def complete(self, req: LLMRequest) -> LLMResponse:
        model = req.model or self.default_model
        if not model:
            raise ProviderError(f"provider '{self.name}' has no default model and none was named")
        if req.tools and not self.capabilities.tools:
            raise ProviderError(f"model '{self.name}:{model}' cannot call tools")
        body: dict[str, Any] = {"model": model, self._max_param: req.max_tokens, "messages": to_openai_messages(req.system, req.messages, self.capabilities.images)}
        if req.tools:
            body["tools"] = to_openai_tools(req.tools)
            body["tool_choice"] = "auto"           # the API's own default, said out loud: some local servers (llama-cpp-python) ignore the tools unless it is present
        headers = {"authorization": f"Bearer {self._key}"} if self._key else {}
        try:
            r = await self._client.post(self._url, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderTimeout("the model call timed out") from e
        except httpx.HTTPError as e:
            raise ProviderUnreachable(f"the model could not be reached ({type(e).__name__})") from e
        if r.status_code >= 300:
            try:
                err = r.json().get("error")
                detail = str(err.get("message", "") if isinstance(err, dict) else err or "")[:200]
            except Exception:
                detail = ""
            raise ProviderError(f"the model service answered {r.status_code}" + (f": {detail}" if detail else ""), r.status_code)
        try:
            data = r.json()
            choice = data["choices"][0]
            msg = choice["message"]
        except Exception as e:
            raise ProviderError("the model service returned an unexpected answer") from e
        blocks: list[dict[str, Any]] = []
        if msg.get("content"):
            blocks.append({"type": "text", "text": msg["content"]})
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError
            except ValueError as e:
                raise ProviderError("the model returned tool arguments that are not valid JSON") from e
            blocks.append({"type": "tool_use", "id": call.get("id") or f"call_{len(blocks)}", "name": fn.get("name", ""), "input": args})
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else _FINISH.get(choice.get("finish_reason") or "stop", "end_turn")
        u = data.get("usage") or {}
        usage = {"input_tokens": int(u.get("prompt_tokens") or 0), "output_tokens": int(u.get("completion_tokens") or 0)} if u else {}
        return LLMResponse(content=blocks, stop_reason=stop, usage=usage, model=data.get("model") or model)
