"""Plain-language wording for what an author can get wrong (docs/02-studio/NorthCX_Guided-Studio.md, requirement R4).

Field errors from the definition are written with the names the screens use and say what is allowed; the checks in `spec.py` and the
release gate write their own sentences. A test builds every kind of mistake and fails on developer words."""
from __future__ import annotations

from typing import Any

LABELS = {
    "id": "Agent id", "instructions": "Instructions", "model": "Model", "max_steps": "Most steps per message", "max_run_tokens": "Token limit per message",
    "audience": "Audience", "shadow": "Shadow mode", "sensitive": "Sensitive conversations", "channel_styles": "Style for each channel", "journeys": "Journeys",
    "tools": "Tools", "guardrails": "Reply and tool checks", "input_guardrails": "Customer message checks", "output_guardrails": "Tool answer checks",
    "forced_handoff": "Topics that always go to a person", "skills": "Skills", "routes": "Specialists", "languages": "Languages", "voice": "Voice",
    "tool_scopes": "Limits on tools", "attachments": "Files the agent accepts", "approvals": "Actions that need a person's OK", "always": "Always needs a person",
    "name": "Name", "goal": "Goal", "steps": "Steps", "purpose": "Purpose", "tool": "Tool", "flexibility": "How strictly to follow the steps", "patterns": "Words that trigger it",
    "config": "Settings", "agent": "Agent", "when": "When",
}
_PLURAL = {"Instructions", "Tools", "Journeys", "Skills", "Specialists", "Languages", "Steps", "Limits on tools", "Reply and tool checks", "Customer message checks",
           "Tool answer checks", "Topics that always go to a person", "Files the agent accepts", "Actions that need a person's OK", "Words that trigger it", "Settings"}


def _label(part: str) -> str:
    return LABELS.get(part, part.replace("_", " ").capitalize())


def _place(loc: tuple[Any, ...]) -> str:
    if not loc:
        return "The definition"
    words = []
    for p in loc:
        if isinstance(p, int):
            words.append(f"item {p + 1}")
        else:
            words.append(_label(str(p)))
    return ", ".join(words)


def _verb(label: str) -> str:
    return "are" if label in _PLURAL else "is"


def explain(err: dict[str, Any]) -> str:
    """One field error as a sentence: where it is, and what is allowed."""
    loc, kind, ctx = tuple(err.get("loc", ())), str(err.get("type", "")), err.get("ctx") or {}
    place = _place(loc)
    be = _verb(place.split(", ")[-1])
    field = next((str(p) for p in reversed(loc) if not isinstance(p, int)), "")
    if kind == "missing":
        return f"{place} {be} required."
    if kind in ("string_too_short", "too_short") and ctx.get("min_length", 1) <= 1:
        return f"{place} cannot be empty."
    if kind in ("string_too_short", "too_short"):
        return f"{place} needs at least {ctx['min_length']}."
    if kind in ("string_too_long", "too_long"):
        return f"{place} can be at most {ctx.get('max_length')} long."
    if kind == "string_pattern_mismatch":
        if field == "id":
            return f"{place} can only use letters, digits, dots, dashes and underscores."
        if field == "name":
            return f"{place} must start with a lowercase letter and use only lowercase letters, digits, dashes and underscores (2 to 40 characters)."
        return f"{place} is not in an allowed form."
    if kind == "less_than_equal":
        return f"{place} must be at most {ctx.get('le')}."
    if kind == "greater_than_equal":
        return f"{place} must be at least {ctx.get('ge')}."
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return f"{place} must be a whole number."
    if kind in ("bool_parsing", "bool_type"):
        return f"{place} must be yes or no."
    if kind == "literal_error":
        return f"{place} must be one of: {str(ctx.get('expected', '')).replace(chr(39), '').replace(' or ', ', ')}."
    if kind == "extra_forbidden":
        return f"'{loc[-1]}' is not something {'an agent' if len(loc) == 1 else 'this part'} can have. Remove it."
    if kind in ("string_type", "list_type", "dict_type", "model_type"):
        return f"{place} is in the wrong form: {'text' if kind == 'string_type' else 'a list' if kind == 'list_type' else 'a set of fields'} is expected."
    return f"{place}: {err.get('msg', 'is not valid')}."


def explain_errors(errors: list[dict[str, Any]]) -> list[str]:
    return [explain(e) for e in errors]


def tool_label(name: str) -> str:
    """A tool's name as words: `lookup_order` is "lookup order"; an MCP tool `shop__orders_lookup` is "orders lookup from shop"."""
    connection, _, rest = name.partition("__")
    return f"{rest.replace('_', ' ')} from {connection}" if rest else name.replace("_", " ")


def _list(items: list[str]) -> str:
    return ", ".join(items)


def summarize(spec: Any, tools: list[dict[str, Any]]) -> list[str]:
    """What the agent will do, in sentences, from the definition and the tool catalogue. No model writes this, so it cannot say anything the
    definition does not."""
    known = {t["name"]: t for t in tools}
    mine = list(dict.fromkeys(spec.tools))
    reads = [t for t in mine if known.get(t, {}).get("effect") != "write"]
    writes = [t for t in mine if known.get(t, {}).get("effect") == "write"]
    always = set(spec.approvals.always)
    out = ["This agent helps your staff." if spec.audience == "staff" else "This agent answers customers."]
    if not mine:
        out.append("It has no tools, so it cannot look anything up or change anything.")
    if reads:
        out.append(f"It can look up: {_list([tool_label(t) for t in reads])}.")
    if writes:
        out.append(f"It can change things: {_list([tool_label(t) for t in writes])}.")
    for t in mine:
        label = tool_label(t)
        if t in always:
            out.append(f"A person approves every use of {label}.")
        elif known.get(t, {}).get("effect") == "write" and not known[t].get("approval"):
            out.append(f"{label} changes things and runs without a person's OK.")
        if t not in always and known.get(t, {}).get("approval"):
            out.append(f"{label} has its own rule that can hold a call for a person.")
    if spec.forced_handoff:
        out.append(f"Conversations about {_list([h.name.replace('_', ' ') for h in spec.forced_handoff])} always go to a person.")
    if spec.journeys:
        n = len(spec.journeys)
        out.append(f"It follows {n} journey{'' if n == 1 else 's'}: {_list([j.name for j in spec.journeys])}.")
    if spec.routes:
        out.append(f"It can pass a conversation to: {_list([r.agent for r in spec.routes])}.")
    if spec.languages:
        out.append(f"It replies in {_list(spec.languages)}.")
    if spec.guardrails or spec.input_guardrails or spec.output_guardrails:
        parts = [(len(spec.guardrails), "on replies and tool calls"), (len(spec.input_guardrails), "on customer messages"), (len(spec.output_guardrails), "on tool answers")]
        shown = [f"{n} {where}" for n, where in parts if n]
        out.append(f"{shown[0].split(' ', 1)[0]} check{'' if shown[0].startswith('1 ') else 's'} {shown[0].split(' ', 1)[1]}" + (", " + ", ".join(shown[1:]) if len(shown) > 1 else "") + ".")
    if spec.shadow:
        out.append("Shadow mode is on: a person approves every reply before the customer sees it.")
    return out


def compare_verdict(rows: list[dict[str, Any]]) -> str:
    """One sentence on how a candidate version did against the live one on the same tests."""
    if not rows:
        return "There are no tests to compare."
    worse = [r["name"] for r in rows if r["change"] == "regressed"]
    better = [r["name"] for r in rows if r["change"] == "fixed"]
    if not worse and not better:
        return f"The candidate gives the same results as the live version on {len(rows)} test{'' if len(rows) == 1 else 's'}."
    parts = []
    if worse:
        parts.append(f"The candidate fails {len(worse)} test{'' if len(worse) == 1 else 's'} that the live version passes: {', '.join(worse)}.")
    if better:
        parts.append(f"It passes {len(better)} test{'' if len(better) == 1 else 's'} that the live version fails: {', '.join(better)}.")
    return " ".join(parts)
