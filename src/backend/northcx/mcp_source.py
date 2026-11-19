"""Tools from an MCP server as `Tool` objects (the second `ToolSource`, after the YAML connectors).

The server decides nothing about safety. A tool is a write, held for a person's approval, unless the operator marked the connection trusted and the
server says the tool only reads (decision 201: the specification says clients must treat annotations as untrusted unless the server is trusted).
Names are `<connection>__<tool>` so two servers can offer the same tool; the model API allows letters, digits, `_` and `-` up to 64 characters."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, model_validator

from .agent import Tool, ToolContext, tool_fingerprint
from .mcp_client import McpClient, McpToolInfo
from .safety.tool_output import ToolOutputInjection
from .secrets import NO_SECRETS, SecretStore

CONNECTION_NAME = re.compile(r"[a-z0-9-]{1,24}")
TOOL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
MAX_DESCRIPTION = 1000


def arguments_model(schema: dict[str, Any]) -> type[BaseModel]:
    """A pass-through input model that checks arguments against the server's own JSON Schema and shows that schema, unchanged, to the model."""
    shown = copy.deepcopy(schema) if schema.get("type") else {**copy.deepcopy(schema), "type": "object"}
    validator = Draft202012Validator(shown)

    class Arguments(BaseModel):
        model_config = ConfigDict(extra="allow")

        @model_validator(mode="before")
        @classmethod
        def _check(cls, value: Any) -> Any:
            error = next(iter(validator.iter_errors(value)), None)
            if error is not None:
                where = ".".join(str(p) for p in error.absolute_path)
                raise ValueError(f"{where + ': ' if where else ''}{error.message}")
            return value

        @classmethod
        def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return copy.deepcopy(shown)

    return Arguments


def _strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


@dataclass
class ToolListChanges:
    """How what the server offers now differs from the list the operator approved. Nothing here is callable until the operator approves it again."""

    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)  # a name, description, input schema or read or write class differs from what was approved
    removed: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.added or self.changed or self.removed)


class McpSource:
    label = "mcp"

    def __init__(self, connection: str, client: McpClient, *, trusted: bool = False, secrets: SecretStore = NO_SECRETS,
                 approved: Mapping[str, str] | None = None, gate: Callable[[str, McpToolInfo, bool], Awaitable[None]] | None = None):
        """`approved` is the operator's pinned list: our tool name to its fingerprint. `discover` offers only tools that are on it and unchanged;
        with no list nothing is offered (a connection nobody has reviewed offers nothing), and `review` shows the operator what the server has.
        `gate`, when given, is awaited before every call with the tool's name, definition and trust, and refuses the call by raising `McpError`
        (a connection switched off, or a tool that is no longer the one approved, must stop agents that were built earlier)."""
        if not CONNECTION_NAME.fullmatch(connection):
            raise ValueError("A connection name is 1 to 24 lowercase letters, digits or hyphens")
        self.connection, self.client, self.trusted, self.secrets, self.approved = connection, client, trusted, secrets, dict(approved or {})
        self.skipped: list[tuple[str, str]] = []  # (the server's tool name, why it is not offered)
        self.changes = ToolListChanges()
        self.offered: dict[str, McpToolInfo] = {}  # our tool name to the server's definition of it, as of the last `review`
        self.gate = gate

    async def review(self) -> list[Tool]:
        """Everything the server offers now that could be used, for the operator to look at. None of it is callable until approved."""
        infos = await self.client.list_tools(self.secrets)
        tools = await self.tools_from(infos)
        offered = {t.name for t in tools}
        self.offered = {f"{self.connection}__{i.name}": i for i in infos if f"{self.connection}__{i.name}" in offered}
        return tools

    async def tools_from(self, infos: list[McpToolInfo]) -> list[Tool]:
        """Tools for these definitions, without asking the server (the operator's approved definitions are stored, so start-up needs no network)."""
        self.skipped = []
        tools = []
        screen = ToolOutputInjection()
        for info in infos:
            name = f"{self.connection}__{info.name}"
            if not TOOL_NAME.fullmatch(name):
                self.skipped.append((info.name, "its name does not fit (letters, digits, _ and - up to 64 characters with the connection name)"))
            elif not await self._clean(screen, name, info):
                self.skipped.append((info.name, "its description or input fields contain instructions to the model"))
            else:
                tools.append(self._tool(name, info))
        return tools

    @staticmethod
    async def _clean(screen: ToolOutputInjection, name: str, info: McpToolInfo) -> bool:
        """False when the description or any text in the input schema reads as an instruction to the model."""
        for text in _strings([info.description, info.input_schema]):
            if not (await screen.check_output(name, text)).allow:
                return False
        return True

    async def discover(self) -> list[Tool]:
        offered = {t.name: t for t in await self.review()}
        gone = {f"{self.connection}__{name}" for name, _ in self.skipped}  # on the server but no longer usable
        self.changes = ToolListChanges(
            added=sorted(n for n in offered if n not in self.approved),
            changed=sorted({n for n, t in offered.items() if n in self.approved and tool_fingerprint(t) != self.approved[n]} | (gone & set(self.approved))),
            removed=sorted(n for n in self.approved if n not in offered and n not in gone))
        return [t for n, t in offered.items() if self.approved.get(n) == tool_fingerprint(t)]

    def _tool(self, name: str, info: McpToolInfo) -> Tool:
        reads = self.trusted and info.read_only_hint is True

        async def run(data: BaseModel, ctx: ToolContext) -> Any:
            if self.gate is not None:
                await self.gate(name, info, self.trusted)
            return await self.client.call_tool(info.name, data.model_dump(), ctx.secrets)

        approval = None if reads else (lambda d, n=name, c=self.connection: f"{n} can change things in {c}")
        return Tool(name, info.description[:MAX_DESCRIPTION] or name, arguments_model(info.input_schema), run, requires_approval=approval, effect="read" if reads else "write",
                    untrusted_output=True)
