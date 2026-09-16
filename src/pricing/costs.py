from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.config.app import PROVIDER_MAP

from .maps import (
    MAPS_LOCK,
    MODEL_COST_SOURCES,
    MODEL_COSTS,
    MODEL_SEGMENT_COSTS,
    PROVIDER_MODEL_COST_SOURCES,
    PROVIDER_MODEL_COSTS,
    PROVIDER_MODEL_SEGMENT_COSTS,
)
from .models import (
    ModelCost,
    ModelTier,
    build_segment_index,
    normalize_model_cost_key,
    resolve_effective_cost,
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
    source: str  # "litellm", "yaml", or future sources (e.g. "openrouter")


def resolve_cost_match(
    provider: str | None,
    model: str,
    model_costs: dict[str, ModelCost] | None = None,
    provider_model_costs: dict[str, dict[str, ModelCost]] | None = None,
    model_cost_sources: dict[str, str] | None = None,
    provider_model_cost_sources: dict[str, dict[str, str]] | None = None,
) -> CostMatch | None:
    """Resolve a model to a cost, honoring config overrides before LiteLLM.

    Priority: provider exact -> global exact -> provider containing
    (cheapest) -> global containing (cheapest).

    When explicit ``model_costs`` / ``provider_model_costs`` are supplied, pass
    the matching ``*_sources`` maps so provenance stays consistent with them;
    otherwise the runtime source maps are used.
    """
    using_runtime_maps = model_costs is None
    model_costs = MODEL_COSTS if model_costs is None else model_costs
    provider_model_costs = (
        PROVIDER_MODEL_COSTS if provider_model_costs is None else provider_model_costs
    )
    sources = MODEL_COST_SOURCES if model_cost_sources is None else model_cost_sources
    provider_sources = (
        PROVIDER_MODEL_COST_SOURCES
        if provider_model_cost_sources is None
        else provider_model_cost_sources
    )
    normalized_model = normalize_model_cost_key(model)
    provider_costs = (
        provider_model_costs.get(provider, {}) if provider is not None else {}
    )

    def _source(key: str, provider_scope: bool) -> str:
        if provider_scope:
            return provider_sources.get(provider or "", {}).get(key, "yaml")
        return sources.get(key, "yaml")

    provider_cost = provider_costs.get(normalized_model)
    if provider_cost is not None:
        return CostMatch(
            cost=provider_cost,
            key=normalized_model,
            scope="provider",
            source=_source(normalized_model, provider_scope=True),
        )

    global_cost = model_costs.get(normalized_model)
    if global_cost is not None:
        return CostMatch(
            cost=global_cost,
            key=normalized_model,
            scope="global",
            source=_source(normalized_model, provider_scope=False),
        )

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
        return CostMatch(
            cost=cost,
            key=key,
            scope="provider",
            source=_source(key, provider_scope=True),
        )

    global_match = model_segments.get(normalized_model)
    if global_match is not None:
        key, cost = global_match
        return CostMatch(
            cost=cost,
            key=key,
            scope="global",
            source=_source(key, provider_scope=False),
        )

    return None


def resolve_model_cost(provider: str, model: str) -> ModelCost | None:
    match = resolve_cost_match(provider, model)
    return match.cost if match is not None else None


@dataclass(frozen=True)
class ResolvedPricing:
    """Everything needed to price one usage row consistently.

    ``cost`` is already time-of-day resolved for the row timestamp, and
    ``multiplier`` is read alongside it so cost and multiplier cannot come from
    different config generations.
    """

    match: CostMatch | None
    cost: ModelCost
    multiplier: Decimal
    source: str | None


def resolve_pricing(
    provider: str | None,
    model: str,
    ts_micros: int,
    model_costs: dict[str, ModelCost] | None = None,
    provider_model_costs: dict[str, dict[str, ModelCost]] | None = None,
    model_cost_sources: dict[str, str] | None = None,
    provider_model_cost_sources: dict[str, dict[str, str]] | None = None,
) -> ResolvedPricing:
    """Resolve provider/model to a time-resolved flat cost + multiplier.

    The single hot-path entry point: ``calculate_costs`` and the snapshot both
    use its output, so a record cannot mix rates and a multiplier. The maps lock
    is held for the whole resolution so a concurrent config refresh (which swaps
    the maps and provider multipliers under the same lock) is never observed
    half-applied.
    """
    with MAPS_LOCK:
        match = resolve_cost_match(
            provider,
            model,
            model_costs,
            provider_model_costs,
            model_cost_sources,
            provider_model_cost_sources,
        )
        multiplier = get_provider_price_multiplier(provider)
    if match is None:
        return ResolvedPricing(
            match=None,
            cost=ModelCost(input=0.0, output=0.0, cache_read=0.0),
            multiplier=multiplier,
            source=None,
        )
    return ResolvedPricing(
        match=match,
        cost=resolve_effective_cost(match.cost, ts_micros),
        multiplier=multiplier,
        source=match.source,
    )


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


def _tier_prices(cost: ModelCost, tokens: int) -> ModelCost:
    """Resolve the effective flat prices for a token count (tiered or not)."""
    if not cost.tiers:
        return cost
    tier = _select_tier(cost.tiers, tokens)
    return ModelCost(
        input=tier.input,
        output=tier.output,
        cache_read=tier.cache_read,
        cache_write=tier.cache_write
        if tier.cache_write is not None
        else cost.cache_write,
    )


def resolve_token_rates(
    cost: ModelCost, tokens: int
) -> tuple[ModelCost, ModelTier | None]:
    """Return the flat rates actually applied for a token count, plus the tier.

    ``tokens`` is the total input token count used for tier selection. The
    returned tier is ``None`` for non-tiered pricing.
    """
    if not cost.tiers:
        return cost, None
    tier = _select_tier(cost.tiers, tokens)
    return _tier_prices(cost, tokens), tier


def compute_input_split(
    *,
    prompt_tokens: int | None,
    cached_tokens: int | None,
    cache_creation_tokens: int | None,
    cost: ModelCost,
    multiplier: Decimal,
) -> dict[str, Decimal]:
    """Split input cost into normal (cache-miss), cache-read, and cache-write.

    Used both by ``calculate_costs`` at record time and by the read path to
    recompute the split from a stored price snapshot. ``multiplier`` is the
    provider price multiplier applied at the time the pricing was in effect.
    """
    prompt = int(prompt_tokens or 0)
    cached = int(cached_tokens or 0)
    cache_created = int(cache_creation_tokens or 0)
    uncached = max(prompt - cached, 0)

    # Tiered pricing (litellm/dashscope): the tier is chosen by context
    # length — the total input token count.
    effective = _tier_prices(cost, uncached + cached + cache_created)

    normal_cost = (
        Decimal(uncached)
        * Decimal(str(effective.input))
        / Decimal(1_000_000)
        * multiplier
    )
    cache_read_cost = (
        Decimal(cached)
        * Decimal(str(effective.cache_read))
        / Decimal(1_000_000)
        * multiplier
    )
    # Cache-write tokens (Anthropic's cache_creation_input_tokens) have no
    # dedicated cost column, so they're folded into the input-cost bucket.
    cache_write_cost = (
        Decimal(cache_created)
        * Decimal(str(effective.cache_write or 0.0))
        / Decimal(1_000_000)
        * multiplier
    )
    return {
        "normal_input_cost_usd": normal_cost,
        "cache_read_cost_usd": cache_read_cost,
        "cache_write_cost_usd": cache_write_cost,
    }


def calculate_costs(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_tokens: int | None,
    cache_creation_tokens: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    model_cost: ModelCost | None = None,
    multiplier: Decimal | None = None,
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

    if multiplier is None:
        multiplier = get_provider_price_multiplier(provider)
    split = compute_input_split(
        prompt_tokens=prompt_tokens,
        cached_tokens=cached_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cost=cost,
        multiplier=multiplier,
    )

    # Tiered pricing (litellm/dashscope): the tier is chosen by context
    # length — the total input token count.
    effective = _tier_prices(cost, uncached + cached + cache_created)
    output_cost = (
        Decimal(completion) * Decimal(str(effective.output)) / Decimal(1_000_000)
    )

    total_input_cost = (
        split["normal_input_cost_usd"]
        + split["cache_read_cost_usd"]
        + split["cache_write_cost_usd"]
    )
    return {
        "input_cost_usd": total_input_cost,
        "output_cost_usd": output_cost * multiplier,
        "total_cost_usd": total_input_cost + output_cost * multiplier,
    }
