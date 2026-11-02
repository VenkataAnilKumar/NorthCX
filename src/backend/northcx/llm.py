from __future__ import annotations

import uuid
from typing import Callable, Union

from .types import LLM, LLMRequest, LLMResponse

DEFAULT_MODEL = "claude-sonnet-5-5"


class AnthropicLLM:
    """Claude backend using the official Anthropic SDK."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

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
        return LLMResponse(content=[b.model_dump() for b in res.content], stop_reason=res.stop_reason or "end_turn")


Script = Union[LLMResponse, Callable[[LLMRequest], LLMResponse]]


class ScriptedLLM:
    """Deterministic fake model for tests and simulations."""

    def __init__(self, script: list[Script]):
        self.script = list(script)
        self.requests: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        if not self.script:
            raise RuntimeError("ScriptedLLM: script exhausted")
        nxt = self.script.pop(0)
        return nxt(req) if callable(nxt) else nxt


def text(t: str) -> LLMResponse:
    return LLMResponse(content=[{"type": "text", "text": t}], stop_reason="end_turn")


def tool_call(name: str, input: dict, id: str | None = None) -> LLMResponse:
    return LLMResponse(
        content=[{"type": "tool_use", "id": id or f"tu_{uuid.uuid4().hex[:6]}", "name": name, "input": input}],
        stop_reason="tool_use",
    )
