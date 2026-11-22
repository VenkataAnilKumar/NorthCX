from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from .guardrails import Guardrail, InputGuardrail, OutputGuardrail
from .handoffs import ForcedTopic
from .secrets import NO_SECRETS, SecretStore


@dataclass
class ToolContext:
    session_id: str
    customer_id: str | None
    memory: Any
    idempotency_key: str | None = None  # stable per approved action; tools should use it to deduplicate writes
    dry_run: bool = False  # true when the platform is testing: write tools are not executed (see Tool.effect)
    secrets: SecretStore = field(default=NO_SECRETS, repr=False)
    facts: dict[str, str] = field(default_factory=dict)  # what the company's systems and the platform report about this customer, for this turn (read only)
    actor: Any = None  # the signed-in person a staff conversation acts for (an access.Identity); None in customer conversations

    def secret(self, name: str) -> str:
        """A credential configured for tools (NORTHCX_SECRET_<NAME>). Never put it in a return value or a message."""
        return self.secrets.get(name)


@dataclass
class Tool:
    """A typed action. `requires_approval` returns a reason string to hold the call for a human."""

    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[..., Any] | Callable[..., Awaitable[Any]]
    requires_approval: Callable[[BaseModel], str | None] | None = None
    # "read" tools have no side effects and always run. "write" tools (the default, the safe assumption) are replaced by
    # `dry_run_result` (or a generic placeholder) when the platform is testing, so simulations never change real systems.
    effect: str = "write"
    dry_run_result: Callable[[BaseModel, ToolContext], Any] | None = None
    # Who the tool is for. A "staff" tool works with company data on behalf of a signed-in person and may be given only to staff agents; it runs only
    # when the actor holds `permission`, and acts with that person's rights, never more.
    audience: str = "customer"
    permission: str | None = None
    # Where the tool was registered from (see `Registry.add_tools`); shown in the catalogue and on each tool_call trace event.
    source: str = "registry"
    # True for a tool whose results and error text come from a system NorthCX does not control (an MCP server): the runtime then screens them for
    # instructions to the model even when the agent configured no output guardrail.
    untrusted_output: bool = False

    def __post_init__(self) -> None:
        if self.effect not in ("read", "write"):
            raise ValueError(f"Tool '{self.name}': effect must be 'read' or 'write', not {self.effect!r}")
        if self.audience not in ("customer", "staff"):
            raise ValueError(f"Tool '{self.name}': audience must be 'customer' or 'staff', not {self.audience!r}")
        if self.audience == "staff" and not self.permission:
            raise ValueError(f"Tool '{self.name}': a staff tool must name the permission it needs")

    def simulate(self, data: BaseModel, ctx: ToolContext) -> Any:
        if self.dry_run_result is not None:
            return self.dry_run_result(data, ctx)
        return {"dry_run": True, "would_run": self.name, "input": data.model_dump(mode="json")}

    def spec(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}

    async def execute(self, data: BaseModel, ctx: ToolContext) -> Any:
        out = self.run(data, ctx)
        return await out if inspect.isawaitable(out) else out


def tool_fingerprint(tool: Tool) -> str:
    """A SHA-256 of the tool's definition: name, description, input schema, effect, audience, permission and whether it needs approval.
    It changes when any of these change; it does not cover the code, the credentials or where the tool came from."""
    definition = {"name": tool.name, "description": tool.description, "input_schema": tool.spec()["input_schema"], "effect": tool.effect,
                  "audience": tool.audience, "permission": tool.permission, "approval": tool.requires_approval is not None}
    return hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass
class Agent:
    """Goals and policies in natural language, plus tools and guardrails."""

    id: str
    instructions: str
    tools: list[Tool] = field(default_factory=list)
    guardrails: list[Guardrail] = field(default_factory=list)
    input_guardrails: list[InputGuardrail] = field(default_factory=list)
    output_guardrails: list[OutputGuardrail] = field(default_factory=list)  # screen tool results before the model reads them
    forced_handoffs: list[ForcedTopic] = field(default_factory=list)  # topics that always go to a person
    version: int | None = None  # set when served from a released version
    digest: str | None = None
    model: str | None = None
    max_steps: int = 8
    channel_styles: dict[str, str] = field(default_factory=dict)  # per-channel writing style, e.g. {"sms": "Two short sentences"}
    attachments: list[str] = field(default_factory=list)  # kinds of attachment this agent accepts: image, pdf, text. Empty: none
    routes: list[Any] = field(default_factory=list)  # RouteSpec objects: specialists this agent may pass a conversation to
    journeys: list[Any] = field(default_factory=list)  # JourneySpec objects; progress through them is recorded on each trace
    languages: list[str] = field(default_factory=list)  # languages the agent supports; the first is the default. Empty: no language handling
    audience: str = "customer"  # "staff": works for a signed-in person with staff tools, never for customers
    always_approve: list[str] = field(default_factory=list)  # tools whose every call waits for a person (spec: approvals.always)
    shadow: bool = False  # shadow mode (shadow.py): the agent drafts, a person sends; nothing that changes something runs without a person
    sensitive: bool = False  # the administrator marked this agent sensitive: its conversations never use a tier the data policy forbids
    max_run_tokens: int | None = None  # stop and hand off when one turn has used this many model tokens
