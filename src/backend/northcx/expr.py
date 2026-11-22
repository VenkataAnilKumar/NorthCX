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


# ---------------- conditions ----------------
MAX_CONDITION = 300
MAX_DEPTH = 8
_TOKEN = re.compile(r"""\s*(?:(?P<num>-?\d+(?:\.\d+)?)|(?P<str>'[^'\\]*'|"[^"\\]*")|(?P<op>==|!=|<=|>=|<|>|\(|\))|(?P<word>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d{1,4}\])*))""")
_WORDS = {"and", "or", "not", "in", "contains", "true", "false", "null", "len"}


class ConditionError(ValueError):
    pass


def _tokens(text: str) -> list[tuple[str, str]]:
    if len(text) > MAX_CONDITION:
        raise ConditionError(f"a condition is at most {MAX_CONDITION} characters")
    out, pos = [], 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        m = _TOKEN.match(text, pos)
        if m is None:
            raise ConditionError(f"cannot read the condition at '{text[pos:pos + 12].strip()}'")
        pos = m.end()
        kind = m.lastgroup or ""
        out.append((kind, m.group(kind)))
    return out


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]], allow_item: bool):
        self.t, self.i, self.allow_item = tokens, 0, allow_item

    def peek(self) -> tuple[str, str] | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise ConditionError("the condition ends too soon")
        self.i += 1
        return tok

    def accept(self, *values: str) -> str | None:
        tok = self.peek()
        if tok is not None and tok[0] in ("op", "word") and tok[1] in values:
            self.i += 1
            return tok[1]
        return None

    def expr(self, depth: int) -> Any:
        if depth > MAX_DEPTH:
            raise ConditionError(f"a condition may nest at most {MAX_DEPTH} levels")
        left = self.and_(depth)
        while self.accept("or"):
            left = ("or", left, self.and_(depth))
        return left

    def and_(self, depth: int) -> Any:
        left = self.not_(depth)
        while self.accept("and"):
            left = ("and", left, self.not_(depth))
        return left

    def not_(self, depth: int) -> Any:
        if self.accept("not"):
            if depth + 1 > MAX_DEPTH:
                raise ConditionError(f"a condition may nest at most {MAX_DEPTH} levels")
            return ("not", self.not_(depth + 1))
        return self.cmp(depth)

    def cmp(self, depth: int) -> Any:
        left = self.atom(depth)
        op = self.accept("==", "!=", "<=", ">=", "<", ">", "in", "contains")
        return (op, left, self.atom(depth)) if op else left

    def atom(self, depth: int) -> Any:
        kind, text = self.take()
        if kind == "num":
            return ("lit", float(text) if "." in text else int(text))
        if kind == "str":
            return ("lit", text[1:-1])
        if kind == "op" and text == "(":
            inner = self.expr(depth + 1)
            if not self.accept(")"):
                raise ConditionError("a bracket is not closed")
            return inner
        if kind == "word":
            if text in ("true", "false", "null"):
                return ("lit", {"true": True, "false": False, "null": None}[text])
            if text == "len":
                if not self.accept("("):
                    raise ConditionError("len needs a path in brackets, such as len(previous.items)")
                p = self.take()
                if p[0] != "word" or not is_path(p[1]) or not self.accept(")"):
                    raise ConditionError("len needs a path in brackets, such as len(previous.items)")
                return ("len", self.path(p[1]))
            if text in _WORDS:
                raise ConditionError(f"'{text}' is not allowed here")
            if not is_path(text):
                raise ConditionError(f"'{text.split('.')[0].split('[')[0]}' is not a value; start with previous, input or item")
            return self.path(text)
        raise ConditionError(f"unexpected '{text}'")

    def path(self, text: str) -> Any:
        if text.split(".")[0].split("[")[0] == "item" and not self.allow_item:
            raise ConditionError("'item' can be used only inside a foreach step")
        return ("path", text)


def parse_condition(text: str, allow_item: bool = False) -> Any:
    """Check a condition and return its tree. Raises ConditionError with a plain message."""
    if not isinstance(text, str) or not text.strip():
        raise ConditionError("write the condition")
    parser = _Parser(_tokens(text), allow_item)
    tree = parser.expr(0)
    if parser.peek() is not None:
        raise ConditionError(f"cannot read the condition from '{parser.peek()[1]}'")  # type: ignore[index]
    return tree


def _truthy(v: Any) -> bool:
    return bool(v) if v is not None else False


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _order(op: str, a: Any, b: Any) -> bool:
    if not ((_num(a) and _num(b)) or (isinstance(a, str) and isinstance(b, str))):
        return False
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]  # type: ignore[operator]


def _within(needle: Any, haystack: Any) -> bool:
    if isinstance(haystack, list):
        return any(_same(needle, x) for x in haystack)
    if isinstance(haystack, str):
        return isinstance(needle, str) and needle in haystack
    if isinstance(haystack, dict):
        return isinstance(needle, str) and needle in haystack
    return False


def evaluate(tree: Any, roots: dict[str, Any]) -> Any:
    """The value of a checked condition. It always ends: the tree is finite and has no calls or loops. A missing value is null and comparing unlike things is false."""
    kind = tree[0]
    if kind == "lit":
        return tree[1]
    if kind == "path":
        return resolve(tree[1], roots)
    if kind == "len":
        v = evaluate(tree[1], roots)
        return len(v) if isinstance(v, (list, str, dict)) else None
    if kind == "not":
        return not _truthy(evaluate(tree[1], roots))
    if kind == "and":
        return _truthy(evaluate(tree[1], roots)) and _truthy(evaluate(tree[2], roots))
    if kind == "or":
        return _truthy(evaluate(tree[1], roots)) or _truthy(evaluate(tree[2], roots))
    a, b = evaluate(tree[1], roots), evaluate(tree[2], roots)
    if kind == "==":
        return _same(a, b)
    if kind == "!=":
        return not _same(a, b)
    if kind in ("<", "<=", ">", ">="):
        return _order(kind, a, b)
    if kind == "in":
        return _within(a, b)
    return _within(b, a)  # contains


def holds(text: str, roots: dict[str, Any], allow_item: bool = False) -> bool:
    return _truthy(evaluate(parse_condition(text, allow_item), roots))
