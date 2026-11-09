"""Staff guardrails (WP5.7): which tools each role's assistant may be given, which model it runs on, and how much one tool call may return.

```yaml
model: "local:llama3.1:8b"          # the model staff assistants use (default: the server's default)
maxItemsPerCall: 25                  # most rows any one tool call may return (volume limit)
roles:                               # tools a role's assistant may have; a role not listed gets every tool its permissions allow
  viewer: [search_knowledge, list_handoffs]
  auditor: [search_conversations, get_conversation, insights_overview]
```
The policy only narrows. It never gives a tool the person's permissions do not allow, and a tool name that does not exist is refused when the file is read.
Every tool call is already in the audit chain; this file adds the limits. There is no export tool yet, so the export rules in the design (mask by default,
volume thresholds that need an approval) are not built: today nothing can export, and the volume limit above caps what one call returns."""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from .secrets import ConfigError

ROLES = ("admin", "release_manager", "developer", "reviewer", "auditor", "viewer")


@dataclass
class StaffPolicy:
    model: str | None = None
    max_items: int = 50
    roles: dict[str, list[str]] = field(default_factory=dict)

    def allows(self, role: str, tool: str) -> bool:
        return role not in self.roles or tool in self.roles[role]


def parse_policy(text: str, known_tools: set[str]) -> StaffPolicy:
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"workspace policy file is not valid YAML: {e}") from e
    if not isinstance(doc, dict) or set(doc) - {"model", "maxItemsPerCall", "roles"}:
        raise ConfigError("workspace policy takes only model, maxItemsPerCall and roles")
    model = doc.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ConfigError("model must be a model name")
    n = doc.get("maxItemsPerCall", 50)
    if not isinstance(n, int) or not 1 <= n <= 200:
        raise ConfigError("maxItemsPerCall must be a whole number from 1 to 200")
    roles = doc.get("roles") or {}
    if not isinstance(roles, dict):
        raise ConfigError("roles must map a role to a list of tools")
    for role, tools in roles.items():
        if role not in ROLES:
            raise ConfigError(f"roles: unknown role '{role}' (roles: {', '.join(ROLES)})")
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            raise ConfigError(f"roles.{role} must be a list of tool names")
        bad = sorted(set(tools) - known_tools)
        if bad:
            raise ConfigError(f"roles.{role}: unknown tool(s) {', '.join(bad)} (tools: {', '.join(sorted(known_tools))})")
    return StaffPolicy(model.strip() if model else None, n, {r: list(t) for r, t in roles.items()})
