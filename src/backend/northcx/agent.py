from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from .guardrails import Guardrail, InputGuardrail


@dataclass
class ToolContext:
    session_id: str
    customer_id: str | None
    memory: Any
    idempotency_key: str | None = None  # stable per approved action; tools should use it to deduplicate writes


@dataclass
class Tool:
    """A typed action. `requires_approval` returns a reason string to hold the call for a human."""

    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[..., Any] | Callable[..., Awaitable[Any]]
    requires_approval: Callable[[BaseModel], str | None] | None = None

    def spec(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}

    async def execute(self, data: BaseModel, ctx: ToolContext) -> Any:
        out = self.run(data, ctx)
        return await out if inspect.isawaitable(out) else out


@dataclass
class Agent:
    """Goals and policies in natural language, plus tools and guardrails."""

    id: str
    instructions: str
    tools: list[Tool] = field(default_factory=list)
    guardrails: list[Guardrail] = field(default_factory=list)
    input_guardrails: list[InputGuardrail] = field(default_factory=list)
    model: str | None = None
    max_steps: int = 8
