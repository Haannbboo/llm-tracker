from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest


CONFIG_TEMPLATE = """
server:
  host: 127.0.0.1
  port: 4000
  api_port: 4001
db:
  path: {db_path}
providers:
  test-provider:
    base_url: https://api.example.com/v1
    api_key: test-key
    models:
      - test-model
      - gpt-4.1
"""


PROJECT_MODULES = [
    "config.app",
    "src.api",
    "src.database",
    "src.proxy",
    "src.utils",
]


def clear_project_modules() -> None:
    for module_name in PROJECT_MODULES:
        sys.modules.pop(module_name, None)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / ".llm-tracker"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        CONFIG_TEMPLATE.format(db_path=tmp_path / "usage.db"),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    clear_project_modules()
    yield tmp_path
    clear_project_modules()


@pytest.fixture
def load_module(isolated_home: Path) -> Callable[[str], ModuleType]:
    def load(module_name: str) -> ModuleType:
        return importlib.import_module(module_name)

    return load


@pytest.fixture
def config_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("config.app")


@pytest.fixture
def api_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.api")


@pytest.fixture
def database_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.database")


@pytest.fixture
def proxy_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.proxy")


@pytest.fixture
def utils_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.utils")
