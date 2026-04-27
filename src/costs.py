from __future__ import annotations

from decimal import Decimal

from config.app import (
    MODEL_COSTS,
    PROVIDER_MODEL_COSTS,
    ModelCost,
    normalize_model_cost_key,
)


def resolve_model_cost(provider: str, model: str) -> ModelCost | None:
    normalized_model = normalize_model_cost_key(model)
    provider_cost = PROVIDER_MODEL_COSTS.get(provider, {}).get(normalized_model)
    if provider_cost is not None:
        return provider_cost
    return MODEL_COSTS.get(normalized_model)


def calculate_costs(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_tokens: int | None,
    provider: str | None = None,
    model: str | None = None,
    model_cost: ModelCost | None = None,
) -> dict[str, Decimal]:
    cost = model_cost
    if cost is None and provider is not None and model is not None:
        cost = resolve_model_cost(provider, model)
    if cost is None:
        cost = ModelCost(input=0.0, output=0.0, cache_read=0.0)

    prompt = int(prompt_tokens or 0)
    completion = int(completion_tokens or 0)
    cached = int(cached_tokens or 0)
    uncached = max(prompt - cached, 0)

    input_cost = Decimal(uncached) * Decimal(str(cost.input)) / Decimal(1_000_000)
    cached_input_cost = (
        Decimal(cached) * Decimal(str(cost.cache_read)) / Decimal(1_000_000)
    )
    output_cost = Decimal(completion) * Decimal(str(cost.output)) / Decimal(1_000_000)

    return {
        "input_cost_usd": input_cost + cached_input_cost,
        "output_cost_usd": output_cost,
        "total_cost_usd": input_cost + cached_input_cost + output_cost,
    }
