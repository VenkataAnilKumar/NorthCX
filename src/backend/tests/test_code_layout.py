"""Rules for how the HTTP layer is organised (work package WP0.1): small modules, one router per area, no unused or missing dependencies."""
import ast
import re
from pathlib import Path

NORTHCX = Path(__file__).resolve().parents[1] / "northcx"
LIMIT = 600


def lines(p: Path) -> int:
    return len(p.read_text().splitlines())


def test_no_module_in_the_http_layer_is_longer_than_the_limit():
    files = [NORTHCX / "server.py", *sorted((NORTHCX / "api").rglob("*.py")), *sorted((NORTHCX / "db" / "stores").glob("*.py")), NORTHCX / "__main__.py", *sorted((NORTHCX / "bootstrap").glob("*.py"))]
    too_long = {str(p.relative_to(NORTHCX)): lines(p) for p in files if lines(p) > LIMIT}
    assert too_long == {}, f"split these (limit {LIMIT} lines): {too_long}"


def test_every_router_module_has_a_register_function_and_is_wired_in():
    server = (NORTHCX / "server.py").read_text()
    routers = sorted(p.stem for p in (NORTHCX / "api" / "routers").glob("*.py") if p.stem != "__init__")
    assert len(routers) >= 20
    for name in routers:
        tree = ast.parse((NORTHCX / "api" / "routers" / f"{name}.py").read_text())
        reg = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "register"]
        assert len(reg) == 1 and [a.arg for a in reg[0].args.args] == ["app", "d"], name
        assert f"_{name}_router.register(app, deps)" in server, f"{name} is not registered by create_app"


def test_the_dependencies_object_has_exactly_the_fields_the_routers_use():
    fields = set(re.findall(r"^    (\w+): ", (NORTHCX / "api" / "deps.py").read_text().split("class AppDeps:")[1], re.M))
    used = set()
    for p in (NORTHCX / "api" / "routers").glob("*.py"):
        used |= set(re.findall(r"= d\.(\w+)", p.read_text()))
    assert used <= fields, f"routers use fields AppDeps does not have: {sorted(used - fields)}"
    assert fields <= used, f"AppDeps has fields no router uses: {sorted(fields - used)}"
    server = (NORTHCX / "server.py").read_text()
    built = set(re.findall(r"(\w+)=\1\b", re.search(r"deps = AppDeps\((.*?)\)\n", server, re.S).group(1)))
    assert built == fields, "create_app must supply every field"


def test_moved_modules_use_absolute_imports_everywhere():
    """A relative import inside a function body is only checked when that code runs; moving a module one level deeper silently breaks it."""
    offenders = []
    for folder in (NORTHCX / "api", NORTHCX / "db" / "stores", NORTHCX / "bootstrap"):
        for p in folder.rglob("*.py"):
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.ImportFrom) and node.level > 0 and not (p.name == "__init__.py" and node.level == 1):
                    offenders.append(f"{p.relative_to(NORTHCX)}:{node.lineno}")
    assert offenders == [], offenders


def test_every_module_in_the_moved_packages_imports_cleanly_including_lazy_imports():
    import importlib
    import importlib.util
    for folder in (NORTHCX / "api", NORTHCX / "db" / "stores", NORTHCX / "bootstrap"):
        for p in folder.rglob("*.py"):
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith("northcx"):
                    assert importlib.util.find_spec(node.module) is not None, f"{p.relative_to(NORTHCX)}:{node.lineno} imports {node.module}"
