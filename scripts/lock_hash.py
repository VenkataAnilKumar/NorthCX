"""Print a fingerprint of the backend's declared dependencies (pyproject.toml). The lock files carry it, and a test compares."""
import hashlib
import json
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "src" / "backend" / "pyproject.toml"


def fingerprint(path: Path = PYPROJECT) -> str:
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    declared = {"requires-python": project.get("requires-python"), "dependencies": sorted(project.get("dependencies", [])),
                "optional": {k: sorted(v) for k, v in sorted(project.get("optional-dependencies", {}).items())}}
    return hashlib.sha256(json.dumps(declared, sort_keys=True).encode()).hexdigest()


if __name__ == "__main__":
    sys.stdout.write(fingerprint() + "\n")
