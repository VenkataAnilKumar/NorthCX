"""Message and model types. Blocks use the same dict shapes as the Claude Messages API."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol

# What the model chooser may know about the conversation being served; set by the runtime for the length of a turn, so the supervisor,
# summaries and assist calls made inside it are chosen by the same data rules. Empty means unknown, and the chooser then assumes sensitive.
MODEL_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("northcx_model_context", default=None)

Block = dict[str, Any]  # {"type": "text"|"tool_use"|"tool_result", ...}
Message = dict[str, Any]  # {"role": "user"|"assistant", "content": str | list[Block]}


@dataclass
class LLMRequest:
    system: str
    messages: list[Message]
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    max_tokens: int = 1024
    context: dict[str, Any] | None = None  # what the model chooser may use: agent, channel, sensitive, needs_tools, effect, language


@dataclass
class LLMResponse:
    content: list[Block]
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)  # input_tokens, output_tokens when the backend reports them
    model: str | None = None  # the model that actually answered
    fallback: bool = False  # answered by a fallback model
    provider: str | None = None  # which provider answered, when several are configured
    decision: dict[str, Any] | None = None  # why this model was chosen (rule, tier, models skipped), when a selector is in use


class LLM(Protocol):
    """Any model backend. The runtime depends only on this interface."""

    async def complete(self, req: LLMRequest) -> LLMResponse: ...


def text_of(blocks: list[Block]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
