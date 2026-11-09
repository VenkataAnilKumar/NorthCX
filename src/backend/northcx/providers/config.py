"""The providers file: which model services this installation may use, loaded once at start.

```yaml
providers:
  - name: local                      # used in model names:  local:llama3.1:8b
    type: openai-compatible          # or: anthropic
    baseUrl: http://ollama:11434/v1
    allowInsecureHttp: true          # only on a trusted private network
    apiKeyEnv: LOCAL_LLM_KEY         # name of an environment variable (or apiKeyFile); a key is never written in this file
    defaultModel: llama3.1:8b
    default: true                    # the provider that bare model names go to
    where: local                     # local | private-cloud | public-cloud  (used by hybrid selection)
    capabilities: {tools: true, parallelTools: true, images: false, maxContextTokens: 128000}
    prices: {llama3.1:8b: {inputPerMillion: 0, outputPerMillion: 0, currency: USD}}
```"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from northcx.providers.base import Capabilities, Price, Provider
from northcx.providers.openai_compat import OpenAICompatibleLLM
from northcx.secrets import ConfigError

WHERE = ("local", "private-cloud", "public-cloud")
_KNOWN = {"name", "type", "baseUrl", "allowInsecureHttp", "apiKeyEnv", "apiKeyFile", "defaultModel", "default", "where", "capabilities", "prices", "timeoutSeconds", "maxTokensParam"}


@dataclass
class ProviderEntry:
    provider: Provider
    default: bool
    where: str


def _price(model: str, p: Any) -> Price:
    if not isinstance(p, dict) or "inputPerMillion" not in p or "outputPerMillion" not in p:
        raise ConfigError(f"price for '{model}' needs inputPerMillion and outputPerMillion")
    try:
        return Price(float(p["inputPerMillion"]), float(p["outputPerMillion"]), str(p.get("currency", "USD")).upper())
    except (TypeError, ValueError) as e:
        raise ConfigError(f"price for '{model}' must be numbers") from e


def parse_providers(text: str, env: Mapping[str, str] | None = None, anthropic_factory=None) -> list[ProviderEntry]:
    env = os.environ if env is None else env
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"providers file is not valid YAML: {e}") from e
    items = doc.get("providers") if isinstance(doc, dict) else None
    if not isinstance(items, list) or not items:
        raise ConfigError("providers file needs a non-empty 'providers' list")
    out: list[ProviderEntry] = []
    seen: set[str] = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ConfigError(f"providers[{i}] must be a mapping")
        if "apiKey" in it or "api_key" in it:
            raise ConfigError(f"providers[{i}]: never put a key in the file; use apiKeyEnv or apiKeyFile")
        unknown = set(it) - _KNOWN
        if unknown:
            raise ConfigError(f"providers[{i}]: unknown setting(s) {sorted(unknown)}")
        name = str(it.get("name", ""))
        if not name or name in seen:
            raise ConfigError(f"providers[{i}]: name is missing or repeated")
        seen.add(name)
        where = str(it.get("where", "public-cloud"))
        if where not in WHERE:
            raise ConfigError(f"provider '{name}': where must be one of {', '.join(WHERE)}")
        caps_in = it.get("capabilities") or {}
        caps = Capabilities(tools=bool(caps_in.get("tools", True)), parallel_tools=bool(caps_in.get("parallelTools", True)), images=bool(caps_in.get("images", False)),
                            documents=bool(caps_in.get("documents", False)), max_context_tokens=caps_in.get("maxContextTokens"))
        prices = {m: _price(m, p) for m, p in (it.get("prices") or {}).items()}
        kind = it.get("type")
        if kind == "openai-compatible":
            key = None
            if it.get("apiKeyEnv") and it.get("apiKeyFile"):
                raise ConfigError(f"provider '{name}': set only one of apiKeyEnv and apiKeyFile")
            if it.get("apiKeyEnv"):
                key = env.get(str(it["apiKeyEnv"])) or None
                if key is None:
                    raise ConfigError(f"provider '{name}': environment variable {it['apiKeyEnv']} is not set")
            elif it.get("apiKeyFile"):
                try:
                    key = Path(str(it["apiKeyFile"])).read_text().strip() or None
                except OSError as e:
                    raise ConfigError(f"provider '{name}': cannot read apiKeyFile ({e.strerror})") from e
            try:
                prov: Provider = OpenAICompatibleLLM(name, str(it.get("baseUrl", "")), it.get("defaultModel"), key, caps, prices,
                                                     float(it.get("timeoutSeconds", 60)), bool(it.get("allowInsecureHttp", False)), str(it.get("maxTokensParam", "max_tokens")))
            except ValueError as e:
                raise ConfigError(f"provider '{name}': {e}") from e
        elif kind == "anthropic":
            if anthropic_factory is None:
                raise ConfigError(f"provider '{name}': the anthropic type is supplied by the server")
            try:
                prov = anthropic_factory(name, it.get("defaultModel"), prices)
            except ValueError as e:
                raise ConfigError(f"provider '{name}': {e}") from e
        else:
            raise ConfigError(f"provider '{name}': type must be openai-compatible or anthropic")
        out.append(ProviderEntry(prov, bool(it.get("default", False)), where))
    if sum(e.default for e in out) > 1:
        raise ConfigError("only one provider can be the default")
    return out
