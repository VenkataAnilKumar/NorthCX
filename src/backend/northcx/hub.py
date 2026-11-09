"""Agent Hub (E22, WP22.2 to WP22.4): requirements checks against the real deployment, install records, and updates that keep local changes visible.

Installing never makes an agent live: it creates a draft version, saves the template's scenarios and runs them, and the release gate and the
organization's release rules still decide what goes live. A template is placeholder-filled text and cannot execute anything."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .templates import Rendered, Template

CHANNEL_NAMES = ("web", "email", "sms", "whatsapp", "telegram", "voice")


@dataclass
class Install:
    agent_id: str
    template_id: str
    template_version: str
    params: dict[str, str]
    version_number: int
    installed_by: str
    spec_snapshot: dict[str, Any]          # the agent as the template made it, so later local edits can be told apart from the template's own changes
    scenario_names: list[str] = field(default_factory=list)
    tests: dict[str, Any] = field(default_factory=dict)
    installed_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"agent": self.agent_id, "template": self.template_id, "templateVersion": self.template_version, "params": self.params, "version": self.version_number,
                "installedBy": self.installed_by, "scenarios": self.scenario_names, "tests": self.tests, "installedAt": self.installed_at, "updatedAt": self.updated_at}


class InstallRepo(Protocol):
    async def save(self, i: Install) -> None: ...
    async def get(self, agent_id: str) -> Install | None: ...
    async def list(self) -> list[Install]: ...


class InMemoryInstalls:
    def __init__(self) -> None:
        self._items: dict[str, Install] = {}

    async def save(self, i: Install) -> None:
        i.updated_at = time.time()
        self._items[i.agent_id] = i

    async def get(self, agent_id: str) -> Install | None:
        return self._items.get(agent_id)

    async def list(self) -> list[Install]:
        return sorted(self._items.values(), key=lambda i: i.agent_id)


def check_requirements(t: Template, r: Rendered, tool_names: set[str], channels: dict[str, bool], knowledge_sources: int, qualification_required: bool = False,
                       required_tools: list[str] | None = None) -> dict[str, Any]:
    """One honest line per requirement, against this deployment as it is now. `ok` is false only for what would stop the agent working."""
    checks: list[dict[str, Any]] = []
    needed = list(dict.fromkeys(list(r.spec.tools) + [x for x in (required_tools if required_tools is not None else t.requires_tools) if x]))
    for tool in needed:
        have = tool in tool_names
        checks.append({"id": f"tool:{tool}", "label": f"Tool '{tool}'", "ok": have, "blocking": True,
                       "detail": "Available in this deployment." if have else "This deployment has no tool by that name. Add it (a connector file or code) or change the tool name when installing."})
    if t.requires_knowledge:
        checks.append({"id": "knowledge", "label": "Knowledge sources", "ok": knowledge_sources > 0, "blocking": True,
                       "detail": f"{knowledge_sources} source(s) available." if knowledge_sources else "This agent answers from your documents, and none have been added yet. Add a source in Library first."})
    for ch in t.requires_channels:
        on = channels.get(ch, False)
        checks.append({"id": f"channel:{ch}", "label": f"Channel '{ch}'", "ok": on, "blocking": True, "detail": "Configured." if on else f"The {ch} channel is not configured on this server."})
    for ch in t.channels:
        if ch not in t.requires_channels:
            on = channels.get(ch, False)
            checks.append({"id": f"channel-hint:{ch}", "label": f"Channel '{ch}' (where it is meant to be used)", "ok": on, "blocking": False,
                           "detail": "Configured." if on else f"Not configured here; it can still be used on other channels."})
    writes = [x for x in needed if x in tool_names]
    checks.append({"id": "tests", "label": "Test scenarios", "ok": len(r.scenarios) > 0, "blocking": False,
                   "detail": f"{len(r.scenarios)} scenario(s) come with it and are saved and run on install." if r.scenarios else "No scenarios come with it; add some before releasing."})
    if qualification_required:
        checks.append({"id": "model", "label": "Model qualification", "ok": True, "blocking": False,
                       "detail": "Model qualification is required here: run this agent's scenarios live on the model you want, and record the result, before it serves customers."})
    for w in r.warnings:
        if "no tool named" not in w:
            checks.append({"id": "warning", "label": "Note", "ok": False, "blocking": False, "detail": w})
    _ = writes
    return {"ok": all(c["ok"] or not c["blocking"] for c in checks), "checks": checks}


def scenario_diff(old: list[str], new: list[dict[str, Any]]) -> dict[str, list[str]]:
    names = {s["name"] for s in new}
    return {"added": sorted(names - set(old)), "removed": sorted(set(old) - names), "kept": sorted(names & set(old))}
