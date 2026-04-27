from pathlib import Path


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
