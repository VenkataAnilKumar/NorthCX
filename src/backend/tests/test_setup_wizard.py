"""WP 6.1 (O1): `scripts/setup.py` writes a working .env with generated secrets."""
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("northcx_setup", ROOT / "scripts" / "setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


def example_settings() -> set[str]:
    """Every setting `.env.example` documents, set or commented out."""
    names = set()
    for line in (ROOT / ".env.example").read_text().splitlines():
        line = line.lstrip("# ").strip()
        if "=" in line and line.split("=")[0].isupper() and line.split("=")[0].replace("_", "").isalnum():
            names.add(line.split("=")[0])
    return names


def run(tmp_path, *args):
    return setup.main(["--dir", str(tmp_path), *args])


def test_the_demo_choice_writes_a_complete_env_with_generated_secrets_that_only_the_owner_can_read(tmp_path, capsys):
    assert run(tmp_path, "--demo", "--non-interactive") == 0
    env = setup.parse_env((tmp_path / ".env").read_text())
    assert env["NORTHCX_DEMO"] == "1" and setup.problems(env) == []
    assert env["NORTHCX_DB_PASSWORD"].isalnum() and len(env["NORTHCX_DB_PASSWORD"]) == 24
    assert len(env["NORTHCX_API_KEY"]) >= 32 and env["NORTHCX_TOKEN_SECRET"] != env["NORTHCX_API_KEY"]
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
    out = capsys.readouterr().out
    assert env["NORTHCX_API_KEY"] not in out and env["NORTHCX_DB_PASSWORD"] not in out        # secrets go to the file, not the screen
    assert "docker compose up -d --build --wait" in out and "keyword rules, not an AI" in out


def test_two_runs_give_different_secrets(tmp_path):
    other = tmp_path / "b"
    other.mkdir()
    run(tmp_path, "--demo", "--non-interactive")
    run(other, "--demo", "--non-interactive")
    a, b = (setup.parse_env((d / ".env").read_text()) for d in (tmp_path, other))
    assert a["NORTHCX_API_KEY"] != b["NORTHCX_API_KEY"] and a["NORTHCX_DB_PASSWORD"] != b["NORTHCX_DB_PASSWORD"]


def test_it_never_overwrites_an_env_unless_told_to_and_then_keeps_the_old_one(tmp_path, capsys):
    (tmp_path / ".env").write_text("NORTHCX_API_KEY=mine\n")
    assert run(tmp_path, "--demo", "--non-interactive") == 1
    assert (tmp_path / ".env").read_text() == "NORTHCX_API_KEY=mine\n" and "already exists" in capsys.readouterr().out
    assert run(tmp_path, "--demo", "--non-interactive", "--force") == 0
    assert [p.read_text() for p in tmp_path.glob(".env.bak-*")] == ["NORTHCX_API_KEY=mine\n"]
    assert setup.parse_env((tmp_path / ".env").read_text())["NORTHCX_DEMO"] == "1"


def test_a_cloud_key_is_written_and_a_missing_model_choice_is_refused_without_asking(tmp_path, capsys):
    with pytest.raises(SystemExit, match="Choose a model"):
        run(tmp_path, "--non-interactive")
    assert not (tmp_path / ".env").exists()
    assert run(tmp_path, "--anthropic-key", "sk-test-key", "--connector-hosts", "api.shop.example") == 0
    env = setup.parse_env((tmp_path / ".env").read_text())
    assert env["ANTHROPIC_API_KEY"] == "sk-test-key" and env["NORTHCX_CONNECTOR_HOSTS"] == "api.shop.example" and "NORTHCX_DEMO" not in env


def test_a_local_model_writes_a_providers_file_the_server_accepts(tmp_path):
    from northcx.providers.config import parse_providers
    assert run(tmp_path, "--local-model-url", "http://host.docker.internal:11434/v1", "--local-model", "qwen-tools") == 0
    env = setup.parse_env((tmp_path / ".env").read_text())
    assert env["NORTHCX_PROVIDERS_FILE"] == "/config/providers.yaml" and "ANTHROPIC_API_KEY" not in env and setup.problems(env) == []
    text = (tmp_path / "config" / "providers.yaml").read_text()
    [entry] = parse_providers(text, {})
    assert entry.provider.name == "local" and entry.provider.default_model == "qwen-tools" and entry.default and entry.where == "local" and yaml.safe_load(text)["providers"][0]["allowInsecureHttp"] is True       # plain http to another host needs the flag
    with pytest.raises(SystemExit, match="--local-model"):
        run(tmp_path / "x", "--local-model-url", "http://localhost:11434/v1")


def test_it_writes_only_settings_that_env_example_documents_and_the_compose_file_passes_them_on(tmp_path):
    run(tmp_path, "--local-model-url", "http://host.docker.internal:11434/v1", "--local-model", "m", "--connector-hosts", "a.example")
    written = set(setup.parse_env((tmp_path / ".env").read_text()))
    assert written <= example_settings(), written - example_settings()
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]["backend"]
    assert "./config:/config:ro" in compose["volumes"]
    passed = set(compose["environment"]) | {"NORTHCX_DB_PASSWORD"}
    assert written <= passed, written - passed


def test_check_says_what_is_wrong_and_what_to_do(tmp_path, capsys):
    assert run(tmp_path, "--check") == 1 and "does not exist" in capsys.readouterr().out
    (tmp_path / ".env").write_text("NORTHCX_DB_PASSWORD=has-dash\nNORTHCX_API_KEY=short\n")
    assert run(tmp_path, "--check") == 1
    out = capsys.readouterr().out
    assert "letters and digits only" in out and "shorter than 24" in out and "No model is set" in out
    (tmp_path / ".env").unlink()
    run(tmp_path, "--demo", "--non-interactive")
    assert run(tmp_path, "--check") == 0 and "looks complete" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")
@pytest.mark.parametrize("args", [("--demo",), ("--local-model-url", "http://host.docker.internal:11434/v1", "--local-model", "m")])
def test_compose_accepts_the_file_it_wrote(tmp_path, args):
    run(tmp_path, *args, "--non-interactive")
    out = subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "--env-file", str(tmp_path / ".env"), "config", "-q"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr


def test_it_runs_as_a_script_with_only_the_standard_library(tmp_path):
    out = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "setup.py"), "--dir", str(tmp_path), "--demo", "--non-interactive"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and (tmp_path / ".env").exists()
