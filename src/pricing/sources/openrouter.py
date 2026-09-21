"""OpenRouter price source.

Fetches OpenRouter's public model catalog and parses the legacy flat ``pricing``
object (``prompt``/``completion``/``input_cache_read`` plus ``pricing.overrides``
time windows), which is what ``/api/v1/models`` currently serves. Prices are
dollar-per-token strings; we store per-million. Entries are global (OpenRouter
vendor names do not map to this tracker's configured provider names).
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import ModelCost, ModelTier, TimeRate, normalize_model_cost_key
from .base import (
    REQUEST_TIMEOUT,
    SourceEntry,
    cache_is_fresh,
    fetch_json,
    load_cache_json,
    save_cache_json,
)

log = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
CACHE_NAME = "openrouter"
DEFAULT_TTL_SECONDS = 6 * 60 * 60

# Non-base variants we don't want to price as distinct models.
_SKIP_MARKERS = (":free", ":batch", ":exacto", ":thinking", ":online", ":nitro")
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _is_base_variant(model_id: str) -> bool:
    if model_id.startswith("~"):
        return False
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _SKIP_MARKERS)


def _per_million(value: Any) -> float | None:
    """Convert a dollar-per-token string/number to per-million, rounded."""
    if value is None:
        return None
    try:
        return round(float(value) * 1_000_000, 6)
    except (TypeError, ValueError):
        return None


def _hhmm_to_minutes(value: Any) -> int:
    """Parse an OpenRouter HHMM UTC value (0000-2359) to minutes since midnight."""
    ivalue = int(value)
    if ivalue < 0 or ivalue > 2359 or ivalue % 100 > 59:
        raise ValueError(f"invalid HHMM value: {value!r}")
    return (ivalue // 100) * 60 + (ivalue % 100)


def _parse_window(raw: dict, base_cache_write: float | None = None) -> TimeRate | None:
    start_raw = raw.get("utc_start")
    end_raw = raw.get("utc_end")
    if start_raw is None and end_raw is None:
        # Whole-day window (e.g. weekend-only rates carry utc_days with no
        # start/end). Represent as 00:00 -> 24:00.
        start, end = 0, 24 * 60
    elif start_raw is None or end_raw is None:
        return None
    else:
        try:
            start = _hhmm_to_minutes(start_raw)
            end = _hhmm_to_minutes(end_raw)
        except (TypeError, ValueError):
            return None
        if start == end:
            return None

    days: frozenset[int] | None = None
    days_raw = raw.get("utc_days")
    if isinstance(days_raw, list) and days_raw:
        try:
            days = frozenset(_WEEKDAYS[str(day).lower()] for day in days_raw)
        except KeyError:
            return None

    input_cost = _per_million(raw.get("prompt"))
    output_cost = _per_million(raw.get("completion"))
    if input_cost is None and output_cost is None:
        return None
    cache_read = _per_million(raw.get("input_cache_read"))
    cache_write = _per_million(raw.get("input_cache_write"))

    return TimeRate(
        days=days,
        start_minute=start,
        end_minute=end,
        cost=ModelCost(
            input=input_cost or 0.0,
            output=output_cost or 0.0,
            cache_read=cache_read or 0.0,
            cache_write=(cache_write if cache_write is not None else base_cache_write),
        ),
    )


def _build_token_tiers(
    base_input: float | None,
    base_output: float | None,
    base_cache_read: float | None,
    base_cache_write: float | None,
    raws: list[dict],
) -> tuple[ModelTier, ...]:
    """Build context tiers from `min_prompt_tokens` pricing overrides."""
    steps: list[tuple[int, dict]] = []
    for raw in raws:
        try:
            min_tokens = int(raw["min_prompt_tokens"])
        except (KeyError, TypeError, ValueError):
            continue
        if min_tokens <= 0:
            continue
        steps.append((min_tokens, raw))
    if not steps:
        return ()
    # A repeated threshold would build a zero-width tier; last one wins.
    steps = list({min_tokens: raw for min_tokens, raw in steps}.items())
    steps.sort(key=lambda step: step[0])

    def rate(value: Any, base: float | None) -> float:
        amount = _per_million(value)
        return amount if amount is not None else base or 0.0

    def opt_rate(value: Any, base: float | None) -> float | None:
        amount = _per_million(value)
        return amount if amount is not None else base

    # Pad with the base rates so the first tier falls out of the same loop.
    padded = [(0, {})] + steps
    tiers = []
    for index, (min_tokens, raw) in enumerate(padded):
        max_tokens = padded[index + 1][0] if index + 1 < len(padded) else None
        tiers.append(
            ModelTier(
                min_tokens=min_tokens,
                max_tokens=max_tokens,
                input=rate(raw.get("prompt"), base_input),
                output=rate(raw.get("completion"), base_output),
                cache_read=rate(raw.get("input_cache_read"), base_cache_read),
                cache_write=opt_rate(raw.get("input_cache_write"), base_cache_write),
            )
        )
    return tuple(tiers)


def _parse_model_entry(entry: dict) -> tuple[str, ModelCost] | None:
    model_id = entry.get("id")
    if not isinstance(model_id, str) or not model_id or not _is_base_variant(model_id):
        return None
    if entry.get("is_free"):
        return None
    pricing = entry.get("pricing")
    if not isinstance(pricing, dict):
        return None

    input_cost = _per_million(pricing.get("prompt"))
    output_cost = _per_million(pricing.get("completion"))
    if input_cost is None and output_cost is None:
        return None
    cache_read = _per_million(pricing.get("input_cache_read"))
    cache_write = _per_million(pricing.get("input_cache_write"))

    time_rates: list[TimeRate] = []
    tier_overrides: list[dict] = []
    overrides = pricing.get("overrides")
    if isinstance(overrides, list):
        for raw in overrides:
            if not isinstance(raw, dict):
                continue
            if "min_prompt_tokens" in raw and not any(
                key in raw for key in ("utc_start", "utc_end", "utc_days")
            ):
                # Context-threshold override, not a time window.
                tier_overrides.append(raw)
                continue
            window = _parse_window(raw, cache_write)
            if window is not None:
                time_rates.append(window)

    cost = ModelCost(
        input=input_cost or 0.0,
        output=output_cost or 0.0,
        cache_read=cache_read or 0.0,
        cache_write=cache_write,
        tiers=_build_token_tiers(
            input_cost, output_cost, cache_read, cache_write, tier_overrides
        ),
        time_rates=tuple(time_rates),
    )
    return normalize_model_cost_key(model_id), cost


def parse_openrouter_json(data: object) -> dict[str, ModelCost]:
    """Parse an OpenRouter ``/models`` payload into a cost map."""
    costs: dict[str, ModelCost] = {}
    if not isinstance(data, dict):
        return costs
    items = data.get("data")
    if not isinstance(items, list):
        return costs

    for entry in items:
        if not isinstance(entry, dict):
            continue
        parsed = _parse_model_entry(entry)
        if parsed is None:
            continue
        key, cost = parsed
        costs[key] = cost
        if "/" in key:
            alias = key.rsplit("/", maxsplit=1)[-1]
            if alias and alias not in costs:
                costs[alias] = cost
    return costs


def _fetch_openrouter_json() -> object | None:
    """Fetch OpenRouter's model catalog. Returns None on failure."""
    return fetch_json(OPENROUTER_URL, REQUEST_TIMEOUT)


class OpenRouterSource:
    """Price source adapter for OpenRouter's model catalog."""

    name = CACHE_NAME

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds

    def fetch(self) -> list[SourceEntry]:
        costs: dict[str, ModelCost] = {}
        if cache_is_fresh(CACHE_NAME, self.ttl_seconds):
            costs = parse_openrouter_json(load_cache_json(CACHE_NAME))

        if not costs:
            raw = _fetch_openrouter_json()
            if raw is not None:
                save_cache_json(CACHE_NAME, raw)
                costs = parse_openrouter_json(raw)
            else:
                costs = parse_openrouter_json(load_cache_json(CACHE_NAME))

        return [
            SourceEntry(provider=None, key=key, cost=cost)
            for key, cost in costs.items()
        ]
