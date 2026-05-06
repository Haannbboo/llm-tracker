import os
import runpy
import subprocess
import sys
from pathlib import Path

import yaml


def test_load_config_expands_database_path(config_module, tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path.write_text(
        """
server:
  host: 127.0.0.1
  port: 4000
db:
  path: ~/.llm-tracker/usage.db
providers: {}
""",
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert config["db"]["path"] == str(Path(tmp_path, ".llm-tracker/usage.db"))
    assert config["db"]["url"] == f"sqlite:///{Path(tmp_path, '.llm-tracker/usage.db')}"


def test_load_config_sets_default_models_mapping(config_module, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: 127.0.0.1
providers: {}
""",
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert config["models"] == {}


def test_load_config_keeps_database_url(config_module, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: 127.0.0.1
db:
  url: postgresql+psycopg://user:pass@db.example.edu:5432/llm_tracker
providers: {}
""",
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert (
        config["db"]["url"]
        == "postgresql+psycopg://user:pass@db.example.edu:5432/llm_tracker"
    )


def test_get_config_path_prefers_env_override(config_module, tmp_path, monkeypatch):
    config_path = tmp_path / "custom-config.yaml"
    monkeypatch.setenv("LLM_TRACKER_CONFIG", str(config_path))

    assert config_module.get_config_path() == str(config_path)


def test_get_tracker_home_prefers_env_override(config_module, tmp_path, monkeypatch):
    tracker_home = tmp_path / "tracker-home"
    monkeypatch.setenv("LLM_TRACKER_HOME", str(tracker_home))

    assert config_module.get_tracker_home() == str(tracker_home)


def test_build_maps_returns_provider_configs(config_module):
    provider_map, model_map = config_module.build_maps(
        {
            "models": {
                "alpha-1": {},
                "alpha-2": {},
                "beta-1": {},
            },
            "providers": {
                "alpha": {
                    "base_url": "https://alpha.example/v1",
                    "api_key": "alpha-key",
                    "models": {"alpha-1": {}, "alpha-2": {}},
                },
                "beta": {
                    "base_url": "https://beta.example/v1",
                    "api_key": "beta-key",
                    "models": {"beta-1": {}},
                },
            },
        }
    )

    assert model_map["alpha-1"] == config_module.ProviderConfig(
        name="alpha",
        base_url="https://alpha.example/v1",
    )
    assert model_map["beta-1"].name == "beta"
    assert provider_map["alpha"].name == "alpha"


def test_build_maps_allows_provider_model_mapping(config_module):
    provider_map, model_map = config_module.build_maps(
        {
            "models": {
                "alpha-1": {},
                "alpha-2": {},
            },
            "providers": {
                "alpha": {
                    "base_url": "https://alpha.example/v1",
                    "models": {
                        "alpha-1": {},
                        "alpha-2": {
                            "cost": {"input": 1.0, "output": 2.0, "cacheRead": 0.1}
                        },
                    },
                },
            },
        }
    )

    assert provider_map["alpha"] == config_module.ProviderConfig(
        name="alpha",
        base_url="https://alpha.example/v1",
    )
    assert model_map["alpha-1"] == provider_map["alpha"]
    assert model_map["alpha-2"] == provider_map["alpha"]


def test_build_maps_parses_provider_price_multiplier(config_module):
    provider_map, model_map = config_module.build_maps(
        {
            "models": {"alpha-1": {}},
            "providers": {
                "alpha": {
                    "base_url": "https://alpha.example/v1",
                    "price_multiplier": 1.35,
                    "models": {"alpha-1": {}},
                },
            },
        }
    )

    assert provider_map["alpha"] == config_module.ProviderConfig(
        name="alpha",
        base_url="https://alpha.example/v1",
        price_multiplier=1.35,
    )
    assert model_map["alpha-1"] == provider_map["alpha"]


def test_build_maps_allows_provider_without_models(config_module):
    provider_map, model_map = config_module.build_maps(
        {
            "models": {},
            "providers": {
                "empty": {
                    "base_url": "https://empty.example/v1",
                    "api_key": "empty-key",
                },
            },
        }
    )

    assert provider_map["empty"] == config_module.ProviderConfig(
        name="empty",
        base_url="https://empty.example/v1",
    )
    assert model_map == {}


def test_build_cost_maps_parses_global_and_provider_model_costs(config_module):
    model_costs, provider_model_costs = config_module.build_cost_maps(
        {
            "models": {
                "alpha-1": {"cost": {"input": 1.5, "output": 2.5, "cacheRead": 0.15}},
                "beta-1": {},
            },
            "providers": {
                "alpha": {
                    "base_url": "https://alpha.example/v1",
                    "models": {
                        "alpha-1": {
                            "cost": {"input": 3.0, "output": 4.0, "cacheRead": 0.3}
                        },
                        "beta-1": {},
                    },
                },
            },
        }
    )

    assert model_costs["alpha-1"] == config_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
    )
    assert "beta-1" not in model_costs
    assert provider_model_costs == {
        "alpha": {
            "alpha-1": config_module.ModelCost(
                input=3.0,
                output=4.0,
                cache_read=0.3,
            )
        }
    }


def test_build_cost_maps_ignores_cache_write(config_module):
    model_costs, provider_model_costs = config_module.build_cost_maps(
        {
            "models": {
                "alpha-1": {
                    "cost": {
                        "input": 1.5,
                        "output": 2.5,
                        "cacheRead": 0.15,
                        "cacheWrite": 1.875,
                    }
                }
            },
            "providers": {
                "alpha": {
                    "base_url": "https://alpha.example/v1",
                    "models": {
                        "alpha-1": {
                            "cost": {
                                "input": 3.0,
                                "output": 4.0,
                                "cacheRead": 0.3,
                                "cacheWrite": 3.75,
                            }
                        }
                    },
                }
            },
        }
    )

    assert model_costs["alpha-1"] == config_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
    )
    assert provider_model_costs["alpha"]["alpha-1"] == config_module.ModelCost(
        input=3.0,
        output=4.0,
        cache_read=0.3,
    )


def test_build_cost_maps_normalizes_model_keys_to_lowercase(config_module):
    model_costs, provider_model_costs = config_module.build_cost_maps(
        {
            "models": {
                "MiniMax-M2.7": {
                    "cost": {"input": 1.5, "output": 2.5, "cacheRead": 0.15}
                }
            },
            "providers": {
                "minimax": {
                    "base_url": "https://api.minimax.example/v1",
                    "models": {
                        "MiniMax-M2.7": {
                            "cost": {"input": 3.0, "output": 4.0, "cacheRead": 0.3}
                        }
                    },
                }
            },
        }
    )

    assert "MiniMax-M2.7" not in model_costs
    assert model_costs["minimax-m2.7"] == config_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
    )
    assert "MiniMax-M2.7" not in provider_model_costs["minimax"]
    assert provider_model_costs["minimax"]["minimax-m2.7"] == (
        config_module.ModelCost(
            input=3.0,
            output=4.0,
            cache_read=0.3,
        )
    )


def test_refresh_runtime_config_updates_globals_in_place(
    config_module, tmp_path, monkeypatch
):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path.write_text(
        """
server:
  host: 127.0.0.1
models:
  alpha-1:
    cost:
      input: 1.0
      output: 2.0
      cacheRead: 0.1
providers:
  alpha:
    base_url: https://alpha.example/v1
    models:
      alpha-1:
        cost:
          input: 3.0
          output: 4.0
          cacheRead: 0.3
""",
        encoding="utf-8",
    )

    config_id = id(config_module.CONFIG)
    provider_map_id = id(config_module.PROVIDER_MAP)
    model_map_id = id(config_module.MODEL_MAP)

    refreshed = config_module.refresh_runtime_config(str(config_path))

    assert id(config_module.CONFIG) == config_id
    assert id(config_module.PROVIDER_MAP) == provider_map_id
    assert id(config_module.MODEL_MAP) == model_map_id
    assert refreshed is config_module.CONFIG
    assert config_module.CONFIG["server"]["host"] == "127.0.0.1"
    assert config_module.PROVIDER_MAP["alpha"] == config_module.ProviderConfig(
        name="alpha",
        base_url="https://alpha.example/v1",
    )
    assert config_module.MODEL_MAP["alpha-1"] == config_module.ProviderConfig(
        name="alpha",
        base_url="https://alpha.example/v1",
    )
    assert config_module.MODEL_COSTS["alpha-1"] == config_module.ModelCost(
        input=1.0,
        output=2.0,
        cache_read=0.1,
    )
    assert config_module.PROVIDER_MODEL_COSTS["alpha"]["alpha-1"] == (
        config_module.ModelCost(
            input=3.0,
            output=4.0,
            cache_read=0.3,
        )
    )


def test_merge_missing_config_defaults_backfills_missing_fields(config_module):
    user_config = {
        "models": {
            "gpt-5": {
                "cost": {
                    "input": 9.0,
                }
            }
        },
        "providers": {
            "anthropic": {
                "base_url": "https://api.anthropic.com/v1",
                "models": {"claude-sonnet-4": {}},
            }
        },
        "server": {
            "port": 4100,
        },
    }
    default_config = {
        "models": {
            "gpt-5": {
                "cost": {
                    "input": 1.25,
                    "output": 10.0,
                    "cacheRead": 0.125,
                }
            },
            "gpt-5-mini": {
                "cost": {
                    "input": 0.25,
                    "output": 2.0,
                    "cacheRead": 0.025,
                }
            },
        },
        "providers": {
            "my-provider": {
                "base_url": "https://api.example.com/v1",
                "models": {"gpt-5": {}},
            }
        },
        "server": {
            "host": "127.0.0.1",
            "port": 4000,
            "api_port": 4001,
            "otlp_port": 4002,
        },
        "db": {
            "path": "~/.llm-tracker/usage.db",
        },
    }

    merged_config = config_module.merge_missing_config_defaults(
        user_config, default_config
    )

    assert merged_config["models"]["gpt-5"]["cost"]["input"] == 9.0
    assert merged_config["models"]["gpt-5"]["cost"]["output"] == 10.0
    assert merged_config["models"]["gpt-5"]["cost"]["cacheRead"] == 0.125
    assert merged_config["models"]["gpt-5-mini"]["cost"]["output"] == 2.0
    assert merged_config["server"]["port"] == 4100
    assert merged_config["server"]["host"] == "127.0.0.1"
    assert merged_config["server"]["api_port"] == 4001
    assert merged_config["db"]["path"] == "~/.llm-tracker/usage.db"


def test_merge_missing_config_defaults_skips_example_provider_backfill(config_module):
    user_config = {
        "models": {},
        "providers": {
            "anthropic": {
                "base_url": "https://api.anthropic.com/v1",
                "models": {"claude-sonnet-4": {}},
            }
        },
    }
    default_config = {
        "providers": {
            "my-provider": {
                "base_url": "https://api.example.com/v1",
                "models": {"gpt-5": {}},
            }
        }
    }

    merged_config = config_module.merge_missing_config_defaults(
        user_config, default_config
    )

    assert "my-provider" not in merged_config["providers"]


def test_sync_config_script_runs_without_pythonpath(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "sync-config.py"
    user_config_path = tmp_path / "config.yaml"
    default_config_path = tmp_path / "config.example.yaml"

    user_config_path.write_text(
        """
models:
  gpt-5:
    cost:
      input: 9.0
""",
        encoding="utf-8",
    )
    default_config_path.write_text(
        """
models:
  gpt-5:
    cost:
      input: 1.25
      output: 10.0
  gpt-5.5:
    cost:
      input: 5.0
      output: 30.0
server:
  host: 127.0.0.1
""",
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            str(user_config_path),
            str(default_config_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr

    merged_config = yaml.safe_load(user_config_path.read_text(encoding="utf-8"))
    assert merged_config["models"]["gpt-5"]["cost"]["input"] == 9.0
    assert merged_config["models"]["gpt-5"]["cost"]["output"] == 10.0
    assert merged_config["models"]["gpt-5.5"]["cost"]["input"] == 5.0
    assert merged_config["server"]["host"] == "127.0.0.1"


def test_configure_codex_settings_prefers_otlp_endpoint_env(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "configure-codex-settings.py"
    config_path = tmp_path / "config.toml"
    env = os.environ.copy()
    env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = "http://127.0.0.1:49153/v1/logs"

    result = subprocess.run(
        [sys.executable, str(script_path), str(config_path), "4005"],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    content = config_path.read_text(encoding="utf-8")
    assert 'endpoint = "http://127.0.0.1:49153/v1/logs"' in content
    assert "localhost:4005" not in content


def test_configure_codex_settings_uses_configured_port_without_env(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "configure-codex-settings.py"
    config_path = tmp_path / "config.toml"
    env = os.environ.copy()
    env.pop("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", None)

    result = subprocess.run(
        [sys.executable, str(script_path), str(config_path), "4005"],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    content = config_path.read_text(encoding="utf-8")
    assert 'endpoint = "http://localhost:4005/v1/logs"' in content


def test_configure_codex_settings_updates_existing_otel_with_endpoint_env(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "configure-codex-settings.py"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[otel]
environment = "dev"
exporter = { otlp-http = { endpoint = "http://localhost:4005/v1/logs", protocol = "json" } }
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = "http://127.0.0.1:49153/v1/logs"

    result = subprocess.run(
        [sys.executable, str(script_path), str(config_path), "4005"],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    content = config_path.read_text(encoding="utf-8")
    assert 'endpoint = "http://127.0.0.1:49153/v1/logs"' in content
    assert "localhost:4005" not in content


def test_configure_codex_settings_updates_nested_otel_endpoint(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "configure-codex-settings.py"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[otel]
environment = "dev"

[otel.exporter]
[otel.exporter.otlp-http]
endpoint = "http://localhost:4005/v1/logs"
protocol = "json"
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = "http://127.0.0.1:49153/v1/logs"

    result = subprocess.run(
        [sys.executable, str(script_path), str(config_path), "4005"],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    content = config_path.read_text(encoding="utf-8")
    assert 'endpoint = "http://127.0.0.1:49153/v1/logs"' in content
    assert "localhost:4005" not in content
    assert 'protocol = "json"' in content


def test_configure_claude_settings_prefers_otlp_endpoint_env(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "configure-claude-settings.py"
    settings_path = tmp_path / "settings.json"
    env = os.environ.copy()
    env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = "http://127.0.0.1:49153/v1/logs"

    result = subprocess.run(
        [sys.executable, str(script_path), str(settings_path), "4005"],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    assert (
        settings["env"]["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"]
        == "http://127.0.0.1:49153/v1/logs"
    )


def test_otlp_gunicorn_config_prefers_otlp_endpoint_env(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / ".llm-tracker"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        """
server:
  host: 127.0.0.1
  port: 4000
  api_port: 4001
  otlp_port: 4005
db:
  path: usage.db
providers: {}
models: {}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "http://127.0.0.1:49153/v1/logs",
    )

    namespace = runpy.run_path(str(repo_root / "config" / "otlp.conf.py"))

    assert namespace["bind"] == "127.0.0.1:49153"


def test_otlp_gunicorn_config_uses_configured_port_without_env(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / ".llm-tracker"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        """
server:
  host: 127.0.0.1
  port: 4000
  api_port: 4001
  otlp_port: 4005
db:
  path: usage.db
providers: {}
models: {}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)

    namespace = runpy.run_path(str(repo_root / "config" / "otlp.conf.py"))

    assert namespace["bind"] == "127.0.0.1:4005"
