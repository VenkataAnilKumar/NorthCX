"""The backend's lock files must match pyproject.toml, and every pinned package must carry hashes."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "src" / "backend"


def _fingerprint() -> str:
    spec = importlib.util.spec_from_file_location("lock_hash", ROOT / "scripts" / "lock_hash.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fingerprint()


def test_the_lock_files_match_the_declared_dependencies():
    for name in ("requirements.lock", "requirements-dev.lock"):
        text = (BACKEND / name).read_text()
        m = re.search(r"^# pyproject-fingerprint: (\w+)$", text, re.M)
        assert m, f"{name} has no fingerprint; run scripts/lock.sh"
        assert m.group(1) == _fingerprint(), f"{name} is older than pyproject.toml; run scripts/lock.sh"


def test_every_pinned_package_is_exact_and_hashed():
    for name in ("requirements.lock", "requirements-dev.lock"):
        blocks = re.split(r"\n(?=[A-Za-z0-9_.\-\[\]]+==)", (BACKEND / name).read_text())[1:]
        assert len(blocks) > 20
        for b in blocks:
            assert re.match(r"[^\s=]+==[^\s]+ ", b), b[:60]
            assert "--hash=sha256:" in b, f"{name}: {b.splitlines()[0]} has no hash"


def test_the_runtime_lock_has_no_test_tools_and_the_dev_lock_has_them():
    runtime = (BACKEND / "requirements.lock").read_text()
    dev = (BACKEND / "requirements-dev.lock").read_text()
    assert "\npytest==" not in runtime and "\npytest==" in dev


def test_the_container_image_installs_from_the_lock_with_hashes_required():
    docker = (BACKEND / "Dockerfile").read_text()
    assert "--require-hashes" in docker and "requirements.lock" in docker
