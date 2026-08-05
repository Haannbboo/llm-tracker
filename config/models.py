"""Shared data classes and utilities for model cost and provider configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_TRACKER_HOME = "~/.llm-tracker"
TRACKER_HOME_ENV_VAR = "LLM_TRACKER_HOME"


def expand_path(path: str) -> str:
    return os.path.expanduser(path)


def get_tracker_home() -> str:
    return expand_path(os.environ.get(TRACKER_HOME_ENV_VAR, DEFAULT_TRACKER_HOME))


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    price_multiplier: float = 1.0
    api_key: str | None = field(default=None, repr=False)
    auth_scheme: str = "bearer"  # "bearer" or "x-api-key" (Anthropic-native)


@dataclass(frozen=True)
class ModelTier:
    """Pricing tier applied when token counts fall within [min_tokens, max_tokens).

    Bounds are in tokens (litellm `range`). Prices are per-million tokens.
    """

    min_tokens: int
    max_tokens: int | None
    input: float
    output: float
    cache_read: float
    cache_write: float | None = None


@dataclass(frozen=True)
class ModelCost:
    input: float
    output: float
    cache_read: float
    cache_write: float | None = None
    tiers: tuple[ModelTier, ...] = ()


@dataclass(frozen=True)
class ResolvedCost:
    cost: ModelCost
    source: str


@dataclass(frozen=True)
class ResolvedCosts:
    global_costs: dict[str, ResolvedCost]
    provider_costs: dict[str, dict[str, ResolvedCost]]


def normalize_model_cost_key(model_name: str) -> str:
    return model_name.lower()


def cost_rank(cost: ModelCost) -> tuple[float, ...]:
    """Ordering key for comparing model costs, cheapest first."""
    return (
        cost.input + cost.output + cost.cache_read + (cost.cache_write or 0.0),
        cost.input,
        cost.output,
        cost.cache_read,
        cost.cache_write or 0.0,
    )


def build_segment_index(
    costs: dict[str, ModelCost],
) -> dict[str, tuple[str, ModelCost]]:
    """Index pricing keys by trailing path segment, cheapest per segment.

    Enables O(1) containing-name resolution for vendor-prefixed keys like
    'openrouter/xiaomi/mimo-v2.5-pro' without scanning the full map on every
    lookup. On equal ranks the first key wins, matching min()'s tie-break.
    """
    index: dict[str, tuple[str, ModelCost]] = {}
    for key, cost in costs.items():
        segment = key.rsplit("/", maxsplit=1)[-1]
        existing = index.get(segment)
        if existing is None or cost_rank(cost) < cost_rank(existing[1]):
            index[segment] = (key, cost)
    return index
