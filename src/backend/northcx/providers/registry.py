"""Several providers behind the one `LLM` interface the runtime already uses.

A model is named `provider:model` (for example `anthropic:claude-sonnet-5-5`). A name with no known provider prefix is a bare model name and goes
to the default provider, so every existing agent and setting keeps working. A prefix counts only if it names a registered provider, which
keeps model names that contain a colon (`llama3:8b`) intact."""
from __future__ import annotations

import dataclasses

from northcx.providers.base import Capabilities, ModelInfo, Price, Provider, ProviderError
from northcx.types import LLMRequest, LLMResponse


class UnknownModel(ValueError):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._default: str | None = None

    def register(self, provider: Provider, default: bool = False) -> None:
        if not provider.name or ":" in provider.name or not provider.name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"provider name '{provider.name}' must be letters, digits, '-' or '_'")
        if provider.name in self._providers:
            raise ValueError(f"provider '{provider.name}' is already registered")
        self._providers[provider.name] = provider
        if default or self._default is None:
            self._default = provider.name

    @property
    def names(self) -> list[str]:
        return sorted(self._providers)

    @property
    def default(self) -> Provider:
        if self._default is None:
            raise UnknownModel("no model provider is configured")
        return self._providers[self._default]

    def get(self, name: str) -> Provider:
        if name not in self._providers:
            raise UnknownModel(f"unknown provider '{name}'")
        return self._providers[name]

    def resolve(self, model: str | None) -> tuple[Provider, str | None]:
        """(provider, the model name that provider understands). None means the default provider's own default model."""
        if model and ":" in model:
            prefix, rest = model.split(":", 1)
            if prefix in self._providers:
                if not rest:
                    raise UnknownModel(f"'{model}' names a provider but no model")
                return self._providers[prefix], rest
        return self.default, model

    def qualify(self, model: str | None) -> str | None:
        """The full `provider:model` form of any model name (None when there is no model to name)."""
        provider, bare = self.resolve(model)
        bare = bare or provider.default_model
        return f"{provider.name}:{bare}" if bare else None

    def info(self, model: str | None) -> ModelInfo:
        provider, bare = self.resolve(model)
        bare = bare or provider.default_model or ""
        return ModelInfo(provider.name, bare, provider.capabilities, provider.prices.get(bare))

    def price_for(self, provider: str | None, model: str | None) -> Price | None:
        """The operator-supplied price of the model that actually answered (None when it has no price)."""
        p = self._providers.get(provider or "") or self.default
        return p.prices.get(model or p.default_model or "")

    def capabilities_for(self, model: str | None) -> Capabilities:
        return self.resolve(model)[0].capabilities

    async def complete(self, req: LLMRequest) -> LLMResponse:
        provider, bare = self.resolve(req.model)
        res = await provider.complete(dataclasses.replace(req, model=bare))
        if res.provider is None:
            res.provider = provider.name
        return res


def require_tools(registry: ProviderRegistry, model: str | None, needs_tools: bool) -> None:
    """Refuse an agent that needs tools on a model that cannot call them."""
    if needs_tools and not registry.capabilities_for(model).tools:
        info = registry.info(model)
        raise ProviderError(f"model '{info.provider}:{info.model}' cannot call tools, but this agent has tools")
