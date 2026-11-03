"""Declarative agent definitions.

An `AgentSpec` is plain data (instructions, references to tools and guardrails by name, limits). A `Registry`
maps those names to code, so a spec can be stored, versioned, diffed, edited in Studio and run.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from .agent import Agent, Tool
from .skills import FLEXIBILITY, Skill, SkillOrder, ToolScope, ToolScopeRule, render_skill, render_voice
from .policies import FACTORIES as POLICY_FACTORIES
from .guardrails import Guardrail, InputGuardrail, OutputGuardrail, LLMPolicy, NoCardNumbers
from .handoffs import ForcedTopic
from .safety import PIIDetection, PromptInjection, ToolOutputInjection, ToolOutputPII
from .types import LLM

SPEC_VERSION = 1


class SpecError(ValueError):
    """The spec is invalid or refers to something the registry does not know."""


class ComponentRef(BaseModel):
    """Reference to a registered guardrail, with optional configuration."""

    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class ForcedTopicSpec(BaseModel):
    """A topic that always goes to a person. `patterns` are case-insensitive regular expressions."""

    name: str = Field(min_length=1)
    patterns: list[str] = Field(min_length=1)
    reply: str | None = None
    model_config = {"extra": "forbid"}

    @field_validator("patterns")
    @classmethod
    def _patterns_compile(cls, v: list[str], info) -> list[str]:
        ForcedTopic(info.data.get("name", "?"), v)  # raises ValueError on a bad or oversized pattern
        return v


class SkillRef(BaseModel):
    name: str
    flexibility: str = "guided"
    model_config = {"extra": "forbid"}

    @field_validator("flexibility")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in FLEXIBILITY:
            raise ValueError(f"flexibility must be one of {', '.join(FLEXIBILITY)}")
        return v


class VoiceSpec(BaseModel):
    tone: str = Field(default="", max_length=200)
    guidelines: list[str] = Field(default_factory=list, max_length=12)
    avoid_phrases: list[str] = Field(default_factory=list, max_length=30)  # also enforced: a reply containing one is rejected
    sign_off: str | None = Field(default=None, max_length=200)
    model_config = {"extra": "forbid"}


class ToolScopeSpec(BaseModel):
    requires_customer: bool = False
    facts: dict[str, list[str]] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class AgentSpec(BaseModel):
    spec_version: int = SPEC_VERSION
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    instructions: str = Field(min_length=1)
    model: str | None = None
    max_steps: int = Field(default=8, ge=1, le=50)
    max_run_tokens: int | None = Field(default=None, ge=1000, le=5_000_000)
    channel_styles: dict[str, str] = Field(default_factory=dict)
    skills: list[SkillRef] = Field(default_factory=list)
    voice: VoiceSpec | None = None
    tool_scopes: dict[str, ToolScopeSpec] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    guardrails: list[ComponentRef] = Field(default_factory=list)
    input_guardrails: list[ComponentRef] = Field(default_factory=list)
    output_guardrails: list[ComponentRef] = Field(default_factory=list)
    forced_handoff: list[ForcedTopicSpec] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

    @field_validator("guardrails", "input_guardrails", "output_guardrails", mode="before")
    @classmethod
    def _allow_bare_names(cls, v: Any) -> Any:
        # Authors may write a plain string instead of {name: ...}
        return [{"name": x} if isinstance(x, str) else x for x in (v or [])]

    @field_validator("channel_styles")
    @classmethod
    def _styles(cls, v: dict[str, str]) -> dict[str, str]:
        for k, text in v.items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{1,19}", k):
                raise ValueError(f"channel name '{k}' must be 2-20 lowercase letters, digits, - or _")
            if not text.strip() or len(text) > 1000:
                raise ValueError(f"style for '{k}' must be 1-1000 characters")
        return v

    @field_validator("spec_version")
    @classmethod
    def _known_version(cls, v: int) -> int:
        if v != SPEC_VERSION:
            raise ValueError(f"Unsupported spec_version {v}; this build reads version {SPEC_VERSION}")
        return v

    def canonical(self) -> str:
        data = self.model_dump(mode="json")
        if data.get("max_run_tokens") is None:
            del data["max_run_tokens"]  # keeps digests of specs written before this field existed
        for key in ("skills", "voice", "tool_scopes"):
            if not data[key]:
                del data[key]  # keeps digests of specs written before these fields existed
        if not data["channel_styles"]:
            del data["channel_styles"]  # keeps digests of specs written before this field existed
        if not data["output_guardrails"]:
            del data["output_guardrails"]  # keeps the digest of specs written before this field existed
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def digest(self) -> str:
        """Stable content hash. Identical specs always have the same digest."""
        return hashlib.sha256(self.canonical().encode()).hexdigest()


GuardrailFactory = Callable[[dict[str, Any], "BuildContext"], Guardrail]
InputFactory = Callable[[dict[str, Any], "BuildContext"], InputGuardrail]
OutputFactory = Callable[[dict[str, Any], "BuildContext"], OutputGuardrail]


class BuildContext:
    """Dependencies a guardrail factory may need (for example a model for a policy supervisor)."""

    def __init__(self, llm: LLM | None = None):
        self.llm = llm


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._guardrails: dict[str, GuardrailFactory] = {}
        self._input_guardrails: dict[str, InputFactory] = {}
        self._output_guardrails: dict[str, OutputFactory] = {}
        self._skills: dict[str, Skill] = {}

    def tool(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise SpecError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        return tool

    def guardrail(self, name: str, factory: GuardrailFactory) -> None:
        self._guardrails[name] = factory

    def input_guardrail(self, name: str, factory: InputFactory) -> None:
        self._input_guardrails[name] = factory

    def output_guardrail(self, name: str, factory: "OutputFactory") -> None:
        self._output_guardrails[name] = factory

    def skill(self, skill: Skill) -> Skill:
        if skill.name in self._skills:
            raise SpecError(f"Skill '{skill.name}' is already registered")
        self._skills[skill.name] = skill
        return skill

    def skill_names(self) -> list[str]:
        return sorted(self._skills)

    def skill_info(self) -> list[Skill]:
        return [self._skills[n] for n in self.skill_names()]

    def output_guardrail_names(self) -> list[str]:
        return sorted(self._output_guardrails)

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def guardrail_names(self) -> list[str]:
        return sorted(self._guardrails)

    def input_guardrail_names(self) -> list[str]:
        return sorted(self._input_guardrails)

    def validate(self, spec: AgentSpec) -> list[str]:
        """Return every problem found, so authors fix them in one pass."""
        problems = []
        for t in dict.fromkeys(spec.tools):  # each unknown name reported once
            if t not in self._tools:
                problems.append(f"Unknown tool '{t}' (known: {', '.join(self.tool_names()) or 'none'})")
        if len(set(spec.tools)) != len(spec.tools):
            problems.append("Duplicate tool references")
        names = [t.name for t in spec.forced_handoff]
        if len(set(names)) != len(names):
            problems.append("Duplicate forced_handoff topic names")
        for g in spec.guardrails:
            if g.name not in self._guardrails:
                problems.append(f"Unknown guardrail '{g.name}' (known: {', '.join(self.guardrail_names()) or 'none'})")
        for g in spec.input_guardrails:
            if g.name not in self._input_guardrails:
                problems.append(f"Unknown input guardrail '{g.name}' (known: {', '.join(self.input_guardrail_names()) or 'none'})")
        for g in spec.output_guardrails:
            if g.name not in self._output_guardrails:
                problems.append(f"Unknown output guardrail '{g.name}' (known: {', '.join(self.output_guardrail_names()) or 'none'})")
        refs = [s.name for s in spec.skills]
        if len(set(refs)) != len(refs):
            problems.append("Duplicate skill references")
        for ref in dict.fromkeys(refs):
            sk = self._skills.get(ref)
            if sk is None:
                problems.append(f"Unknown skill '{ref}' (known: {', '.join(self.skill_names()) or 'none'})")
                continue
            for t in sk.tool_names():
                if t not in self._tools:
                    problems.append(f"Skill '{ref}' needs the tool '{t}', which is not registered")
        for t in spec.tool_scopes:
            if t not in self._tools:
                problems.append(f"tool_scopes names the unknown tool '{t}'")
        return problems

    def _all_tools(self, spec: AgentSpec) -> list[str]:
        """The spec's tools plus those its skills need (each once)."""
        extra = [t for r in spec.skills for t in self._skills[r.name].tool_names()]
        return list(dict.fromkeys(list(spec.tools) + extra))

    def _compose(self, spec: AgentSpec) -> str:
        """Instructions as the model sees them: the spec's own text, then brand voice, then each skill."""
        parts = [spec.instructions.rstrip()]
        if spec.voice:
            parts.append(render_voice(spec.voice.tone, spec.voice.guidelines, spec.voice.avoid_phrases, spec.voice.sign_off))
        parts += [render_skill(self._skills[r.name], r.flexibility) for r in spec.skills]
        return "\n\n".join(parts) + ("\n" if spec.instructions.endswith("\n") else "")

    def _enforcers(self, spec: AgentSpec) -> list[Guardrail]:
        """Guardrails that turn skills, voice and tool scopes from advice into rules."""
        out: list[Guardrail] = [SkillOrder(self._skills[r.name]) for r in spec.skills if r.flexibility == "strict" and self._skills[r.name].steps]
        if spec.voice and spec.voice.avoid_phrases:
            out.append(POLICY_FACTORIES["forbidden_phrases"]({"phrases": spec.voice.avoid_phrases, "reason": "Reply uses wording the brand voice forbids."}, None))
        if spec.tool_scopes:
            out.append(ToolScope({t: ToolScopeRule(s.requires_customer, {k: list(v) for k, v in s.facts.items()}, list(s.channels))
                                  for t, s in spec.tool_scopes.items()}))
        return out

    def build(self, spec: AgentSpec, ctx: BuildContext | None = None) -> Agent:
        problems = self.validate(spec)
        if problems:
            raise SpecError("; ".join(problems))
        ctx = ctx or BuildContext()
        try:
            return Agent(
                id=spec.id,
                instructions=self._compose(spec),
                model=spec.model,
                max_steps=spec.max_steps,
                max_run_tokens=spec.max_run_tokens,
                channel_styles=dict(spec.channel_styles),
                tools=[self._tools[t] for t in self._all_tools(spec)],
                guardrails=[self._guardrails[g.name](g.config, ctx) for g in spec.guardrails] + self._enforcers(spec),
                input_guardrails=[self._input_guardrails[g.name](g.config, ctx) for g in spec.input_guardrails],
                output_guardrails=[self._output_guardrails[g.name](g.config, ctx) for g in spec.output_guardrails],
                forced_handoffs=[ForcedTopic(t.name, t.patterns, **({"reply": t.reply} if t.reply else {}))
                                 for t in spec.forced_handoff],
            )
        except (TypeError, ValueError) as e:  # bad guardrail configuration
            raise SpecError(f"Invalid guardrail configuration: {e}") from e


def default_registry() -> Registry:
    """A registry with NorthCX's built-in guardrails. Callers add their own tools."""
    r = Registry()
    r.guardrail("no_card_numbers", lambda cfg, ctx: NoCardNumbers())
    for _name, _factory in POLICY_FACTORIES.items():
        r.guardrail(_name, _factory)

    def llm_policy(cfg: dict[str, Any], ctx: BuildContext) -> Guardrail:
        if ctx.llm is None:
            raise ValueError("llm_policy needs a model; pass BuildContext(llm=...)")
        policies = cfg.get("policies")
        if not policies or not all(isinstance(p, str) for p in policies):
            raise ValueError("llm_policy needs a non-empty list of policy strings in 'policies'")
        return LLMPolicy(ctx.llm, policies, cfg.get("model"))

    r.guardrail("llm_policy", llm_policy)
    r.input_guardrail("pii_detection", lambda cfg, ctx: PIIDetection(**cfg))
    r.input_guardrail("prompt_injection", lambda cfg, ctx: PromptInjection(**cfg))
    r.output_guardrail("tool_output_injection", lambda cfg, ctx: ToolOutputInjection(**cfg))
    r.output_guardrail("tool_output_pii", lambda cfg, ctx: ToolOutputPII(**cfg))
    return r


def parse_spec(text: str) -> AgentSpec:
    """Parse YAML or JSON text (JSON is valid YAML)."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SpecError(f"Not valid YAML or JSON: {e}") from e
    if not isinstance(data, dict):
        raise SpecError("A spec must be a mapping with fields such as 'id' and 'instructions'")
    try:
        return AgentSpec.model_validate(data)
    except ValidationError as e:
        raise SpecError(_format_errors(e)) from e


def load_spec(path: str | Path) -> AgentSpec:
    return parse_spec(Path(path).read_text())


def load_specs(directory: str | Path) -> list[AgentSpec]:
    d = Path(directory)
    if not d.is_dir():
        raise SpecError(f"Spec directory not found: {directory}")
    files = sorted(d.glob("*.y*ml")) + sorted(d.glob("*.json"))
    if not files:
        raise SpecError(f"No agent spec files (*.yaml, *.yml, *.json) in {directory}")
    specs = [load_spec(p) for p in files]
    ids = [s.id for s in specs]
    if len(set(ids)) != len(ids):
        raise SpecError("Duplicate agent ids in " + str(directory))
    return specs


def dump_spec(spec: AgentSpec) -> str:
    """Stable JSON text for storage."""
    return json.dumps(spec.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _format_errors(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in err['loc']) or 'spec'}: {err['msg']}" for err in e.errors())
