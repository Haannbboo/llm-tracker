from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable, Generator
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

NO_REMOTE_PRICING_CONFIG = (
    Path(__file__).parent / "fixtures" / "no-remote-pricing-config.yaml"
)
os.environ.setdefault("LLM_TRACKER_CONFIG", str(NO_REMOTE_PRICING_CONFIG))


CONFIG_TEMPLATE = """
pricing:
  auto_fetch: false
server:
  host: 127.0.0.1
  port: 4000
  api_port: 4001
db:
  path: {db_path}
evaluation:
  auto_enabled: false
  idle_sleep_cap_seconds: 1
models:
  test-model:
    cost:
      input: 2.0
      output: 6.0
      cacheRead: 0.5
  gpt-4.1:
    cost:
      input: 2.0
      output: 8.0
      cacheRead: 0.5
providers:
  test-provider:
    base_url: https://api.example.com/v1
    api_key: test-key
    price_multiplier: 1.25
    models:
      test-model: {{}}
      gpt-4.1: {{}}
"""


PROJECT_MODULES = [
    "config.app",
    "config.runtime_ports",
    "src.api",
    "src.cli",
    "src.costs",
    "src.database",
    "src.evaluation",
    "src.evaluation_worker",
    "src.schema_migrations",
    "src.otlp",
    "src.proxy",
    "src.recorder",
    "src.utils",
    "src.provider_parser",
]


def clear_project_modules() -> None:
    removed_modules = set(PROJECT_MODULES)
    for module_name in PROJECT_MODULES:
        sys.modules.pop(module_name, None)
    # Clear package submodules (e.g. src.database.models)
    for key in list(sys.modules):
        if any(key.startswith(prefix + ".") for prefix in PROJECT_MODULES):
            sys.modules.pop(key, None)
            removed_modules.add(key)

    for module_name in removed_modules:
        package_name, _, attribute = module_name.rpartition(".")
        package = sys.modules.get(package_name)
        if package is not None and hasattr(package, attribute):
            delattr(package, attribute)


@pytest.fixture
def isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Path, None, None]:
    config_dir = tmp_path / ".llm-tracker"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        CONFIG_TEMPLATE.format(db_path=tmp_path / "usage.db"),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LLM_TRACKER_CONFIG", str(config_path))
    clear_project_modules()
    # Patch CONFIG["db"] so cached modules see the test's DB path.
    import config.app

    monkeypatch.setitem(
        config.app.CONFIG,
        "db",
        {
            "path": str(tmp_path / "usage.db"),
            "url": f"sqlite:///{tmp_path / 'usage.db'}",
        },
    )
    yield tmp_path


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
def cli_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.cli")


@pytest.fixture
def costs_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.costs")


@pytest.fixture
def database_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.database")


@pytest.fixture
def evaluation_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.evaluation")


@pytest.fixture
def evaluation_worker_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.evaluation_worker")


@pytest.fixture
def schema_migrations_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.schema_migrations")


@pytest.fixture
def proxy_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.proxy")


@pytest.fixture
def otlp_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.otlp")


@pytest.fixture
def utils_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("src.utils")


@pytest.fixture
def runtime_ports_module(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module("config.runtime_ports")


# ponytail: lightweight DB fixture — one DB per session, truncate tables between tests.
# Use this for database tests that just need a clean DB with latest schema.
# Use isolated_home for tests that need full module teardown or custom schemas.

# Tables to truncate between tests (in dependency order for FK safety).
# IMPORTANT: Add any new table created by schema migrations here, otherwise
# data will leak between fresh_db tests and cause spurious failures.
# Verify with: list of tables should match inspect(engine).get_table_names()
_TRUNCATE_TABLES = [
    "usage_daily",
    "tool_calls",
    "evaluation_jobs",
    "sessions",
    "usage",
    "base_urls",
    "auth_tokens",
    "users",
]


@pytest.fixture(scope="session")
def _session_db(tmp_path_factory):
    """Session-scoped DB with latest schema — shared across all fresh_db tests."""
    import src.database as db
    import src.schema_migrations as sm

    db_path = str(tmp_path_factory.mktemp("dbsession") / "usage.db")
    db.init_db(db_path)
    sm.migrate_database(db_path)
    return db_path


@pytest.fixture
def fresh_db(_session_db: str, monkeypatch: pytest.MonkeyPatch):
    """Function-scoped clean database (truncated, not recreated).

    Returns an object with .db_path, .database_module, .schema_migrations_module.
    The schema is created once per test session; between tests all tables are truncated.
    CONFIG["db"] is patched so default-arg calls hit the test DB.
    """
    # Import each time — fast because sys.modules caches.
    # Only slow after isolated_home clears modules (rare, ~17 tests).
    import config.app
    import src.database as db
    import src.schema_migrations as sm

    db_path = _session_db
    db_url = f"sqlite:///{db_path}"

    # Patch CONFIG so functions called without db_path use the test DB
    monkeypatch.setitem(config.app.CONFIG["db"], "path", db_path)
    monkeypatch.setitem(config.app.CONFIG["db"], "url", db_url)

    # Truncate all tables for a clean slate (much faster than recreating DB)
    engine = db.get_engine(db_path)
    with engine.begin() as conn:
        for table in _TRUNCATE_TABLES:
            conn.execute(db.text(f"DELETE FROM {table}"))

    return SimpleNamespace(
        db_path=db_path,
        database_module=db,
        schema_migrations_module=sm,
    )
