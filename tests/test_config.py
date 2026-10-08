import runpy
import threading
from pathlib import Path

import pytest
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
  path: ~/.tokenage/usage.db
providers: {}
""",
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert config["db"]["path"] == str(Path(tmp_path, ".tokenage/usage.db"))
    assert config["db"]["url"] == f"sqlite:///{Path(tmp_path, '.tokenage/usage.db')}"


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


def test_load_config_normalizes_provider_keys(config_module, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n  OpenAI:\n    base_url: https://api.example.com/v1\n",
        encoding="utf-8",
    )
    config = config_module.load_config(str(config_path))
    assert set(config["providers"]) == {"openai"}
    assert config["providers"]["openai"]["base_url"] == "https://api.example.com/v1"


def test_load_config_rejects_nonpositive_record_cap(config_module, tmp_path):
    """A 0/negative record cap would silently drop every export; default wins."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: 127.0.0.1
providers: {}
otlp:
  max_records_per_request: 0
""",
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert config["otlp"]["max_records_per_request"] == 1_000


def test_load_config_keeps_database_url(config_module, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: 127.0.0.1
db:
  url: postgresql+psycopg://user:pass@db.example.edu:5432/tokenage
providers: {}
""",
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert (
        config["db"]["url"]
        == "postgresql+psycopg://user:pass@db.example.edu:5432/tokenage"
    )


def test_get_config_path_prefers_env_override(config_module, tmp_path, monkeypatch):
    config_path = tmp_path / "custom-config.yaml"
    monkeypatch.setenv("TOKENAGE_CONFIG", str(config_path))

    assert config_module.get_config_path() == str(config_path)


def test_get_tracker_home_prefers_env_override(config_module, tmp_path, monkeypatch):
    tracker_home = tmp_path / "tracker-home"
    monkeypatch.setenv("TOKENAGE_HOME", str(tracker_home))

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
        api_key="alpha-key",
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
                "AlPhA": {
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
        api_key="empty-key",
    )
    assert model_map == {}


def test_build_maps_skips_disabled_provider(config_module):
    provider_map, model_map = config_module.build_maps(
        {
            "models": {},
            "providers": {
                "live": {
                    "base_url": "https://live.example/v1",
                    "models": {"live-1": {}},
                },
                "paused": {
                    "enabled": False,
                    "base_url": "https://paused.example/v1",
                    "api_key": "paused-key",
                    "models": {"paused-1": {}},
                },
            },
        }
    )

    assert "paused" not in provider_map
    assert "paused-1" not in model_map
    assert provider_map["live"].name == "live"
    assert model_map["live-1"].name == "live"


def test_build_maps_treats_missing_enabled_as_enabled(config_module):
    provider_map, _ = config_module.build_maps(
        {
            "models": {},
            "providers": {
                "alpha": {
                    "base_url": "https://alpha.example/v1",
                    "enabled": True,
                    "models": {"alpha-1": {}},
                },
            },
        }
    )

    assert provider_map["alpha"].name == "alpha"


def test_build_maps_normalizes_empty_api_key_to_none(config_module):
    provider_map, _ = config_module.build_maps(
        {
            "models": {},
            "providers": {
                "empty-key": {
                    "base_url": "https://empty.example/v1",
                    "api_key": "",
                },
            },
        }
    )

    assert provider_map["empty-key"].api_key is None


def test_resolve_all_costs_parses_global_and_provider_model_costs(
    config_module, pricing_maps_module
):
    resolved = pricing_maps_module.resolve_all_costs(
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

    assert resolved.global_costs["alpha-1"].cost == pricing_maps_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
    )
    assert "beta-1" not in resolved.global_costs
    assert set(resolved.provider_costs) == {"alpha"}
    assert resolved.provider_costs["alpha"]["alpha-1"].cost == (
        pricing_maps_module.ModelCost(
            input=3.0,
            output=4.0,
            cache_read=0.3,
        )
    )


def test_resolve_all_costs_preserves_cache_write_metadata(
    config_module, pricing_maps_module
):
    resolved = pricing_maps_module.resolve_all_costs(
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

    assert resolved.global_costs["alpha-1"].cost == pricing_maps_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
        cache_write=1.875,
    )
    assert resolved.provider_costs["alpha"]["alpha-1"].cost == (
        pricing_maps_module.ModelCost(
            input=3.0,
            output=4.0,
            cache_read=0.3,
            cache_write=3.75,
        )
    )


def test_resolve_all_costs_normalizes_model_keys_to_lowercase(
    config_module, pricing_maps_module
):
    resolved = pricing_maps_module.resolve_all_costs(
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

    assert "MiniMax-M2.7" not in resolved.global_costs
    assert resolved.global_costs["minimax-m2.7"].cost == pricing_maps_module.ModelCost(
        input=1.5,
        output=2.5,
        cache_read=0.15,
    )
    assert "MiniMax-M2.7" not in resolved.provider_costs["minimax"]
    assert resolved.provider_costs["minimax"]["minimax-m2.7"].cost == (
        pricing_maps_module.ModelCost(
            input=3.0,
            output=4.0,
            cache_read=0.3,
        )
    )


def test_refresh_runtime_config_updates_globals_in_place(
    config_module, tmp_path, monkeypatch, pricing_maps_module
):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path.write_text(
        """
pricing:
  auto_fetch: false
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
    assert pricing_maps_module.MODEL_COSTS["alpha-1"] == pricing_maps_module.ModelCost(
        input=1.0,
        output=2.0,
        cache_read=0.1,
    )
    assert pricing_maps_module.PROVIDER_MODEL_COSTS["alpha"]["alpha-1"] == (
        pricing_maps_module.ModelCost(
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
            "path": "~/.tokenage/usage.db",
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
    assert merged_config["db"]["path"] == "~/.tokenage/usage.db"


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


def test_otlp_gunicorn_config_prefers_otlp_endpoint_env(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / ".tokenage"
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

    namespace = runpy.run_path(str(repo_root / "src" / "config" / "otlp.conf.py"))

    assert namespace["bind"] == "127.0.0.1:49153"


def test_otlp_gunicorn_config_uses_configured_port_without_env(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / ".tokenage"
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

    namespace = runpy.run_path(str(repo_root / "src" / "config" / "otlp.conf.py"))

    assert namespace["bind"] == "127.0.0.1:4005"


def test_gunicorn_configs_resolve_log_paths_to_repo_root(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / ".tokenage"
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

    for conf in ("api.conf.py", "proxy.conf.py", "otlp.conf.py"):
        namespace = runpy.run_path(str(repo_root / "src" / "config" / conf))
        assert namespace["ROOT"] == str(repo_root)


def test_replace_contents_updates_keys(config_module):
    target = {"a": 1, "b": 2, "c": 3}
    source = {"a": 10, "b": 20, "d": 40}
    config_module._replace_contents(target, source)
    assert target == {"a": 10, "b": 20, "d": 40}
    assert "c" not in target


def test_replace_contents_empty_source(config_module):
    target = {"a": 1, "b": 2}
    source = {}
    config_module._replace_contents(target, source)
    assert target == {}


def test_replace_contents_no_stale_keys(config_module):
    target = {"a": 1}
    source = {"a": 2}
    config_module._replace_contents(target, source)
    assert target == {"a": 2}


def test_replace_contents_concurrent_readers_never_see_empty(config_module):
    target = {f"key{i}": i for i in range(100)}
    errors = []

    def reader():
        for _ in range(1000):
            if not target:
                errors.append("saw empty dict")
                return

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()

    new_source = {f"key{i}": i * 10 for i in range(50, 150)}
    config_module._replace_contents(target, new_source)

    for thread in threads:
        thread.join()

    assert not errors


def test_set_evaluation_evaluator(config_module, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("evaluation:\n  evaluator: codex\n", encoding="utf-8")

    config_module.set_evaluation_evaluator("claude", str(config_path))

    content = config_path.read_text(encoding="utf-8")
    assert "evaluator: claude" in content
    assert config_module.CONFIG["evaluation"]["evaluator"] == "claude"


def test_load_config_auth_defaults(config_module, tmp_path, monkeypatch):
    monkeypatch.delenv("TOKENAGE_AUTH__GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("TOKENAGE_AUTH__GOOGLE_CLIENT_SECRET", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("providers: {}\n", encoding="utf-8")

    config = config_module.load_config(str(config_path))

    assert config["auth"]["provider"] == "local"
    assert config["auth"]["allowlist"] == []
    assert config["auth"]["google_client_id"] == ""
    assert config["auth"]["google_client_secret"] == ""


@pytest.mark.parametrize(
    "auth_yaml,provider",
    [
        ("auth: {}\n", "local"),
        ("auth:\n  provider: google\n", "google"),
    ],
)
def test_load_config_auth_provider_mapping(
    config_module, tmp_path, auth_yaml, provider
):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(auth_yaml, encoding="utf-8")

    assert config_module.load_config(str(config_path))["auth"]["provider"] == provider


def test_load_config_rejects_unknown_auth_provider(config_module, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  provider: github\n", encoding="utf-8")

    with pytest.raises(ValueError, match="auth.provider"):
        config_module.load_config(str(config_path))


def test_load_config_google_creds_prefer_env(config_module, tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "auth:\n  provider: google\n  google_client_id: from-yaml\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TOKENAGE_AUTH__GOOGLE_CLIENT_ID", "from-env")
    monkeypatch.setenv("TOKENAGE_AUTH__GOOGLE_CLIENT_SECRET", "from-env-secret")

    config = config_module.load_config(str(config_path))

    assert config["auth"]["provider"] == "google"
    assert config["auth"]["google_client_id"] == "from-env"
    assert config["auth"]["google_client_secret"] == "from-env-secret"


def test_load_config_reads_google_creds_from_yaml(config_module, tmp_path, monkeypatch):
    monkeypatch.delenv("TOKENAGE_AUTH__GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("TOKENAGE_AUTH__GOOGLE_CLIENT_SECRET", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "auth:\n  google_client_id: from-yaml\n  google_client_secret: from-yaml\n",
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert config["auth"]["google_client_id"] == "from-yaml"
    assert config["auth"]["google_client_secret"] == "from-yaml"


def test_set_evaluation_evaluator_creates_missing_parent_dirs(config_module, tmp_path):
    target = tmp_path / ".tokenage" / "nested" / "config.yaml"

    config_module.set_evaluation_evaluator("remote", path=str(target))

    saved = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert saved["evaluation"]["evaluator"] == "remote"
