"""Kilo: the tokenage plugin entry in ``~/.config/kilo/opencode.json``."""

from __future__ import annotations

from pathlib import Path

from client.agents import plugin

NAME, LABEL = "kilo", "Kilo"


def config_path() -> Path:
    return Path.home() / ".config" / "kilo" / "opencode.json"


def configure(project_root: str | Path, logs_endpoint: str, token: str | None = None):
    return plugin.configure(
        NAME, LABEL, config_path(), project_root, logs_endpoint, token
    )


def disable(project_root: str | Path, expected_endpoint: str | None) -> int:
    return plugin.disable(NAME, LABEL, config_path(), expected_endpoint)
