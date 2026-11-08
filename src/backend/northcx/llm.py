from __future__ import annotations

import copy
import dataclasses
import uuid
from typing import Callable, Union

from .types import LLM, LLMRequest, LLMResponse

from .providers.anthropic import DEFAULT_MODEL, AnthropicHttpLLM, AnthropicLLM  # noqa: F401  (the adapters live in northcx/providers; re-exported here)


Script = Union[LLMResponse, Callable[[LLMRequest], LLMResponse]]


class ScriptedLLM:
    """Deterministic fake model for tests and simulations."""

    def __init__(self, script: list[Script]):
        self.script = list(script)
        self.requests: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(dataclasses.replace(req, messages=copy.deepcopy(req.messages)))  # as sent: the runtime keeps changing its own list
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
