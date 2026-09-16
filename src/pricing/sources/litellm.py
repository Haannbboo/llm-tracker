"""LiteLLM price source: fetch/cache/parse LiteLLM's public pricing JSON.

``LiteLLMSource`` adapts the parsed cost map into the generic ``SourceEntry``
shape used by the source registry.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from src.pricing.models import ModelCost, ModelTier, normalize_model_cost_key

from .base import (
    REQUEST_TIMEOUT,
    SourceEntry,
    cache_is_fresh,
    fetch_json,
    load_cache_json,
    save_cache_json,
)

LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm"
    "/main/model_prices_and_context_window.json"
)
CACHE_NAME = "litellm"
CACHE_TTL_SECONDS = 24 * 60 * 60  # re-fetch from GitHub at most once a day

log = logging.getLogger(__name__)

_remote_lock = threading.Lock()
_remote_costs: dict[str, ModelCost] | None = None

# Prefixes that LiteLLM prepends to model keys.
_PROVIDER_PREFIX_RE = re.compile(
    r"^(?:"
    r"anthropic\."  # anthropic.claude-sonnet-4-5-20250929-v1:0
    r"|openai\."  # openai.gpt-4o
    r"|azure_ai/"  # azure_ai/gpt-5.4
    r"|bedrock_converse\."  # bedrock_converse.anthropic.claude-...
    r"|bedrock\."  # bedrock.anthropic.claude-...
    r"|vertex_ai/"  # vertex_ai/gemini-2.5-pro
    r"|gemini/"  # gemini/gemini-2.5-pro
    r"|deepseek/"  # deepseek/deepseek-chat
    r"|cohere/"  # cohere/command-r-plus
    r"|mistral/"  # mistral/mistral-large
    r"|together_ai/"  # together_ai/meta-llama/...
    r"|fireworks_ai/"  # fireworks_ai/accounts/...
    r"|groq/"  # groq/llama-3.1-70b
    r"|palm/"  # palm/chat-bison
    r"|ollama/"  # ollama/llama3
    r"|voyage/"  # voyage/voyage-3
    r"|databricks/"  # databricks/databricks-meta-...
    r"|xai/"  # xai/grok-3
    r"|stepfun/"  # stepfun/step-2-16k
    r")",
    re.IGNORECASE,
)

# Date suffixes appended to model names: claude-sonnet-4-5-20250929
_DATE_SUFFIX_RE = re.compile(r"-\d{8}(?:-\w+)?(?:-v\d+(?::\d+)?)?$")

# Version suffixes: gpt-4o-2024-08-06, gpt-5.4-turbo
_VERSION_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")

# LiteLLM uses "claude-3-7-sonnet", llm-tracker uses "claude-sonnet-3-7"
_CLAUDE_3X_RE = re.compile(r"^claude-(\d+)-(?:(\d+)-)?(sonnet|opus|haiku)$")


def _strip_provider_prefix(model_key: str) -> str:
    """Remove LiteLLM provider prefixes like 'anthropic.', 'azure_ai/'."""
    return _PROVIDER_PREFIX_RE.sub("", model_key)


def _strip_version_suffix(name: str) -> str:
    """Strip date/version suffixes to get the base model name."""
    name = _DATE_SUFFIX_RE.sub("", name)
    name = _VERSION_SUFFIX_RE.sub("", name)
    return name


def _is_chat_model(entry: dict[str, Any]) -> bool:
    """Check if a token-priced model entry we should track."""
    mode = entry.get("mode", "chat")
    return mode in ("chat", "text", "reasoning", "responses")


def _parse_tiered_pricing(entry: dict[str, Any]) -> tuple[ModelTier, ...] | None:
    """Parse litellm `tiered_pricing` into per-million ModelTier entries."""
    raw_tiers = entry.get("tiered_pricing")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        return None

    tiers: list[ModelTier] = []
    for raw in raw_tiers:
        if not isinstance(raw, dict):
            continue
        try:
            rng = raw.get("range")
            if not isinstance(rng, list) or not rng:
                continue
            min_tokens = int(float(rng[0]))
            max_tokens = (
                int(float(rng[1])) if len(rng) > 1 and rng[1] is not None else None
            )
            # Missing per-tier prices fall back to the entry's top-level values.
            tier_input = raw.get("input_cost_per_token")
            tier_output = raw.get("output_cost_per_token")
            tier_cache = raw.get("cache_read_input_token_cost")
            tier_cache_write = raw.get("cache_creation_input_token_cost")
            if tier_input is None:
                tier_input = entry.get("input_cost_per_token")
            if tier_output is None:
                tier_output = entry.get("output_cost_per_token")
            if tier_cache is None:
                tier_cache = entry.get("cache_read_input_token_cost")
            if tier_cache_write is None:
                tier_cache_write = entry.get("cache_creation_input_token_cost")
            if tier_input is None and tier_output is None:
                continue
            tiers.append(
                ModelTier(
                    min_tokens=min_tokens,
                    max_tokens=max_tokens,
                    input=round(float(tier_input or 0) * 1_000_000, 6),
                    output=round(float(tier_output or 0) * 1_000_000, 6),
                    cache_read=round(float(tier_cache or 0) * 1_000_000, 6),
                    cache_write=(
                        round(float(tier_cache_write) * 1_000_000, 6)
                        if tier_cache_write is not None
                        else None
                    ),
                )
            )
        except (TypeError, ValueError):
            # Malformed tier (bad range or non-numeric price): skip it rather
            # than dropping the whole pricing file at config load time.
            continue
    return tuple(tiers) or None


def _parse_model_entry(
    model_key: str, entry: dict[str, Any]
) -> tuple[str, ModelCost] | None:
    """Parse a LiteLLM model entry into a normalized key and ModelCost."""
    if not isinstance(entry, dict):
        return None

    if not _is_chat_model(entry):
        return None

    tiers = _parse_tiered_pricing(entry)

    input_cost = entry.get("input_cost_per_token")
    output_cost = entry.get("output_cost_per_token")
    cache_read = entry.get("cache_read_input_token_cost")
    cache_write = entry.get("cache_creation_input_token_cost")

    # Some models only have tiered pricing; use the first tier as the flat price.
    if input_cost is None and output_cost is None:
        if tiers is None:
            return None
        first = tiers[0]
        input_cost = first.input / 1_000_000
        output_cost = first.output / 1_000_000
        cache_read = first.cache_read / 1_000_000
        cache_write = None

    # Skip models with no token-based pricing
    if input_cost is None and output_cost is None:
        return None

    # Convert per-token to per-million, round to avoid float imprecision
    input_per_million = round(float(input_cost or 0) * 1_000_000, 6)
    output_per_million = round(float(output_cost or 0) * 1_000_000, 6)
    cache_read_per_million = round(float(cache_read or 0) * 1_000_000, 6)
    cache_write_per_million = (
        round(float(cache_write) * 1_000_000, 6) if cache_write is not None else None
    )

    cost = ModelCost(
        input=input_per_million,
        output=output_per_million,
        cache_read=cache_read_per_million,
        cache_write=cache_write_per_million,
        tiers=tuple(tiers) if tiers else (),
    )

    # Normalize key: strip provider prefix, lowercase
    normalized = normalize_model_cost_key(_strip_provider_prefix(model_key))
    return normalized, cost


def _claude_3x_alias(name: str) -> str | None:
    """Generate llm-tracker style alias for LiteLLM's claude-3-x-sonnet naming.

    'claude-3-7-sonnet' -> 'claude-sonnet-3-7'
    'claude-3-opus'     -> 'claude-opus-3'
    """
    m = _CLAUDE_3X_RE.match(name)
    if m:
        major = m.group(1)
        minor = m.group(2)
        model_type = m.group(3)
        version = f"{major}-{minor}" if minor else major
        return f"claude-{model_type}-{version}"
    return None


def _add_aliases(costs: dict[str, ModelCost], key: str, cost: ModelCost) -> None:
    """Add useful aliases for a model key if they don't already exist."""
    # Version-stripped alias (e.g. strip -20250929 from claude-sonnet-4-5-20250929)
    base_name = normalize_model_cost_key(_strip_version_suffix(key))
    if base_name != key and base_name not in costs:
        costs[base_name] = cost

    # Claude 3.x naming alias (claude-3-7-sonnet -> claude-sonnet-3-7)
    # Try both the full key and the date-stripped base name
    for candidate in (key, base_name):
        alias = _claude_3x_alias(candidate)
        if alias and alias != candidate and alias not in costs:
            costs[alias] = cost


def _parse_litellm_json(data: dict[str, Any]) -> dict[str, ModelCost]:
    """Parse the full LiteLLM pricing JSON into a cost map."""
    costs: dict[str, ModelCost] = {}

    for model_key, entry in data.items():
        if model_key.startswith("sample_spec"):
            continue
        result = _parse_model_entry(model_key, entry)
        if result is not None:
            normalized_key, cost = result
            costs[normalized_key] = cost
            _add_aliases(costs, normalized_key, cost)

    # Deduplicate: if both "gpt-5.5" and "gpt-5.5-2026-04-23" exist,
    # keep only the shorter base name.
    to_remove: list[str] = []
    for key in costs:
        base = normalize_model_cost_key(_strip_version_suffix(key))
        if base != key and base in costs:
            to_remove.append(key)

    for key in to_remove:
        del costs[key]

    return costs


def _load_local_cache() -> dict[str, ModelCost]:
    """Load cached pricing from the shared pricing cache."""
    raw = load_cache_json(CACHE_NAME)
    return _parse_litellm_json(raw) if isinstance(raw, dict) else {}


def _fetch_litellm_json() -> dict[str, Any] | None:
    """Fetch the LiteLLM pricing JSON from GitHub. Returns None on failure."""
    return fetch_json(LITELLM_URL, REQUEST_TIMEOUT)


def fetch_remote_pricing(
    ttl_seconds: int = CACHE_TTL_SECONDS,
) -> dict[str, ModelCost]:
    """Load pricing, hitting GitHub only if the local cache is older than
    ``ttl_seconds``.

    Returns the merged cost map. Falls back to stale local cache on failure.
    Thread-safe.
    """
    global _remote_costs

    with _remote_lock:
        if cache_is_fresh(CACHE_NAME, ttl_seconds):
            cached = _load_local_cache()
            # A fresh mtime with no parseable data means a truncated/corrupt
            # write, not "we already have today's pricing" -- don't let that
            # block a real fetch for a full TTL.
            if cached:
                _remote_costs = cached
                log.info(
                    "Loaded %d model prices from local cache (fresh)",
                    len(_remote_costs),
                )
                return dict(_remote_costs)

        # Try fetching fresh data
        raw = _fetch_litellm_json()
        if raw is not None:
            save_cache_json(CACHE_NAME, raw)
            _remote_costs = _parse_litellm_json(raw)
            log.info("Loaded %d model prices from LiteLLM", len(_remote_costs))
        elif _remote_costs is None:
            # First call failed, try stale cache
            _remote_costs = _load_local_cache()
            log.info("Loaded %d model prices from local cache", len(_remote_costs))

        return dict(_remote_costs)


class LiteLLMSource:
    """Price source adapter for the LiteLLM pricing JSON."""

    name = "litellm"

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds

    def fetch(self) -> list[SourceEntry]:
        return [
            SourceEntry(provider=None, key=key, cost=cost)
            for key, cost in fetch_remote_pricing(self.ttl_seconds).items()
        ]
