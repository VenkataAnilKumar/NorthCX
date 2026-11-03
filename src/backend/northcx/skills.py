"""Skills, workflow flexibility, brand voice and per-customer tool scopes (A3, A4, A10, T6).

A *skill* is a named, reusable piece of know-how: instructions, the tools it uses, and an ordered list of steps. An agent
lists the skills it has and, for each, how strictly the steps are followed:

- `strict`: the order is enforced. A tool that belongs to a later step is refused until the earlier required steps' tools
  have been used in this conversation, and the refusal tells the agent what to do first.
- `guided`: the agent is told to follow the steps in order unless the situation needs otherwise. Nothing is enforced.
- `free`: the steps are offered as suggestions.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .guardrails import Guardrail, GuardrailContext, Verdict

FLEXIBILITY = ("strict", "guided", "free")
_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")


class SkillError(ValueError):
    pass


@dataclass(frozen=True)
class SkillStep:
    purpose: str
    tool: str | None = None  # the tool that completes this step, if it has one
    required: bool = True


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    steps: tuple[SkillStep, ...] = ()
    tools: tuple[str, ...] = ()  # extra tools the skill needs, besides those named in steps

    def tool_names(self) -> list[str]:
        return list(dict.fromkeys([s.tool for s in self.steps if s.tool] + list(self.tools)))


def parse_skill(data: Any, source: str = "") -> Skill:
    where = source or "skill"
    if not isinstance(data, dict):
        raise SkillError(f"{where}: must be a mapping")
    unknown = set(data) - {"name", "description", "instructions", "steps", "tools"}
    if unknown:
        raise SkillError(f"{where}: unknown setting(s) {', '.join(sorted(unknown))}")
    name = str(data.get("name", ""))
    if not _NAME.match(name):
        raise SkillError(f"{where}: name must be 2-40 lowercase letters, digits, - or _")
    instructions = str(data.get("instructions", "")).strip()
    if not instructions or len(instructions) > 4000:
        raise SkillError(f"{where}: instructions must be 1-4000 characters")
    steps = []
    for i, s in enumerate(data.get("steps") or [], 1):
        if isinstance(s, str):
            s = {"purpose": s}
        if not isinstance(s, dict) or set(s) - {"purpose", "tool", "required"} or not str(s.get("purpose", "")).strip():
            raise SkillError(f"{where}: step {i} needs a 'purpose' (and may have 'tool' and 'required')")
        steps.append(SkillStep(str(s["purpose"]).strip()[:300], s.get("tool"), bool(s.get("required", True))))
    tools = data.get("tools") or []
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise SkillError(f"{where}: tools must be a list of tool names")
    return Skill(name, str(data.get("description", "")).strip()[:300], instructions, tuple(steps), tuple(tools))


def skill_to_dict(s: Skill) -> dict[str, Any]:
    return {"name": s.name, "description": s.description, "instructions": s.instructions,
            "steps": [{"purpose": x.purpose, **({"tool": x.tool} if x.tool else {}), "required": x.required} for x in s.steps], "tools": list(s.tools)}


def load_skills(path: str | Path) -> list[Skill]:
    p = Path(path)
    files = [p] if p.is_file() else sorted(f for f in p.glob("*") if f.suffix in (".yaml", ".yml", ".json"))
    out: list[Skill] = []
    for f in files:
        try:
            docs = [d for d in yaml.safe_load_all(f.read_text()) if d]
        except yaml.YAMLError as e:
            raise SkillError(f"{f}: not valid YAML or JSON: {e}") from e
        out += [parse_skill(d, str(f)) for d in docs]
    names = [s.name for s in out]
    if len(set(names)) != len(names):
        raise SkillError("skill names must be unique")
    return out


def render_skill(skill: Skill, flexibility: str, label: str = "Skill") -> str:
    lines = [f"## {label}: {skill.name}", skill.instructions]
    if skill.steps:
        how = {"strict": "Follow these steps in this order. Required steps cannot be skipped; the system refuses a step's tool until the earlier required steps are done.",
               "guided": "Follow these steps in this order unless the customer's situation clearly calls for something else.",
               "free": "These steps are suggestions; use your judgement."}[flexibility]
        lines.append(how)
        for i, s in enumerate(skill.steps, 1):
            lines.append(f"{i}. {s.purpose}" + (f" (tool: {s.tool})" if s.tool else "") + ("" if s.required else " (optional)"))
    return "\n".join(lines)


def render_voice(tone: str, guidelines: list[str], avoid: list[str], sign_off: str | None) -> str:
    lines = ["## Brand voice", f"Tone: {tone}"] if tone else ["## Brand voice"]
    lines += [f"- {g}" for g in guidelines]
    if avoid:
        lines.append("Never use these words or phrases: " + ", ".join(f'"{a}"' for a in avoid))
    if sign_off:
        lines.append(f'End conversations with: "{sign_off}"')
    return "\n".join(lines)


def tools_used(ctx: GuardrailContext) -> set[str]:
    """Every tool the agent has called so far in this conversation."""
    used = set()
    for m in ctx.messages:
        if isinstance(m.get("content"), list):
            used |= {b.get("name") for b in m["content"] if b.get("type") == "tool_use"}
    return used


class SkillOrder(Guardrail):
    """Enforces a strict skill: a step's tool is refused until the required steps before it have been done."""

    def __init__(self, skill: Skill):
        self.skill = skill
        self.name = f"skill-order:{skill.name}"
        self.steps = [s for s in skill.steps if s.tool]

    async def check_tool_call(self, name: str, input: dict[str, Any], ctx: GuardrailContext) -> Verdict:
        idx = next((i for i, s in enumerate(self.steps) if s.tool == name), None)
        if idx is None:
            return Verdict.ok()
        used = tools_used(ctx)
        for earlier in self.steps[:idx]:
            if earlier.required and earlier.tool not in used and earlier.tool != name:
                return Verdict.deny(f"Skill '{self.skill.name}' step '{earlier.purpose}' must be done first (use {earlier.tool})")
        return Verdict.ok()


@dataclass
class ToolScopeRule:
    requires_customer: bool = False
    facts: dict[str, list[str]] = field(default_factory=dict)  # the customer's fact must have one of these values
    channels: list[str] = field(default_factory=list)  # only on these channels (empty = any)


class ToolScope(Guardrail):
    """Limits who and where a tool may be used: only for identified customers, only for customers whose facts match,
    only on certain channels. Facts include what the company's systems report, so identity checks done elsewhere count."""

    name = "tool-scope"

    def __init__(self, rules: dict[str, ToolScopeRule]):
        self.rules = rules

    async def check_tool_call(self, name: str, input: dict[str, Any], ctx: GuardrailContext) -> Verdict:
        rule = self.rules.get(name)
        if rule is None:
            return Verdict.ok()
        if rule.requires_customer and not ctx.customer_id:
            return Verdict.deny(f"'{name}' is only available to identified customers")
        for key, allowed in rule.facts.items():
            if str(ctx.facts.get(key, "")).lower() not in {a.lower() for a in allowed}:
                return Verdict.deny(f"'{name}' is not available for this customer")
        if rule.channels and (ctx.channel or "") not in rule.channels:
            return Verdict.deny(f"'{name}' is not available on this channel")
        return Verdict.ok()
