"""WP 6.5 (O7): the production compose setup does not start without sign-in."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker-compose.yml"


def test_the_server_exits_with_the_instruction_when_sign_in_is_required_and_no_key_exists():
    env = {k: v for k, v in os.environ.items() if not k.startswith("NORTHCX_") and k != "ANTHROPIC_API_KEY"}
    env.update({"NORTHCX_REQUIRE_AUTH": "1", "NORTHCX_DEMO": "1"})
    out = subprocess.run([sys.executable, "-m", "northcx"], cwd=ROOT / "src" / "backend", env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode != 0
    assert "NORTHCX_REQUIRE_AUTH=1 but no API key exists" in out.stdout + out.stderr and "NORTHCX_API_KEY" in out.stdout + out.stderr


def test_the_compose_backend_requires_sign_in_and_an_api_key():
    backend = yaml.safe_load(COMPOSE.read_text())["services"]["backend"]["environment"]
    assert backend["NORTHCX_REQUIRE_AUTH"] == "1"
    assert backend["NORTHCX_API_KEY"].startswith("${NORTHCX_API_KEY:?")        # compose itself refuses an empty key


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")
def test_compose_refuses_to_start_without_a_key_or_a_database_password(tmp_path):
    (tmp_path / ".env").write_text("")
    out = subprocess.run(["docker", "compose", "-f", str(COMPOSE), "--env-file", str(tmp_path / ".env"), "config", "-q"], capture_output=True, text=True, timeout=60)
    assert out.returncode != 0 and ("NORTHCX_DB_PASSWORD" in out.stderr or "NORTHCX_API_KEY" in out.stderr)
