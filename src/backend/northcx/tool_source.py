"""Where a set of tools comes from. A source finds tools and returns them as `Tool` objects; it never applies approvals, scopes, dry-run or
secret handling, because the runtime applies those to every tool alike (docs/04-integrations/NorthCX_Tool-Gateway.md).

Two sources exist: YAML connector files (`YamlConnectorSource`) and MCP servers (`northcx/mcp_source.py`). `label` is the source name shown on each tool
and must be one of `spec.TOOL_SOURCES`; register what a source returns with `Registry.add_tools(source.label, await source.discover())`."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .agent import Tool
from .connectors import load_connectors


class ToolSource(Protocol):
    label: str

    async def discover(self) -> list[Tool]: ...


class YamlConnectorSource:
    """The connector files in a folder (or one file), limited to the hosts the operator allowed."""

    label = "connectors"

    def __init__(self, path: str | Path, allowed_hosts: set[str]):
        self.path, self.allowed_hosts = path, allowed_hosts

    async def discover(self) -> list[Tool]:
        return load_connectors(self.path, self.allowed_hosts)
