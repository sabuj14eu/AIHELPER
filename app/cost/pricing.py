"""Price table for paid providers.

USD per 1,000,000 tokens. These are estimates used for budget enforcement and
reporting; they are not an invoice. Prices change — treat this file as data,
review it when a provider changes its pricing, and record the date.

An unknown model is deliberately priced at the most expensive known rate for
its provider rather than at zero: a budget that under-counts is worse than one
that over-counts.
"""

from __future__ import annotations

from dataclasses import dataclass

VERIFIED_ON = "2026-09-07"


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float


PRICES: dict[str, dict[str, ModelPrice]] = {
    "openai": {
        "gpt-4o-mini": ModelPrice(0.15, 0.60),
        "gpt-4o": ModelPrice(2.50, 10.00),
        "gpt-4.1-mini": ModelPrice(0.40, 1.60),
        "gpt-4.1": ModelPrice(2.00, 8.00),
        "o4-mini": ModelPrice(1.10, 4.40),
    },
    "anthropic": {
        "claude-haiku-4-5": ModelPrice(1.00, 5.00),
        "claude-sonnet-5": ModelPrice(3.00, 15.00),
        "claude-opus-5": ModelPrice(15.00, 75.00),
    },
}

# What to charge when a provider or model is not in the table at all.
UNKNOWN_PRICE = ModelPrice(15.00, 75.00)


def _normalise(model: str) -> str:
    """Strip date suffixes: 'claude-sonnet-5-20260101' -> 'claude-sonnet-5'."""
    parts = model.split("-")
    if parts and parts[-1].isdigit() and len(parts[-1]) >= 6:
        return "-".join(parts[:-1])
    return model


def price_for(provider: str, model: str) -> ModelPrice:
    table = PRICES.get(provider.lower())
    if not table:
        return UNKNOWN_PRICE
    key = model.lower()
    if key in table:
        return table[key]
    normalised = _normalise(key)
    if normalised in table:
        return table[normalised]
    # Prefix match handles versioned names not yet listed.
    for name, price in table.items():
        if key.startswith(name):
            return price
    # Unknown model on a known provider: charge that provider's worst rate.
    return max(table.values(), key=lambda p: p.output_per_mtok)


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    price = price_for(provider, model)
    cost = (input_tokens / 1_000_000) * price.input_per_mtok + (
        output_tokens / 1_000_000
    ) * price.output_per_mtok
    return round(cost, 6)


def known_models() -> dict[str, list[str]]:
    return {provider: sorted(models) for provider, models in PRICES.items()}
