import os
import threading
from typing import Any

import yaml

from ..utils import replace_contents as _replace_contents
from . import merge as merge_helpers
from .models import ProviderConfig, expand_path, get_tracker_home

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

    otlp = config.setdefault("otlp", {})
    otlp.setdefault("max_body_bytes", 2_000_000)  # 2 MB
    otlp.setdefault("rate_limit_per_minute", 300)  # 5 req/s per token

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


_config_lock = threading.Lock()


def refresh_runtime_config(path: str | None = None) -> dict[str, Any]:
    from src.pricing.maps import MAPS_LOCK, refresh_pricing_maps
    from src.pricing.sources.registry import fetch_sources

    updated_config = load_config(path)

    # Fetch configured price sources (each uses its local cache on failure).
    auto_fetch = updated_config.get("pricing", {}).get("auto_fetch", True)
    fetched = fetch_sources(updated_config) if auto_fetch else []

    provider_map, model_map = build_maps(updated_config)

    # Swap the pricing maps and PROVIDER_MAP under one lock so a record never
    # pairs new rates with an old multiplier (or vice versa).
    with MAPS_LOCK:
        refresh_pricing_maps(updated_config, fetched)
        with _config_lock:
            _replace_contents(CONFIG, updated_config)
            _replace_contents(PROVIDER_MAP, provider_map)
            _replace_contents(MODEL_MAP, model_map)

    return CONFIG


CONFIG: dict[str, Any] = {}
PROVIDER_MAP: dict[str, ProviderConfig] = {}
MODEL_MAP: dict[str, ProviderConfig] = {}
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
    config_parent = os.path.dirname(config_path)
    if config_parent:
        os.makedirs(config_parent, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
    _reload_config(path)
