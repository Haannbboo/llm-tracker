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
