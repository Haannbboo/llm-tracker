import asyncio


def test_usage_daily_endpoint_exists(api_module):
    # This just verifies the endpoint function is defined
    assert hasattr(api_module, "usage_daily")
    assert callable(api_module.usage_daily)


def test_get_config_returns_raw_content_for_malformed_yaml(
    api_module, isolated_home, monkeypatch
):
    config_path = isolated_home / ".llm-tracker" / "broken.yaml"
    config_path.write_text("providers:\n  broken: [\n", encoding="utf-8")
    monkeypatch.setattr(api_module, "CONFIG_PATH", str(config_path))

    result = asyncio.run(api_module.get_config())

    assert result["content"] == "providers:\n  broken: [\n"
    assert result["parsed"] == {}


def test_update_config_refreshes_runtime_config(
    api_module, config_module, isolated_home
):
    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    api_module.CONFIG_PATH = str(config_path)

    result = asyncio.run(
        api_module.update_config(
            api_module.ConfigUpdate(
                content="""
server:
  host: 0.0.0.0
  port: 4000
db:
  path: ~/.llm-tracker/usage.db
providers:
  new-provider:
    base_url: https://new.example/v1
    models:
      - new-model
"""
            )
        )
    )

    assert result == {"status": "success"}
    assert config_module.CONFIG["server"]["host"] == "0.0.0.0"
    assert config_module.PROVIDER_MAP["new-provider"] == config_module.ProviderConfig(
        name="new-provider",
        base_url="https://new.example/v1",
    )
    assert config_module.MODEL_MAP["new-model"] == config_module.ProviderConfig(
        name="new-provider",
        base_url="https://new.example/v1",
    )
