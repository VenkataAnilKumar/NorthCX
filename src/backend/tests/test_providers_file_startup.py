"""The server starts from a providers file with no Anthropic key, and refuses a bad file with a clear message."""
from types import SimpleNamespace

import pytest

from northcx.bootstrap.settings import load_settings

FILE = """
providers:
  - name: local
    type: openai-compatible
    baseUrl: http://localhost:11434/v1
    defaultModel: llama3.1:8b
    default: true
    where: local
"""


def env(monkeypatch, tmp_path, text):
    for k in ("NORTHCX_DEMO", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE", "NORTHCX_MODEL_FALLBACKS"):
        monkeypatch.delenv(k, raising=False)
    f = tmp_path / "providers.yaml"
    f.write_text(text)
    monkeypatch.setenv("NORTHCX_PROVIDERS_FILE", str(f))
    monkeypatch.setenv("NORTHCX_API_KEY", "a-long-enough-key-123456")


def test_a_providers_file_replaces_the_need_for_an_anthropic_key(monkeypatch, tmp_path):
    env(monkeypatch, tmp_path, FILE)
    c = SimpleNamespace()
    load_settings(c)
    assert c.providers.names == ["local"] and c.providers.qualify(None) == "local:llama3.1:8b" and c.provider_where == {"anthropic": "public-cloud", "local": "local"}


def test_both_configured_means_the_flagged_provider_is_the_default(monkeypatch, tmp_path):
    env(monkeypatch, tmp_path, FILE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0123456789")
    c = SimpleNamespace()
    load_settings(c)
    assert c.providers.names == ["anthropic", "local"] and c.providers.qualify(None) == "local:llama3.1:8b" and c.providers.qualify("claude-x") == "local:claude-x"
    assert c.providers.qualify("anthropic:claude-x") == "anthropic:claude-x"


def test_a_bad_file_stops_the_server_with_the_reason(monkeypatch, tmp_path):
    env(monkeypatch, tmp_path, FILE.replace("type: openai-compatible", "type: nonsense"))
    with pytest.raises(SystemExit) as e:
        load_settings(SimpleNamespace())
    assert "type must be" in str(e.value)
