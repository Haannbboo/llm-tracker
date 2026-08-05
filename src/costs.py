from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from config.app import (
    MODEL_COSTS,
    MODEL_SEGMENT_COSTS,
    PROVIDER_MAP,
    PROVIDER_MODEL_COSTS,
    PROVIDER_MODEL_SEGMENT_COSTS,
    ModelCost,
    ModelTier,
    build_segment_index,
    normalize_model_cost_key,
)


def get_provider_price_multiplier(provider: str | None) -> Decimal:
    if not provider:
        return Decimal("1.0")
    provider_config = PROVIDER_MAP.get(provider)
    if provider_config is None:
        return Decimal("1.0")
    return Decimal(str(provider_config.price_multiplier))


@dataclass(frozen=True)
class CostMatch:
    cost: ModelCost
    key: str
    scope: str  # "provider" or "global"


def resolve_cost_match(
    provider: str | None,
    model: str,
    model_costs: dict[str, ModelCost] | None = None,
    provider_model_costs: dict[str, dict[str, ModelCost]] | None = None,
) -> CostMatch | None:
    """Resolve a model to a cost, honoring config overrides before LiteLLM.

    Priority: provider exact -> global exact -> provider containing
    (cheapest) -> global containing (cheapest).
    """
    using_runtime_maps = model_costs is None
    model_costs = MODEL_COSTS if model_costs is None else model_costs
    provider_model_costs = (
        PROVIDER_MODEL_COSTS if provider_model_costs is None else provider_model_costs
    )
    normalized_model = normalize_model_cost_key(model)
    provider_costs = (
        provider_model_costs.get(provider, {}) if provider is not None else {}
    )

    provider_cost = provider_costs.get(normalized_model)
    if provider_cost is not None:
        return CostMatch(
            cost=provider_cost,
            key=normalized_model,
            scope="provider",
        )

    global_cost = model_costs.get(normalized_model)
    if global_cost is not None:
        return CostMatch(cost=global_cost, key=normalized_model, scope="global")

    if using_runtime_maps:
        # Hot record path: use the prebuilt segment indexes to avoid a full
        # scan of the LiteLLM pricing map on every lookup that misses an exact
        # key.
        provider_segments = (
            PROVIDER_MODEL_SEGMENT_COSTS.get(provider, {})
            if provider is not None
            else {}
        )
        model_segments = MODEL_SEGMENT_COSTS
    else:
        provider_segments = build_segment_index(provider_costs)
        model_segments = build_segment_index(model_costs)

    provider_match = provider_segments.get(normalized_model)
    if provider_match is not None:
        key, cost = provider_match
        return CostMatch(cost=cost, key=key, scope="provider")

    global_match = model_segments.get(normalized_model)
    if global_match is not None:
        key, cost = global_match
        return CostMatch(cost=cost, key=key, scope="global")

    return None


def resolve_model_cost(provider: str, model: str) -> ModelCost | None:
    match = resolve_cost_match(provider, model)
    return match.cost if match is not None else None


def _select_tier(tiers: tuple[ModelTier, ...], tokens: int) -> ModelTier:
    """Pick the pricing tier whose [min_tokens, max_tokens) range holds `tokens`.

    Falls back to the last tier when tokens exceed every range, and to the
    first tier when tokens are below every range.
    """
    chosen = tiers[0]
    for tier in tiers:
        if tokens < tier.min_tokens:
            break
        chosen = tier
        if tier.max_tokens is None or tokens < tier.max_tokens:
            break
    return chosen


def calculate_costs(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_tokens: int | None,
    cache_creation_tokens: int | None = None,
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
    cache_created = int(cache_creation_tokens or 0)
    uncached = max(prompt - cached, 0)

    # Tiered pricing (litellm/dashscope): the tier is chosen by context
    # length — the total input token count.
    tier = None
    if cost.tiers:
        tier = _select_tier(cost.tiers, uncached + cached + cache_created)

    input_price = tier.input if tier is not None else cost.input
    cache_read_price = tier.cache_read if tier is not None else cost.cache_read
    output_price = tier.output if tier is not None else cost.output
    cache_write_price = (
        tier.cache_write
        if tier is not None and tier.cache_write is not None
        else cost.cache_write
    )

    input_cost = Decimal(uncached) * Decimal(str(input_price)) / Decimal(1_000_000)
    cached_input_cost = (
        Decimal(cached) * Decimal(str(cache_read_price)) / Decimal(1_000_000)
    )
    # Cache-write tokens (Anthropic's cache_creation_input_tokens) have no
    # dedicated cost column, so they're folded into the input-cost bucket.
    cache_write_cost = (
        Decimal(cache_created)
        * Decimal(str(cache_write_price or 0.0))
        / Decimal(1_000_000)
    )
    output_cost = Decimal(completion) * Decimal(str(output_price)) / Decimal(1_000_000)
    multiplier = get_provider_price_multiplier(provider)

    total_input_cost = input_cost + cached_input_cost + cache_write_cost
    return {
        "input_cost_usd": total_input_cost * multiplier,
        "output_cost_usd": output_cost * multiplier,
        "total_cost_usd": (total_input_cost + output_cost) * multiplier,
    }
