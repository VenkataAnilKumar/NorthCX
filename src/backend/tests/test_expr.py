"""WP 5.2: the small, total condition language for routines (A4, A5)."""
import random

import pytest

from northcx import expr

ROOTS = {"previous": {"total": 240, "status": "late", "items": [{"sku": "a"}, {"sku": "b"}], "flag": True, "note": "Refund pending"}, "input": {"priority": "urgent"}, "item": {"id": 7}}


@pytest.mark.parametrize("text,want", [
    ("previous.total > 100", True), ("previous.total >= 240", True), ("previous.total < 100", False),
    ("previous.status == 'late'", True), ('previous.status != "late"', False),
    ("len(previous.items) == 2", True), ("len(previous.missing) == 0", False),
    ("previous.items[1].sku == 'b'", True), ("previous.items[5].sku == 'b'", False),
    ("previous.flag", True), ("not previous.flag", False), ("previous.missing", False), ("not previous.missing", True),
    ("'late' in previous.status", True), ("'ate' in previous.status", True), ("'x' in previous.status", False), ("input.priority in previous.items", False),
    ("previous.note contains 'Refund'", True), ("previous.note contains 'refund'", False),
    ("input.priority == 'urgent' and previous.total > 100", True), ("input.priority == 'low' or previous.total > 100", True),
    ("(input.priority == 'low' or previous.total > 100) and not previous.flag", False),
    ("previous.total == '240'", False),            # unlike types are not equal
    ("previous.flag == 1", False),                 # a yes/no is not a number
    ("previous.missing == null", True), ("previous.total > 'a'", False), ("item.id == 7", True),
])
def test_conditions_give_the_expected_answer(text, want):
    assert expr.holds(text, ROOTS, allow_item=True) is want


@pytest.mark.parametrize("bad", [
    "", "   ", "__import__('os')", "previous.total.upper()", "previous.total +", "previous.total > ", "(previous.total", "previous.total > 1)",
    "open('x')", "x == 1", "previous.", "previous..a", "len(5)", "len(previous.items", "lambda: 1", "previous.total = 3", "previous.total > 1; x", "previous.status in ['x']",
    "item.id == 1", "a" * 301, "(" * 9 + "previous.flag" + ")" * 9, "not " * 9 + "previous.flag", "previous['a']", "previous.a$b", "true false",
])
def test_a_condition_that_could_do_more_than_read_values_is_refused_when_saved(bad):
    with pytest.raises(expr.ConditionError):
        expr.parse_condition(bad)


def test_item_is_allowed_only_where_a_foreach_gives_one():
    with pytest.raises(expr.ConditionError, match="only inside a foreach"):
        expr.parse_condition("item.id == 1")
    assert expr.parse_condition("item.id == 1", allow_item=True)


def _random_condition(r: random.Random, depth: int = 0) -> str:
    atoms = ["previous.total", "previous.items[0].sku", "input.priority", "previous.missing", "len(previous.items)", "'late'", "240", "true", "null", "previous.note"]
    if depth > 3 or r.random() < 0.3:
        return r.choice(atoms)
    pick = r.random()
    if pick < 0.2:
        return f"not {_random_condition(r, depth + 1)}"
    if pick < 0.4:
        return f"({_random_condition(r, depth + 1)} {r.choice(['and', 'or'])} {_random_condition(r, depth + 1)})"
    return f"{r.choice(atoms)} {r.choice(['==', '!=', '<', '<=', '>', '>=', 'in', 'contains'])} {r.choice(atoms)}"


def _random_value(r: random.Random, depth: int = 0) -> object:
    pick = r.random()
    if depth > 2 or pick < 0.4:
        return r.choice([None, True, False, 0, 1, 240, -3, 2.5, "", "late", "Refund pending"])
    if pick < 0.7:
        return [_random_value(r, depth + 1) for _ in range(r.randint(0, 3))]
    return {k: _random_value(r, depth + 1) for k in r.sample(["total", "items", "note", "sku", "priority", "missing"], r.randint(0, 4))}


def test_any_condition_over_any_values_ends_with_true_or_false():
    r = random.Random(11)
    for _ in range(3000):
        text = _random_condition(r)
        roots = {"previous": _random_value(r), "input": _random_value(r)}
        assert expr.holds(text, roots) in (True, False), text


def test_templates_keep_the_type_of_a_whole_placeholder_and_write_others_into_text():
    roots = {"previous": {"order": {"id": "1042"}, "total": 60, "ids": [1, 2]}, "input": "plain text"}
    assert expr.fill({"n": "{{previous.total}}", "s": "order {{previous.order.id}} of {{previous.total}}", "l": "{{previous.ids}}", "i": "{{input}}", "k": 5}, roots) == \
        {"n": 60, "s": "order 1042 of 60", "l": [1, 2], "i": "plain text", "k": 5}
    assert expr.fill("{{previous.nothing}} ok", roots) == " ok"
    assert expr.paths_in({"a": ["{{item.x}}", "{{ previous.y }}"]}) == ["item.x", "previous.y"]
