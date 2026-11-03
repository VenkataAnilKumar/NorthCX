"""The server must start exactly the way the Docker Compose stack starts it: every listed setting present, most of them blank."""
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from northcx.secrets import normalise_environment

ROOT = Path(__file__).resolve().parents[3]


def test_blank_settings_count_as_not_set():
    env = {"NORTHCX_A": "", "NORTHCX_B": "   ", "NORTHCX_C": "x", "OTHER": "", "NORTHCX_D_FILE": ""}
    assert sorted(normalise_environment(env)) == ["NORTHCX_A", "NORTHCX_B", "NORTHCX_D_FILE"]
    assert env == {"NORTHCX_C": "x", "OTHER": ""}


def compose_settings() -> list[str]:
    block = (ROOT / "docker-compose.yml").read_text().split("  backend:")[1].split("  web:")[0]
    return re.findall(r"^\s+(NORTHCX_[A-Z0-9_]+):", block, re.M)


def test_every_documented_setting_is_passed_through_compose():
    """Anything the guides tell an operator to set must reach the container; otherwise the setting silently does nothing."""
    passed = set(compose_settings())
    documented = set(re.findall(r"`(NORTHCX_[A-Z0-9_]+)`", (ROOT / "docs/08-implementation/NorthCX_Deployment-Guide.md").read_text()))
    documented = {d for d in documented if not d.endswith("_FILE") and not d.startswith("NORTHCX_SECRET_") and d not in {"NORTHCX_DB_PASSWORD", "NORTHCX_API_URL", "NORTHCX_BACKEND_PORT", "NORTHCX_WEB_PORT", "NORTHCX_BIND", "NORTHCX_TRACE_DIR"}}  # compose-level or in-memory-only settings
    assert not (documented - passed), sorted(documented - passed)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_server_starts_with_every_compose_setting_present_and_blank():
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("NORTHCX_")}
    env.update({name: "" for name in compose_settings()})
    env.update({"NORTHCX_DEMO": "1", "NORTHCX_API_KEY": "k" * 32, "PORT": str(port), "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    p = subprocess.Popen([sys.executable, "-m", "northcx"], env=env, cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 40
        ready = False
        while time.time() < deadline and p.poll() is None:
            try:
                ready = urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1).status == 200
                break
            except Exception:
                time.sleep(0.3)
        assert ready, (p.stdout.read() if p.poll() is not None else "did not become ready")
    finally:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
