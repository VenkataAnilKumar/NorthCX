"""Release hygiene: one version everywhere, licences declared, the files a project needs are present."""
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from examples.support_agent import support_agent
from northcx import __version__
from northcx.access import AccessControl
from northcx.llm import ScriptedLLM
from northcx.runtime import Runtime
from northcx.server import create_app
from northcx.store import InMemoryStore
from northcx.trace import TraceStore

ROOT = Path(__file__).resolve().parents[3]


def pep440_to_semver(v: str) -> str:
    return re.sub(r"(\d+\.\d+\.\d+)(?:rc(\d+))?", lambda m: m.group(1) + (f"-rc.{m.group(2)}" if m.group(2) else ""), v)


def test_every_part_of_the_product_has_the_same_version_and_licence():
    py = (ROOT / "src/backend/pyproject.toml").read_text()
    assert f'version = "{__version__}"' in py and 'license = { text = "Apache-2.0" }' in py
    for pkg in ("web", "sdk"):
        data = json.loads((ROOT / f"src/{pkg}/package.json").read_text())
        assert data["version"] == pep440_to_semver(__version__) and data["license"] == "Apache-2.0", pkg
    assert re.search(rf"## \[{re.escape(pep440_to_semver(__version__))}\]", (ROOT / "CHANGELOG.md").read_text())


def test_the_files_an_open_source_project_needs_are_there():
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY.md", "SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md", "README.md"):
        assert (ROOT / name).is_file() and (ROOT / name).stat().st_size > 100, name
    assert "Apache License" in (ROOT / "LICENSE").read_text()[:200]


def test_the_version_is_shown_to_signed_in_users_only():
    rt = Runtime(ScriptedLLM([]), InMemoryStore(), TraceStore())
    c = TestClient(create_app(rt, rt.traces, {"support": support_agent()}, access=AccessControl(bootstrap_key="boot" * 10)))
    assert c.get("/health").json() == {"ok": True}                                            # nothing about the version to anonymous callers
    assert c.get("/v1/me", headers={"authorization": "Bearer " + "boot" * 10}).json()["serverVersion"] == __version__
