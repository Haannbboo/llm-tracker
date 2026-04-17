import os
from dataclasses import dataclass
from typing import Any

import yaml

CONFIG_PATH = "~/.llm-tracker/config.yaml"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str


def load_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    with open(os.path.expanduser(path), encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    config["db"]["path"] = os.path.expanduser(config["db"]["path"])
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


CONFIG = load_config()
PROVIDER_MAP, MODEL_MAP = build_maps(CONFIG)
