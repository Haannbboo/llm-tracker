from fastapi.testclient import TestClient


def test_local_setup_health_reports_agent_otlp_config_status(api_module, isolated_home):
    home = isolated_home
    claude_dir = home / ".claude"
    codex_dir = home / ".codex"
    gemini_dir = home / ".gemini"
    claude_dir.mkdir()
    codex_dir.mkdir()
    gemini_dir.mkdir()

    claude_dir.joinpath("settings.json").write_text(
        """{
          "env": {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:4002/v1/logs",
            "API_KEY": "super-secret"
          }
        }""",
        encoding="utf-8",
    )
    codex_dir.joinpath("config.toml").write_text(
        """[otel]
enabled = true
[otel.exporter.otlp-http]
endpoint = "http://localhost:9999/v1/logs"
protocol = "json"
api_key = "super-secret"
""",
        encoding="utf-8",
    )
    gemini_dir.joinpath("settings.json").write_text(
        """{
          "telemetry": {
            "enabled": true,
            "target": "local",
            "otlpEndpoint": "http://localhost:4002",
            "otlpProtocol": "http",
            "token": "super-secret"
          }
        }""",
        encoding="utf-8",
    )

    response = TestClient(api_module.app).get("/local/setup-health")

    assert response.status_code == 200
    data = response.json()
    assert data["expected"]["otlp_logs_endpoint"] == "http://localhost:4002/v1/logs"
    assert data["expected"]["otlp_endpoint"] == "http://localhost:4002"
    assert data["summary"] == {
        "total_agents": 3,
        "configured_agents": 3,
        "matching_agents": 2,
    }

    agents = data["agents"]
    assert agents["claude"]["configured"] is True
    assert agents["claude"]["endpoint_matches"] is True
    assert agents["claude"]["configured_endpoint"] == "http://localhost:4002/v1/logs"
    assert agents["codex"]["configured"] is True
    assert agents["codex"]["endpoint_matches"] is False
    assert agents["codex"]["configured_endpoint"] == "http://localhost:9999/v1/logs"
    assert agents["gemini"]["configured"] is True
    assert agents["gemini"]["endpoint_matches"] is True
    assert agents["gemini"]["configured_endpoint"] == "http://localhost:4002"

    assert "super-secret" not in response.text
    assert "api_key" not in response.text.lower()
    assert "token" not in response.text.lower()


def test_local_setup_health_handles_missing_agent_configs(api_module):
    response = TestClient(api_module.app).get("/local/setup-health")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {
        "total_agents": 3,
        "configured_agents": 0,
        "matching_agents": 0,
    }
    for agent in data["agents"].values():
        assert agent["configured"] is False
        assert agent["endpoint_matches"] is False
        assert agent["configured_endpoint"] is None
        assert agent["status"] == "missing_config"
