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
