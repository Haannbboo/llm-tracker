import os
from dataclasses import dataclass
from typing import Any

import yaml
from . import merge as merge_helpers

DEFAULT_TRACKER_HOME = "~/.llm-tracker"
CONFIG_ENV_VAR = "LLM_TRACKER_CONFIG"
TRACKER_HOME_ENV_VAR = "LLM_TRACKER_HOME"

merge_missing_config_defaults = merge_helpers.merge_missing_config_defaults
sync_config_file_with_defaults = merge_helpers.sync_config_file_with_defaults


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    price_multiplier: float = 1.0


@dataclass(frozen=True)
class ModelCost:
    input: float
    output: float
    cache_read: float


def normalize_model_cost_key(model_name: str) -> str:
    return model_name.lower()


def expand_path(path: str) -> str:
    return os.path.expanduser(path)


def get_tracker_home() -> str:
    return expand_path(os.environ.get(TRACKER_HOME_ENV_VAR, DEFAULT_TRACKER_HOME))


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
) -> tuple[dict[str, ModelCost], dict[str, dict[str, ModelCost]]]:
    model_costs: dict[str, ModelCost] = {}
    provider_model_costs: dict[str, dict[str, ModelCost]] = {}

    for model_name, model_config in config.get("models", {}).items():
        model_cost = _parse_model_cost(model_config)
        if model_cost is not None:
            model_costs[normalize_model_cost_key(model_name)] = model_cost

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

    return model_costs, provider_model_costs


def refresh_runtime_config(path: str | None = None) -> dict[str, Any]:
    updated_config = load_config(path)
    provider_map, model_map = build_maps(updated_config)
    model_costs, provider_model_costs = build_cost_maps(updated_config)

    CONFIG.clear()
    CONFIG.update(updated_config)
    PROVIDER_MAP.clear()
    PROVIDER_MAP.update(provider_map)
    MODEL_MAP.clear()
    MODEL_MAP.update(model_map)
    MODEL_COSTS.clear()
    MODEL_COSTS.update(model_costs)
    PROVIDER_MODEL_COSTS.clear()
    PROVIDER_MODEL_COSTS.update(provider_model_costs)

    return CONFIG


CONFIG: dict[str, Any] = {}
PROVIDER_MAP: dict[str, ProviderConfig] = {}
MODEL_MAP: dict[str, ProviderConfig] = {}
MODEL_COSTS: dict[str, ModelCost] = {}
PROVIDER_MODEL_COSTS: dict[str, dict[str, ModelCost]] = {}
refresh_runtime_config(CONFIG_PATH)
