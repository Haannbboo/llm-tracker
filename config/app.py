import os
import threading
from typing import Any

import yaml

from . import merge as merge_helpers
from .models import (
    ModelCost,
    ModelTier,
    ProviderConfig,
    ResolvedCost,
    ResolvedCosts,
    build_segment_index,
    expand_path,
    get_tracker_home,
    normalize_model_cost_key,
)

CONFIG_ENV_VAR = "LLM_TRACKER_CONFIG"

merge_missing_config_defaults = merge_helpers.merge_missing_config_defaults
sync_config_file_with_defaults = merge_helpers.sync_config_file_with_defaults


def get_config_path(path: str | None = None) -> str:
    if path:
        return expand_path(path)
    return expand_path(
        os.environ.get(CONFIG_ENV_VAR, os.path.join(get_tracker_home(), "config.yaml"))
    )


CONFIG_PATH = get_config_path()


def load_config(path: str | None = None) -> dict[str, Any]:
    with open(get_config_path(path), encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    config = config or {}
    server = config.setdefault("server", {})
    db = config.setdefault("db", {})
    config.setdefault("models", {})
    config.setdefault("providers", {})

    server.setdefault("host", "127.0.0.1")
    server.setdefault("port", 4000)
    server.setdefault("api_port", server["port"] + 1)
    server.setdefault("otlp_port", server["api_port"] + 1)

    auth = config.setdefault("auth", {})
    auth.setdefault("enabled", False)
    auth.setdefault("allowlist", [])
    # Google OAuth credentials are env-only, never YAML (by decision in
    # docs/design/specs/pr1-auth-foundation.md); env always wins.
    auth["google_client_id"] = os.environ.get("LLMTRACKER_AUTH__GOOGLE_CLIENT_ID", "")
    auth["google_client_secret"] = os.environ.get(
        "LLMTRACKER_AUTH__GOOGLE_CLIENT_SECRET", ""
    )

    evaluation = config.setdefault("evaluation", {})
    evaluation.setdefault("auto_enabled", True)
    evaluation.setdefault("quiet_delay_seconds", 600)
    evaluation.setdefault("max_concurrent_jobs", 1)
    evaluation.setdefault("queue_buffer_multiplier", 2)
    evaluation.setdefault("idle_sleep_cap_seconds", 30)
    evaluation.setdefault("worker_tick_timeout_seconds", 120)

    if "url" not in db:
        db.setdefault("path", os.path.join(get_tracker_home(), "usage.db"))
        db["path"] = expand_path(db["path"])
        db["url"] = f"sqlite:///{db['path']}"
    elif isinstance(db["url"], str) and db["url"].startswith("sqlite:///"):
        sqlite_path = db["url"][10:]
        if sqlite_path.startswith("~"):
            db["url"] = f"sqlite:///{expand_path(sqlite_path)}"

    if "path" in db and isinstance(db["path"], str):
        db["path"] = expand_path(db["path"])
    return config


def _iter_provider_models(provider: dict[str, Any]) -> list[str]:
    models = provider.get("models", {})
    if isinstance(models, dict):
        return list(models)
    if isinstance(models, list):
        return models
    return []


def _parse_tiered_cost(cost: dict[str, Any], flat: ModelCost) -> tuple[ModelTier, ...]:
    """Parse YAML `cost.tiers` (per-million prices with `range` token bounds).

    Missing per-tier prices fall back to the flat cost values.
    """
    raw_tiers = cost.get("tiers")
    if not isinstance(raw_tiers, list):
        return ()

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
            tier_input = raw.get("input")
            tier_output = raw.get("output")
            tier_cache_read = raw.get("cacheRead")
            tier_cache_write = raw.get("cacheWrite")
            tiers.append(
                ModelTier(
                    min_tokens=min_tokens,
                    max_tokens=max_tokens,
                    input=flat.input if tier_input is None else float(tier_input),
                    output=flat.output if tier_output is None else float(tier_output),
                    cache_read=(
                        flat.cache_read
                        if tier_cache_read is None
                        else float(tier_cache_read)
                    ),
                    cache_write=(
                        flat.cache_write
                        if tier_cache_write is None
                        else float(tier_cache_write)
                    ),
                )
            )
        except (TypeError, ValueError):
            # Malformed tier (bad range or non-numeric price): skip it rather
            # than crashing config load at import time.
            continue
    return tuple(tiers)


def _parse_model_cost(
    model_config: Any, base: ModelCost | None = None
) -> ModelCost | None:
    if not isinstance(model_config, dict):
        return None

    cost = model_config.get("cost")
    if not isinstance(cost, dict):
        return None

    flat = ModelCost(
        input=float(cost.get("input", base.input if base else 0)),
        output=float(cost.get("output", base.output if base else 0)),
        cache_read=float(cost.get("cacheRead", base.cache_read if base else 0)),
        cache_write=(
            float(cost["cacheWrite"])
            if "cacheWrite" in cost
            else base.cache_write
            if base
            else None
        ),
    )

    # YAML tiers without flat prices: default flat values to the first tier
    # (mirrors litellm, which uses the first tier as the flat price).
    raw_tiers = cost.get("tiers")
    has_flat = bool({"input", "output", "cacheRead"}.intersection(cost))
    effective_flat = flat
    if isinstance(raw_tiers, list) and raw_tiers and not has_flat:
        raw_first = raw_tiers[0]
        if isinstance(raw_first, dict) and isinstance(raw_first.get("range"), list):
            try:
                effective_flat = ModelCost(
                    input=float(raw_first.get("input", flat.input)),
                    output=float(raw_first.get("output", flat.output)),
                    cache_read=float(raw_first.get("cacheRead", flat.cache_read)),
                    cache_write=flat.cache_write,
                )
            except (TypeError, ValueError):
                effective_flat = flat

    if "tiers" in cost:
        # Explicit tiers (even `tiers: []`) fully define the pricing shape.
        tiers = _parse_tiered_cost(cost, effective_flat)
    elif has_flat:
        # Explicit flat prices are an override: clear any inherited tiers so
        # the flat rates are actually billed.
        tiers = ()
    else:
        tiers = base.tiers if base is not None else ()
    if effective_flat is not flat:
        flat = effective_flat

    return ModelCost(
        input=flat.input,
        output=flat.output,
        cache_read=flat.cache_read,
        cache_write=flat.cache_write,
        tiers=tiers,
    )


def _apply_patch(config: dict[str, Any], path: list[str], op: str, value: Any) -> None:
    if not path:
        raise ValueError("Patch path cannot be empty")

    target = config
    for key in path[:-1]:
        if not isinstance(target, dict):
            raise ValueError(f"Cannot traverse non-mapping key '{key}'")
        if op == "delete" and key not in target:
            return
        next_target = target.setdefault(key, {}) if op == "set" else target[key]
        if not isinstance(next_target, dict):
            raise ValueError(f"Cannot traverse non-mapping key '{key}'")
        target = next_target

    if not isinstance(target, dict):
        raise ValueError(f"Cannot apply patch at '{path[-1]}'")

    if op == "set":
        target[path[-1]] = value
        return
    if op == "delete":
        target.pop(path[-1], None)
        return
    raise ValueError(f"Unsupported patch operation: {op}")


def build_maps(
    config: dict[str, Any],
) -> tuple[dict[str, ProviderConfig], dict[str, ProviderConfig]]:
    provider_map: dict[str, ProviderConfig] = {}
    model_map: dict[str, ProviderConfig] = {}

    for provider_name, provider in config["providers"].items():
        provider_config = ProviderConfig(
            name=provider_name,
            base_url=provider["base_url"],
            price_multiplier=float(provider.get("price_multiplier", 1.0)),
            api_key=provider.get("api_key") or None,
            auth_scheme=provider.get("auth_scheme", "bearer"),
        )
        provider_map[provider_name] = provider_config
        for model in _iter_provider_models(provider):
            model_map[model] = provider_config

    return provider_map, model_map


def build_cost_maps(
    config: dict[str, Any],
    remote_costs: dict[str, ModelCost] | None = None,
) -> tuple[dict[str, ModelCost], dict[str, dict[str, ModelCost]]]:
    resolved = resolve_all_costs(config, remote_costs)
    model_costs = {key: rc.cost for key, rc in resolved.global_costs.items()}
    provider_model_costs = {
        provider: {key: rc.cost for key, rc in costs.items()}
        for provider, costs in resolved.provider_costs.items()
    }
    return model_costs, provider_model_costs


def resolve_all_costs(
    config: dict[str, Any],
    remote_costs: dict[str, ModelCost] | None = None,
) -> ResolvedCosts:
    """Resolve global and provider model costs with source metadata."""
    global_costs: dict[str, ResolvedCost] = {}
    provider_costs: dict[str, dict[str, ResolvedCost]] = {}
    remote_costs = remote_costs or {}

    for key, cost in remote_costs.items():
        global_costs[key] = ResolvedCost(
            cost=cost,
            source="litellm",
        )

    for model_name, model_config in config.get("models", {}).items():
        normalized_model = normalize_model_cost_key(model_name)
        base_cost = global_costs.get(normalized_model)
        model_cost = _parse_model_cost(
            model_config,
            base_cost.cost if base_cost is not None else None,
        )
        if model_cost is not None:
            global_costs[normalized_model] = ResolvedCost(
                cost=model_cost,
                source="yaml",
            )

    for provider_name, provider in config.get("providers", {}).items():
        if not isinstance(provider, dict):
            continue
        models = provider.get("models", {})
        if isinstance(models, dict):
            for model_name, model_config in models.items():
                normalized_model = normalize_model_cost_key(model_name)
                base_cost = global_costs.get(normalized_model)
                model_cost = _parse_model_cost(
                    model_config,
                    base_cost.cost if base_cost is not None else None,
                )
                if model_cost is not None:
                    provider_costs.setdefault(provider_name, {})[normalized_model] = (
                        ResolvedCost(
                            cost=model_cost,
                            source="yaml",
                        )
                    )

    return ResolvedCosts(global_costs=global_costs, provider_costs=provider_costs)


_config_lock = threading.Lock()


def _replace_contents(target: dict, source: dict) -> None:
    """Update target in place to match source without a clear-then-fill window."""
    target.update(source)
    for stale in set(target) - set(source):
        del target[stale]


def refresh_runtime_config(path: str | None = None) -> dict[str, Any]:
    from .pricing import fetch_remote_pricing

    updated_config = load_config(path)

    # Fetch LiteLLM pricing (uses local cache as fallback if network unavailable).
    auto_fetch = updated_config.get("pricing", {}).get("auto_fetch", True)
    if auto_fetch:
        remote_costs = fetch_remote_pricing()
    else:
        remote_costs = {}

    provider_map, model_map = build_maps(updated_config)
    model_costs, provider_model_costs = build_cost_maps(updated_config, remote_costs)
    model_segment_costs = build_segment_index(model_costs)
    provider_model_segment_costs = {
        provider_name: build_segment_index(costs)
        for provider_name, costs in provider_model_costs.items()
    }

    with _config_lock:
        _replace_contents(CONFIG, updated_config)
        _replace_contents(PROVIDER_MAP, provider_map)
        _replace_contents(MODEL_MAP, model_map)
        _replace_contents(MODEL_COSTS, model_costs)
        _replace_contents(PROVIDER_MODEL_COSTS, provider_model_costs)
        _replace_contents(MODEL_SEGMENT_COSTS, model_segment_costs)
        _replace_contents(PROVIDER_MODEL_SEGMENT_COSTS, provider_model_segment_costs)

    return CONFIG


CONFIG: dict[str, Any] = {}
PROVIDER_MAP: dict[str, ProviderConfig] = {}
MODEL_MAP: dict[str, ProviderConfig] = {}
MODEL_COSTS: dict[str, ModelCost] = {}
PROVIDER_MODEL_COSTS: dict[str, dict[str, ModelCost]] = {}
MODEL_SEGMENT_COSTS: dict[str, tuple[str, ModelCost]] = {}
PROVIDER_MODEL_SEGMENT_COSTS: dict[str, dict[str, tuple[str, ModelCost]]] = {}
refresh_runtime_config(CONFIG_PATH)


def _reload_config(path: str | None = None) -> None:
    """Re-applies the config merge so CONFIG reflects the latest file values."""
    updated_config = load_config(path)
    with _config_lock:
        _replace_contents(CONFIG, updated_config)


def set_evaluation_evaluator(evaluator: str, path: str | None = None) -> None:
    """Set the evaluator type in config.yaml and reload config."""
    config_path = get_config_path(path)
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    evaluation = config.setdefault("evaluation", {})
    evaluation["evaluator"] = evaluator
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
    _reload_config(path)
