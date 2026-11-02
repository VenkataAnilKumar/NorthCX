"""Message and model types. Blocks use the same dict shapes as the Claude Messages API."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

Block = dict[str, Any]  # {"type": "text"|"tool_use"|"tool_result", ...}
Message = dict[str, Any]  # {"role": "user"|"assistant", "content": str | list[Block]}


@dataclass
class LLMRequest:
    system: str
    messages: list[Message]
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    max_tokens: int = 1024


@dataclass
class LLMResponse:
    content: list[Block]
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)  # input_tokens, output_tokens when the backend reports them
    model: str | None = None  # the model that actually answered
    fallback: bool = False  # answered by a fallback model


class LLM(Protocol):
    """Any model backend. The runtime depends only on this interface."""

    async def complete(self, req: LLMRequest) -> LLMResponse: ...


def text_of(blocks: list[Block]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
