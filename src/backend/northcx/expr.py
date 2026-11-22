"""Values and templates for routines.

A routine passes a step's result to the next one as text. When the text is JSON it can be read as a value: `{{previous.order.id}}` in a step's
arguments or prompt, with `previous`, `input` (what started the run) and, inside a `foreach`, `item` as the roots. A missing part reads as null.
Nothing here can call anything, loop or run code.
"""
from __future__ import annotations

import json
import re
from typing import Any

ROOTS = ("previous", "input", "item")
_PATH = re.compile(r"(?P<root>previous|input|item)(?P<rest>(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d{1,4}\])*)")
_STEP = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d{1,4})\]")
TEMPLATE = re.compile(r"\{\{\s*((?:previous|input|item)(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d{1,4}\])*)\s*\}\}")


def is_path(text: str) -> bool:
    return _PATH.fullmatch(text) is not None


def as_value(text: str) -> Any:
    """Text that is JSON is read as the value it holds; any other text stays text."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def resolve(path: str, roots: dict[str, Any]) -> Any:
    """The value at a path such as `previous.items[0].status`, or None when any part is missing."""
    m = _PATH.fullmatch(path)
    if m is None:
        raise ValueError(f"not a path: {path!r}")
    cur = roots.get(m.group("root"))
    for name, index in _STEP.findall(m.group("rest")):
        if name:
            cur = cur.get(name) if isinstance(cur, dict) else None
        else:
            i = int(index)
            cur = cur[i] if isinstance(cur, list) and i < len(cur) else None
    return cur


def paths_in(value: Any) -> list[str]:
    """Every placeholder path written in a string, list or mapping, for checking a definition when it is saved."""
    if isinstance(value, str):
        return TEMPLATE.findall(value)
    if isinstance(value, list):
        return [p for v in value for p in paths_in(v)]
    if isinstance(value, dict):
        return [p for v in value.values() for p in paths_in(v)]
    return []


def fill(value: Any, roots: dict[str, Any]) -> Any:
    """The value with every placeholder replaced. A string that is exactly one placeholder keeps the type of what it points at; a placeholder inside longer text
    is written into it (objects as JSON)."""
    if isinstance(value, str):
        whole = TEMPLATE.fullmatch(value.strip())
        if whole:
            return resolve(whole.group(1), roots)
        def one(m: re.Match[str]) -> str:
            v = resolve(m.group(1), roots)
            return v if isinstance(v, str) else "" if v is None else json.dumps(v, default=str)
        return TEMPLATE.sub(one, value)
    if isinstance(value, list):
        return [fill(v, roots) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, roots) for k, v in value.items()}
    return value
