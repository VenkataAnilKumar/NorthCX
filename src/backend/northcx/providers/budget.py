"""Starting with a money budget is refused unless every provider's default model has a price in the budget currency."""
from __future__ import annotations

from northcx.providers.registry import ProviderRegistry


def check_money_budget(providers: ProviderRegistry, currency: str) -> None:
    """Fail closed: a model with no price would spend without ever counting against the budget."""
    for name in providers.names:
        prov = providers.get(name)
        price = prov.prices.get(prov.default_model or "")
        if price is None or price.currency != currency:
            raise ValueError(f"provider '{name}' has no price for its default model in {currency}; add one in the providers file (prices), "
                             "or for Claude a `type: anthropic` entry named anthropic")
