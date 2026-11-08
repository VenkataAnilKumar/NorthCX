"""Claude, in two interchangeable clients: the official SDK (default) and a direct HTTPS client (NORTHCX_ANTHROPIC_CLIENT=http).

This is the only module that imports the Anthropic SDK; a test fails if another one does. The neutral request and response shapes are
Claude's own, so this adapter is thin."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import httpx

from northcx.providers.base import Capabilities, Price, ProviderError, ProviderTimeout, ProviderUnreachable
from northcx.types import LLMRequest, LLMResponse

DEFAULT_MODEL = "claude-sonnet-5-5"
API_VERSION = "2023-06-01"
CAPABILITIES = Capabilities(tools=True, parallel_tools=True, images=True, documents=True)


def _usage(u: Any) -> dict[str, int]:
    get = (lambda k: u.get(k)) if isinstance(u, dict) else (lambda k: getattr(u, k, None))
    return {"input_tokens": int(get("input_tokens") or 0), "output_tokens": int(get("output_tokens") or 0)} if u else {}


class AnthropicLLM:
    """Claude through the official Anthropic SDK."""
    name = "anthropic"
    capabilities = CAPABILITIES

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL, client: Any = None, prices: dict[str, Price] | None = None):
        if client is None:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key)
        self._client = client
        self._model = model
        self.default_model = model
        self.prices = dict(prices or {})

    async def complete(self, req: LLMRequest) -> LLMResponse:
        kwargs = dict(
            model=req.model or self._model,
            max_tokens=req.max_tokens,
            system=req.system,
            messages=req.messages,
        )
        if req.tools:
            kwargs["tools"] = req.tools
        res = await self._client.messages.create(**kwargs)
        return LLMResponse(content=[b.model_dump(exclude_none=True) for b in res.content], stop_reason=res.stop_reason or "end_turn",
                           usage=_usage(getattr(res, "usage", None)), model=getattr(res, "model", None))


class AnthropicHttpLLM:
    """Claude's Messages API over HTTPS, without the SDK. Same neutral request and response; errors carry the HTTP status."""
    name = "anthropic"
    capabilities = CAPABILITIES

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, base_url: str | None = None, timeout: float = 60.0,
                 client: httpx.AsyncClient | None = None, prices: dict[str, Price] | None = None):
        if not api_key:
            raise ValueError("an API key is required")
        base = (base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
        u = urlsplit(base)
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1")):
            raise ValueError("the Anthropic base URL must be https")
        self._url, self._key, self.default_model = f"{base}/v1/messages", api_key, model
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        self.prices = dict(prices or {})

    async def complete(self, req: LLMRequest) -> LLMResponse:
        body: dict[str, Any] = {"model": req.model or self.default_model, "max_tokens": req.max_tokens, "system": req.system, "messages": req.messages}
        if req.tools:
            body["tools"] = req.tools
        try:
            r = await self._client.post(self._url, json=body, headers={"x-api-key": self._key, "anthropic-version": API_VERSION})
        except httpx.TimeoutException as e:
            raise ProviderTimeout("the model call timed out") from e
        except httpx.HTTPError as e:
            raise ProviderUnreachable(f"the model could not be reached ({type(e).__name__})") from e
        if r.status_code >= 300:
            try:
                detail = str((r.json().get("error") or {}).get("message", ""))[:200]
            except Exception:
                detail = ""
            raise ProviderError(f"the model service answered {r.status_code}" + (f": {detail}" if detail else ""), r.status_code)
        data = r.json()
        return LLMResponse(content=list(data.get("content", [])), stop_reason=data.get("stop_reason") or "end_turn",
                           usage=_usage(data.get("usage")), model=data.get("model"))
