import os
from dataclasses import dataclass
from typing import Any

import yaml

DEFAULT_TRACKER_HOME = "~/.llm-tracker"
CONFIG_ENV_VAR = "LLM_TRACKER_CONFIG"
TRACKER_HOME_ENV_VAR = "LLM_TRACKER_HOME"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str


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
    config.setdefault("providers", {})

    server.setdefault("host", "0.0.0.0")
    server.setdefault("port", 4000)
    server.setdefault("api_port", server["port"] + 1)
    server.setdefault("otlp_port", server["api_port"] + 1)

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


def build_maps(
    config: dict[str, Any],
) -> tuple[dict[str, ProviderConfig], dict[str, ProviderConfig]]:
    provider_map: dict[str, ProviderConfig] = {}
    model_map: dict[str, ProviderConfig] = {}

    for provider_name, provider in config["providers"].items():
        provider_config = ProviderConfig(
            name=provider_name, base_url=provider["base_url"]
        )
        provider_map[provider_name] = provider_config
        for model in provider.get("models", []):
            model_map[model] = provider_config

    return provider_map, model_map


def refresh_runtime_config(path: str | None = None) -> dict[str, Any]:
    updated_config = load_config(path)
    provider_map, model_map = build_maps(updated_config)

    CONFIG.clear()
    CONFIG.update(updated_config)
    PROVIDER_MAP.clear()
    PROVIDER_MAP.update(provider_map)
    MODEL_MAP.clear()
    MODEL_MAP.update(model_map)

    return CONFIG


CONFIG: dict[str, Any] = {}
PROVIDER_MAP: dict[str, ProviderConfig] = {}
MODEL_MAP: dict[str, ProviderConfig] = {}
refresh_runtime_config(CONFIG_PATH)
