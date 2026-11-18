"""Documentation that is generated from, or checked against, the code must not drift."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_route_reference_matches_the_servers_permission_table():
    gen = load("gen_route_reference")
    assert gen.current() == gen.render(), "NorthCX_API-Design.md is out of date: run python scripts/gen_route_reference.py"


def test_every_database_table_is_described_in_the_schema_document():
    tables = set()
    for p in (ROOT / "src" / "backend" / "northcx" / "db" / "migrations" / "versions").glob("*.py"):
        tables |= set(re.findall(r'create_table\(\s*"([a-z_]+)"', p.read_text()))
    doc = (ROOT / "docs" / "11-operations" / "NorthCX_Database-Schema.md").read_text()
    assert sorted(t for t in tables if f"`{t}`" not in doc) == []


def test_every_setting_the_code_reads_is_in_the_deployment_guide():
    names = set()
    for p in (ROOT / "src" / "backend" / "northcx").rglob("*.py"):
        names |= set(re.findall(r'["\'](NORTHCX_[A-Z0-9_]+)["\']', p.read_text()))
    guide = (ROOT / "docs" / "11-operations" / "NorthCX_Deployment-Guide.md").read_text()
    assert sorted(n for n in names if not n.endswith("_FILE") and n not in guide) == []


def test_every_setting_the_code_reads_is_in_the_example_environment_file():
    names = set()
    for p in (ROOT / "src" / "backend" / "northcx").rglob("*.py"):
        names |= set(re.findall(r'["\'](NORTHCX_[A-Z0-9_]+)["\']', p.read_text()))
    example = (ROOT / ".env.example").read_text()
    assert sorted(n for n in names if not n.endswith("_FILE") and n not in example) == []


def test_decision_log_numbers_are_unique_and_complete():
    nums = [int(n) for n in re.findall(r"^\| (\d+) \|", (ROOT / "docs" / "12-project" / "NorthCX_Decision-Log.md").read_text(), re.M)]
    assert len(nums) == len(set(nums)), "a decision number is used twice"
    assert sorted(nums) == list(range(1, len(nums) + 1)), "a decision number is missing"


def test_the_generated_api_reference_is_up_to_date():
    gen = load("gen_api_reference")
    for name, text in gen.outputs().items():
        assert (ROOT / "docs" / "api" / name).read_text() == text, f"docs/api/{name} is out of date: run python scripts/gen_api_reference.py"


def test_every_route_in_the_permission_table_is_in_the_api_reference_with_the_same_permission():
    import json
    import re

    from northcx.server import ROUTE_PERMISSIONS

    schema = json.loads((ROOT / "docs" / "api" / "openapi.json").read_text())
    concrete = [(m.upper(), re.sub(r"\{[^}]+\}", "x1", p), op) for p, ops in schema["paths"].items() for m, op in ops.items()]
    missing = []
    for method, regex, perm in ROUTE_PERMISSIONS:
        hits = [op for m, p, op in concrete if m == method and re.fullmatch(regex, p)]
        if not hits or any(op["x-required-permission"] != perm for op in hits if op["x-required-permission"] is not None):
            missing.append((method, regex))
    assert missing == []
    assert [(m, p) for m, p, op in concrete if not op.get("x-public") and not op["x-required-permission"]] == []  # nothing is served without being classified
