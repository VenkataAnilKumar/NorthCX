"""Building the model providers an installation may use, the same way for the server and the command line.

Providers come from the providers file (`NORTHCX_PROVIDERS_FILE`: local, private-cloud and public-cloud models side by side) and,
when `ANTHROPIC_API_KEY` is set and the file has no provider named `anthropic`, Claude is added as well. Errors are
`ConfigError` with a message that names the setting at fault; callers decide how to report them."""
from __future__ import annotations

from pathlib import Path

from northcx.llm import DEFAULT_MODEL, AnthropicHttpLLM, AnthropicLLM
from northcx.providers import ProviderRegistry
from northcx.secrets import ConfigError


def build_providers(providers_file: str, anthropic_key: str | None, anthropic_client: str = "sdk") -> tuple[ProviderRegistry, dict[str, str]]:
    """The provider registry and, for each provider name, where it runs (local, private-cloud or public-cloud)."""
    if anthropic_client not in ("sdk", "http"):
        raise ConfigError("NORTHCX_ANTHROPIC_CLIENT must be sdk or http")

    def make_claude(name: str = "anthropic", model: str | None = None, prices: dict | None = None):
        if name != "anthropic":
            raise ValueError("the anthropic provider must be named 'anthropic'")
        if not anthropic_key:
            raise ValueError("needs ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY_FILE)")
        args = dict(model=model or DEFAULT_MODEL, prices=prices)
        return AnthropicHttpLLM(anthropic_key, **args) if anthropic_client == "http" else AnthropicLLM(**args)

    providers = ProviderRegistry()  # bare model names go to the default provider
    entries = []
    if providers_file:
        from northcx.providers.config import parse_providers

        try:
            entries = parse_providers(Path(providers_file).read_text(), anthropic_factory=make_claude)
        except (OSError, ConfigError, ValueError) as e:
            raise ConfigError(f"NORTHCX_PROVIDERS_FILE: {e}") from e
    if anthropic_key and not any(e.provider.name == "anthropic" for e in entries):
        try:
            providers.register(make_claude(), default=not any(e.default for e in entries))
        except ValueError as e:
            raise ConfigError(str(e)) from e
    for e in entries:
        try:
            providers.register(e.provider, default=e.default)
        except ValueError as err:
            raise ConfigError(f"NORTHCX_PROVIDERS_FILE: {err}") from err
    return providers, {"anthropic": "public-cloud", **{e.provider.name: e.where for e in entries}}
