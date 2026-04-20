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
            "providers": {
                "alpha": {
                    "base_url": "https://alpha.example/v1",
                    "api_key": "alpha-key",
                    "models": ["alpha-1", "alpha-2"],
                },
                "beta": {
                    "base_url": "https://beta.example/v1",
                    "api_key": "beta-key",
                    "models": ["beta-1"],
                },
            }
        }
    )

    assert model_map["alpha-1"] == config_module.ProviderConfig(
        name="alpha",
        base_url="https://alpha.example/v1",
    )
    assert model_map["beta-1"].name == "beta"
    assert provider_map["alpha"].name == "alpha"


def test_build_maps_allows_provider_without_models(config_module):
    provider_map, model_map = config_module.build_maps(
        {
            "providers": {
                "empty": {
                    "base_url": "https://empty.example/v1",
                    "api_key": "empty-key",
                },
            }
        }
    )

    assert provider_map["empty"] == config_module.ProviderConfig(
        name="empty",
        base_url="https://empty.example/v1",
    )
    assert model_map == {}
