"""Tools from an MCP server as `Tool` objects (the second `ToolSource`, after the YAML connectors).

The server decides nothing about safety. A tool is a write, held for a person's approval, unless the operator marked the connection trusted and the
server says the tool only reads (decision 201: the specification says clients must treat annotations as untrusted unless the server is trusted).
Names are `<connection>__<tool>` so two servers can offer the same tool; the model API allows letters, digits, `_` and `-` up to 64 characters."""
from __future__ import annotations

import copy
import re
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, model_validator

from .agent import Tool, ToolContext
from .mcp_client import McpClient, McpToolInfo
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


class McpSource:
    label = "mcp"

    def __init__(self, connection: str, client: McpClient, *, trusted: bool = False, secrets: SecretStore = NO_SECRETS):
        if not CONNECTION_NAME.fullmatch(connection):
            raise ValueError("A connection name is 1 to 24 lowercase letters, digits or hyphens")
        self.connection, self.client, self.trusted, self.secrets = connection, client, trusted, secrets
        self.skipped: list[tuple[str, str]] = []  # (the server's tool name, why it is not offered)

    async def discover(self) -> list[Tool]:
        self.skipped = []
        tools = []
        for info in await self.client.list_tools(self.secrets):
            name = f"{self.connection}__{info.name}"
            if not TOOL_NAME.fullmatch(name):
                self.skipped.append((info.name, "its name does not fit (letters, digits, _ and - up to 64 characters with the connection name)"))
                continue
            tools.append(self._tool(name, info))
        return tools

    def _tool(self, name: str, info: McpToolInfo) -> Tool:
        reads = self.trusted and info.read_only_hint is True

        async def run(data: BaseModel, ctx: ToolContext) -> Any:
            return await self.client.call_tool(info.name, data.model_dump(), ctx.secrets)

        approval = None if reads else (lambda d, n=name, c=self.connection: f"{n} can change things in {c}")
        return Tool(name, info.description[:MAX_DESCRIPTION] or name, arguments_model(info.input_schema), run, requires_approval=approval, effect="read" if reads else "write")
