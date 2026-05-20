"""Shared data classes and utilities for model cost and provider configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

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


@dataclass(frozen=True)
class ModelCost:
    input: float
    output: float
    cache_read: float
    cache_write: float | None = None


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
