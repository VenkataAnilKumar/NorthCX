"""What every model provider adapter provides: a neutral `complete`, declared capabilities, prices and errors that carry a status code.

The neutral request and response shapes are in northcx/types.py (Claude-style blocks: text, tool_use, tool_result). An adapter translates
at its edge; the runtime never sees a provider's own format."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from northcx.types import LLMRequest, LLMResponse


@dataclass(frozen=True)
class Capabilities:
    """What a model can do, so a configuration that cannot work is refused when it is saved, not discovered in a conversation."""
    tools: bool = True
    parallel_tools: bool = True
    images: bool = False
    documents: bool = False
    max_context_tokens: int | None = None


@dataclass(frozen=True)
class Price:
    """Money per million tokens. Prices are supplied by the operator (they change, and NorthCX does not guess them)."""
    input_per_million: float
    output_per_million: float
    currency: str = "USD"

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_million + output_tokens * self.output_per_million) / 1_000_000


class ProviderError(RuntimeError):
    """A provider call failed. `status_code` is the HTTP status when there was one, so retry and fallback decisions stay correct.
    The message never contains credentials or request bodies."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderTimeout(ProviderError, TimeoutError):
    pass


class ProviderUnreachable(ProviderError, ConnectionError):
    pass


class Provider(Protocol):
    name: str
    default_model: str | None
    capabilities: Capabilities
    prices: dict[str, Price]

    async def complete(self, req: LLMRequest) -> LLMResponse: ...


@dataclass
class ModelInfo:
    """What the platform knows about one qualified model name."""
    provider: str
    model: str
    capabilities: Capabilities
    price: Price | None = None
    extra: dict[str, str] = field(default_factory=dict)
