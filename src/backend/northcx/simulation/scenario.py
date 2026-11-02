"""Scenario files: YAML or JSON, validated strictly so a typo fails loudly instead of silently checking nothing."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class ScenarioError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = {"extra": "forbid"}


class HandoffExpect(_Strict):
    trigger: str | None = None
    topics: list[str] | None = None


class StepExpect(_Strict):
    """Checks on one step. Everything is optional; unset fields check nothing."""

    status: str | None = None
    tools_called: list[str] = Field(default_factory=list)
    tools_not_called: list[str] = Field(default_factory=list)
    reply_includes: list[str] = Field(default_factory=list)
    reply_excludes: list[str] = Field(default_factory=list)
    reply_matches: str | None = None
    guardrail_hits: list[str] = Field(default_factory=list)
    handoff: Literal["none"] | HandoffExpect | None = None
    approval_state: str | None = None  # for `decide` steps
    expired: int | None = None  # for `expire_approvals` steps

    @field_validator("reply_matches")
    @classmethod
    def _regex_compiles(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:  # pydantic only turns ValueError into a validation message
                raise ValueError(f"invalid regular expression {v!r}: {e}") from e
        return v


class ApprovalExpect(_Strict):
    tool: str
    state: str


class FinalExpect(StepExpect):
    """Checks across the whole scenario."""

    max_model_calls: int | None = Field(default=None, ge=0)
    model_input_includes: list[str] = Field(default_factory=list)
    model_input_excludes: list[str] = Field(default_factory=list)
    approvals: list[ApprovalExpect] = Field(default_factory=list)
    outbox_kinds: list[str] | None = None


class Say(_Strict):
    say: str = Field(min_length=1)
    expect: StepExpect | None = None


class Decide(_Strict):
    decide: Literal["approve", "reject"]
    by: str = "simulated-reviewer"
    note: str | None = None
    tool: str | None = None  # which pending approval; default: the most recent
    expect: StepExpect | None = None


class ExpireApprovals(_Strict):
    expire_approvals: bool
    expect: StepExpect | None = None


Step = Say | Decide | ExpireApprovals


class ModelResponse(_Strict):
    """One scripted model response: plain text, or a tool call."""

    text: str | None = None
    tool_call: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "ModelResponse":
        if (self.text is None) == (self.tool_call is None):
            raise ValueError("a model response needs exactly one of 'text' or 'tool_call'")
        if self.tool_call is not None and set(self.tool_call) - {"name", "input"} or (
                self.tool_call is not None and "name" not in self.tool_call):
            raise ValueError("tool_call needs 'name' and optionally 'input'")
        return self


class JudgeSpec(_Strict):
    rubric: str = Field(min_length=1)
    min_score: int = Field(default=4, ge=1, le=5)


class Scenario(_Strict):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    description: str = ""
    agent: str
    required: bool = True  # required scenarios gate releases
    customer_id: str | None = None
    facts: dict[str, str] = Field(default_factory=dict)
    model: list[ModelResponse] | None = None  # scripted model responses (deterministic runs)
    turns: list[Step] = Field(min_length=1)
    expect: FinalExpect = Field(default_factory=FinalExpect)
    judge: JudgeSpec | None = None
    trials: int = Field(default=1, ge=1, le=50)  # live-model runs are repeated
    min_pass_rate: float = Field(default=1.0, gt=0, le=1)
    source: str = ""  # file the scenario came from

    @model_validator(mode="after")
    def _steps_make_sense(self) -> "Scenario":
        if not any(isinstance(t, Say) for t in self.turns):
            raise ValueError("a scenario needs at least one 'say' step")
        first = self.turns[0]
        if not isinstance(first, Say):
            raise ValueError("the first step must be a 'say'")
        return self


def _fmt(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())


def parse_scenario(data: Any, source: str = "") -> Scenario:
    if not isinstance(data, dict):
        raise ScenarioError(f"{source or 'scenario'}: must be a mapping")
    try:
        sc = Scenario.model_validate(data)
    except ValidationError as e:
        raise ScenarioError(f"{source or 'scenario'}: {_fmt(e)}") from e
    sc.source = source
    return sc


def load_scenarios(path: str | Path) -> list[Scenario]:
    """Load one file, or every .yaml/.yml/.json file under a directory (recursively). Names must be unique."""
    p = Path(path)
    files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.suffix in (".yaml", ".yml", ".json"))
    if not files:
        raise ScenarioError(f"No scenario files found in {path}")
    out: list[Scenario] = []
    for f in files:
        try:
            docs = list(yaml.safe_load_all(f.read_text()))
        except yaml.YAMLError as e:
            raise ScenarioError(f"{f}: not valid YAML or JSON: {e}") from e
        for doc in docs:
            if doc is not None:
                out.append(parse_scenario(doc, str(f)))
    names = [s.name for s in out]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ScenarioError(f"Duplicate scenario names: {', '.join(dupes)}")
    return out
