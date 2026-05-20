import os
import threading
from typing import Any

import yaml
from . import merge as merge_helpers
from .models import (
    ModelCost,
    ProviderConfig,
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


def _parse_model_cost(model_config: Any) -> ModelCost | None:
    if not isinstance(model_config, dict):
        return None

    cost = model_config.get("cost")
    if not isinstance(cost, dict):
        return None

    return ModelCost(
        input=float(cost.get("input", 0)),
        output=float(cost.get("output", 0)),
        cache_read=float(cost.get("cacheRead", 0)),
        cache_write=float(cost["cacheWrite"]) if "cacheWrite" in cost else None,
    )


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
        )
        provider_map[provider_name] = provider_config
        for model in _iter_provider_models(provider):
            model_map[model] = provider_config

    return provider_map, model_map


def build_cost_maps(
    config: dict[str, Any],
    remote_costs: dict[str, ModelCost] | None = None,
) -> tuple[dict[str, ModelCost], dict[str, dict[str, ModelCost]]]:
    model_costs: dict[str, ModelCost] = {}
    provider_model_costs: dict[str, dict[str, ModelCost]] = {}

    # Layer 1: YAML models (manual overrides)
    for model_name, model_config in config.get("models", {}).items():
        model_cost = _parse_model_cost(model_config)
        if model_cost is not None:
            model_costs[normalize_model_cost_key(model_name)] = model_cost

    # Layer 2: YAML provider-specific overrides
    for provider_name, provider in config["providers"].items():
        provider_costs: dict[str, ModelCost] = {}
        models = provider.get("models", {})
        if isinstance(models, dict):
            for model_name, model_config in models.items():
                model_cost = _parse_model_cost(model_config)
                if model_cost is not None:
                    provider_costs[normalize_model_cost_key(model_name)] = model_cost
        if provider_costs:
            provider_model_costs[provider_name] = provider_costs

    # Layer 3: Remote pricing fills gaps (models with no YAML cost)
    if remote_costs:
        for key, cost in remote_costs.items():
            if key not in model_costs:
                model_costs[key] = cost

    return model_costs, provider_model_costs


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

    with _config_lock:
        _replace_contents(CONFIG, updated_config)
        _replace_contents(PROVIDER_MAP, provider_map)
        _replace_contents(MODEL_MAP, model_map)
        _replace_contents(MODEL_COSTS, model_costs)
        _replace_contents(PROVIDER_MODEL_COSTS, provider_model_costs)

    return CONFIG


CONFIG: dict[str, Any] = {}
PROVIDER_MAP: dict[str, ProviderConfig] = {}
MODEL_MAP: dict[str, ProviderConfig] = {}
MODEL_COSTS: dict[str, ModelCost] = {}
PROVIDER_MODEL_COSTS: dict[str, dict[str, ModelCost]] = {}
refresh_runtime_config(CONFIG_PATH)
