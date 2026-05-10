import asyncio
from decimal import Decimal

from fastapi.testclient import TestClient


def test_usage_daily_endpoint_exists(api_module):
    # This just verifies the endpoint function is defined
    assert hasattr(api_module, "usage_daily")
    assert callable(api_module.usage_daily)


def test_usage_high_watermark_endpoint(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "get_usage_high_watermark", lambda: 42)

    result = asyncio.run(api_module.usage_high_watermark())

    assert result == {"id": 42}


def test_usage_run_summary_endpoint_passes_filters(api_module, monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {
            "window": {"after_id": 5, "until_id": 9, "row_count": 1},
            "summary": {"requests": 1},
            "sessions": [],
            "client_sources": [],
            "models": [],
        }

    monkeypatch.setattr(api_module, "summarize_usage_window", fake_summary)

    result = asyncio.run(
        api_module.usage_run_summary(
            after_id=5,
            until_id=9,
            since="2026-04-17T00:00:00+00:00",
            until="2026-04-18T00:00:00+00:00",
            client_source="codex",
            session_id="conv-1",
            provider="openai",
            model="gpt-test",
            include_rows=True,
        )
    )

    assert captured == {
        "after_id": 5,
        "until_id": 9,
        "since": "2026-04-17T00:00:00+00:00",
        "until": "2026-04-18T00:00:00+00:00",
        "client_source": "codex",
        "session_id": "conv-1",
        "provider": "openai",
        "model": "gpt-test",
        "include_rows": True,
    }
    assert result["summary"]["requests"] == 1


def test_usage_high_watermark_route(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "get_usage_high_watermark", lambda: 42)

    response = TestClient(api_module.app).get("/usage/high-watermark")

    assert response.status_code == 200
    assert response.json() == {"id": 42}


def test_usage_run_summary_route_parses_query_filters(api_module, monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {
            "window": {"after_id": 5, "until_id": 9, "row_count": 1},
            "summary": {"requests": 1},
            "sessions": [],
            "client_sources": [],
            "models": [],
        }

    monkeypatch.setattr(api_module, "summarize_usage_window", fake_summary)

    response = TestClient(api_module.app).get(
        "/usage/run-summary",
        params={
            "after_id": "5",
            "until_id": "9",
            "since": "2026-04-17T00:00:00+00:00",
            "until": "2026-04-18T00:00:00+00:00",
            "client_source": "codex",
            "session_id": "conv-1",
            "provider": "openai",
            "model": "gpt-test",
            "include_rows": "true",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "after_id": 5,
        "until_id": 9,
        "since": "2026-04-17T00:00:00+00:00",
        "until": "2026-04-18T00:00:00+00:00",
        "client_source": "codex",
        "session_id": "conv-1",
        "provider": "openai",
        "model": "gpt-test",
        "include_rows": True,
    }
    assert response.json()["summary"]["requests"] == 1


def test_usage_ingest_route_persists_usage(api_module, monkeypatch):
    captured = {}

    def fake_log_usage(usage):
        captured["usage"] = usage

    def fake_resolve_base_url_id(**kwargs):
        captured["base_url"] = kwargs
        return 7

    monkeypatch.setattr(api_module, "log_usage", fake_log_usage, raising=False)
    monkeypatch.setattr(
        api_module, "resolve_base_url_id", fake_resolve_base_url_id, raising=False
    )
    monkeypatch.setattr(
        api_module,
        "calculate_costs",
        lambda **kwargs: {
            "input_cost_usd": Decimal("0.01000000"),
            "output_cost_usd": Decimal("0.02000000"),
            "total_cost_usd": Decimal("0.03000000"),
        },
        raising=False,
    )

    response = TestClient(api_module.app).post(
        "/usage",
        json={
            "ts": "2026-05-03T17:00:00+00:00",
            "provider": "codesonline",
            "model": "gpt-5.5",
            "client_source": "codex",
            "session_id": "codex-session-1",
            "endpoint": "generate-otlp",
            "prompt_tokens": 21742,
            "completion_tokens": 6,
            "cached_tokens": 6528,
            "reasoning_tokens": 0,
            "total_tokens": 21748,
            "latency_ms": 12338,
            "ttft_ms": 8263,
            "base_url": "https://free.codesonline.dev",
            "base_url_source": "codex_config",
        },
    )

    assert response.status_code == 201
    assert response.json() == {"status": "success"}
    usage = captured["usage"]
    assert usage.provider == "codesonline"
    assert usage.model == "gpt-5.5"
    assert usage.client_source == "codex"
    assert usage.session_id == "codex-session-1"
    assert usage.prompt_tokens == 21742
    assert usage.completion_tokens == 6
    assert usage.cached_tokens == 6528
    assert usage.total_tokens == 21748
    assert usage.input_cost_usd == Decimal("0.01000000")
    assert usage.output_cost_usd == Decimal("0.02000000")
    assert usage.total_cost_usd == Decimal("0.03000000")
    assert usage.base_url_id == 7
    assert captured["base_url"] == {
        "base_url": "https://free.codesonline.dev",
        "provider_name": "codesonline",
        "source": "codex_config",
    }


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
models:
  new-model: {}
providers:
  new-provider:
    base_url: https://new.example/v1
    models:
      new-model: {}
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


def test_usage_endpoint_passes_client_source(api_module, monkeypatch):
    captured = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(api_module, "fetch_recent_usage", fake_fetch)

    response = TestClient(api_module.app).get(
        "/usage", params={"client_source": "claude-code", "limit": "10"}
    )
    assert response.status_code == 200
    assert captured["client_source"] == "claude-code"


def test_usage_count_endpoint_passes_client_source(api_module, monkeypatch):
    captured = {}

    def fake_count(**kwargs):
        captured.update(kwargs)
        return 5

    monkeypatch.setattr(api_module, "count_usage", fake_count)

    response = TestClient(api_module.app).get(
        "/usage/count", params={"client_source": "codex"}
    )
    assert response.status_code == 200
    assert captured["client_source"] == "codex"


def test_usage_summary_endpoint_passes_client_source(api_module, monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(api_module, "summarize_usage_daily", fake_summary)

    response = TestClient(api_module.app).get(
        "/usage/summary", params={"client_source": "gemini-cli"}
    )
    assert response.status_code == 200
    assert captured["client_source"] == "gemini-cli"


def test_usage_daily_endpoint_passes_client_source(api_module, monkeypatch):
    captured = {}

    def fake_daily(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(api_module, "aggregate_daily_by_period", fake_daily)

    response = TestClient(api_module.app).get(
        "/usage/daily", params={"client_source": "claude-code"}
    )
    assert response.status_code == 200
    assert captured["client_source"] == "claude-code"


def test_usage_by_source_endpoint(api_module, monkeypatch):
    captured = {}

    def fake_by_source(**kwargs):
        captured.update(kwargs)
        return [
            {
                "client_source": "claude-code",
                "requests": 10,
                "prompt_tokens": 5000,
                "completion_tokens": 3000,
                "reasoning_tokens": 0,
                "cached_tokens": 1000,
                "total_tokens": 8000,
                "avg_latency_ms": 250.0,
                "input_cost_usd": 0.01,
                "output_cost_usd": 0.02,
                "total_cost_usd": 0.03,
                "successful_requests": 9,
                "failed_requests": 1,
            },
            {
                "client_source": "codex",
                "requests": 5,
                "prompt_tokens": 2000,
                "completion_tokens": 1000,
                "reasoning_tokens": 0,
                "cached_tokens": 500,
                "total_tokens": 3000,
                "avg_latency_ms": 180.0,
                "input_cost_usd": 0.005,
                "output_cost_usd": 0.01,
                "total_cost_usd": 0.015,
                "successful_requests": 5,
                "failed_requests": 0,
            },
        ]

    monkeypatch.setattr(api_module, "summarize_usage_by_source", fake_by_source)

    response = TestClient(api_module.app).get(
        "/usage/by-source",
        params={
            "since": "2026-01-01",
            "until": "2026-12-31",
            "client_source": "claude-code",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["client_source"] == "claude-code"
    assert data[0]["requests"] == 10
    assert captured["since"] == "2026-01-01"
    assert captured["client_source"] == "claude-code"


def test_usage_by_source_endpoint_passes_all_filters(api_module, monkeypatch):
    captured = {}

    def fake_by_source(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(api_module, "summarize_usage_by_source", fake_by_source)

    response = TestClient(api_module.app).get(
        "/usage/by-source",
        params={"provider": "openai", "model": "gpt-4o"},
    )
    assert response.status_code == 200
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-4o"


def test_usage_by_provider_endpoint_includes_avg_effective_price_per_million(
    api_module, monkeypatch
):
    captured = {}

    def fake_by_provider(**kwargs):
        captured.update(kwargs)
        return [
            {
                "provider": "openai",
                "requests": 3,
                "prompt_tokens": 600,
                "completion_tokens": 300,
                "reasoning_tokens": 0,
                "cached_tokens": 100,
                "total_tokens": 900,
                "avg_latency_ms": 210.0,
                "input_cost_usd": 0.003,
                "output_cost_usd": 0.006,
                "total_cost_usd": 0.009,
                "avg_effective_price_usd": 0.00001,
                "avg_effective_price_per_million_usd": 10.0,
                "successful_requests": 3,
                "failed_requests": 0,
            }
        ]

    monkeypatch.setattr(api_module, "summarize_usage_by_provider", fake_by_provider)

    response = TestClient(api_module.app).get(
        "/usage/by-provider",
        params={"provider": "openai", "model": "gpt-4o", "client_source": "codex"},
    )

    assert response.status_code == 200
    assert response.json()[0]["avg_effective_price_per_million_usd"] == 10.0
    assert captured == {
        "since": None,
        "until": None,
        "provider": "openai",
        "model": "gpt-4o",
        "client_source": "codex",
    }


def test_connectivity_endpoint(api_module, monkeypatch):
    class FakeResponse:
        def __init__(self):
            self.status_code = 200
            self.text = '{"ok": true}'

        def json(self):
            return {"ok": True}

    async def fake_post(*args, **kwargs):
        return FakeResponse()

    # Mock httpx.AsyncClient.post
    from unittest.mock import AsyncMock, MagicMock

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=fake_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    response = TestClient(api_module.app).post(
        "/test-connectivity",
        json={
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "format": "openai",
            "model": "gpt-test",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status_code"] == 200
    assert data["body"] == {"ok": True}
    assert "latency_ms" in data
    assert data["url"] == "https://api.openai.com/v1/chat/completions"


def test_connectivity_endpoint_adds_v1(api_module, monkeypatch):
    captured = {}

    async def fake_post(url, **kwargs):
        captured["url"] = url

        class FakeResponse:
            status_code = 200
            text = '{"ok": true}'

            def json(self):
                return {"ok": True}

        return FakeResponse()

    from unittest.mock import AsyncMock, MagicMock

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=fake_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    TestClient(api_module.app).post(
        "/test-connectivity",
        json={
            "base_url": "https://free.codesonline.dev",
            "api_key": "sk-test",
            "format": "openai",
        },
    )

    assert captured["url"] == "https://free.codesonline.dev/v1/chat/completions"


def test_connectivity_endpoint_deduplicates_url(api_module, monkeypatch):
    captured = {}

    async def fake_post(url, **kwargs):
        captured["url"] = url

        class FakeResponse:
            status_code = 200
            text = '{"ok": true}'

            def json(self):
                return {"ok": True}

        return FakeResponse()

    from unittest.mock import AsyncMock, MagicMock

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=fake_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    TestClient(api_module.app).post(
        "/test-connectivity",
        json={
            "base_url": "https://api.openai.com/v1/chat/completions",
            "api_key": "sk-test",
            "format": "openai",
        },
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"


def test_daily_by_dimension_returns_per_model_data(api_module, monkeypatch):
    """GET /usage/daily-by-dimension returns daily data grouped by model."""
    captured = {}

    def fake_daily_by_dimension(**kwargs):
        captured.update(kwargs)
        return [
            {
                "dimension": "claude-sonnet-4-6",
                "period": "2026-05-07",
                "total_tokens": 1000,
                "total_cost_usd": 0.01,
                "requests": 1,
                "completion_tokens": 400,
                "latency_sum_ms": 500,
                "successful_requests": 1,
                "failed_requests": 0,
            }
        ]

    monkeypatch.setattr(
        api_module, "aggregate_daily_by_dimension", fake_daily_by_dimension
    )

    response = TestClient(api_module.app).get(
        "/usage/daily-by-dimension",
        params={
            "dimension": "model",
            "since": "2026-05-07T00:00:00Z",
            "until": "2026-05-08T00:00:00Z",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["dimension"] == "claude-sonnet-4-6"
    assert "period" in data[0]
    assert "total_tokens" in data[0]


def test_daily_by_dimension_endpoint_passes_all_filters(api_module, monkeypatch):
    """GET /usage/daily-by-dimension passes all filter params to the database function."""
    captured = {}

    def fake_daily_by_dimension(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        api_module, "aggregate_daily_by_dimension", fake_daily_by_dimension
    )

    response = TestClient(api_module.app).get(
        "/usage/daily-by-dimension",
        params={
            "dimension": "provider",
            "since": "2026-05-01T00:00:00Z",
            "until": "2026-05-08T00:00:00Z",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "client_source": "claude-code",
        },
    )
    assert response.status_code == 200
    assert captured == {
        "dimension": "provider",
        "since": "2026-05-01T00:00:00Z",
        "until": "2026-05-08T00:00:00Z",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "client_source": "claude-code",
    }


def test_sessions_endpoint_exists(api_module):
    assert hasattr(api_module, "get_sessions")
    assert callable(api_module.get_sessions)


def test_sessions_endpoint_passes_filters(api_module, monkeypatch):
    captured = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return []

    def fake_count(**kwargs):
        return 0

    monkeypatch.setattr(api_module, "fetch_sessions", fake_fetch)
    monkeypatch.setattr(api_module, "count_sessions", fake_count)

    response = TestClient(api_module.app).get(
        "/sessions",
        params={
            "client_source": "claude-code",
            "since": "2026-05-01T00:00:00Z",
            "until": "2026-05-10T00:00:00Z",
            "sort_by": "total_cost_usd",
            "sort_order": "asc",
            "limit": "25",
            "offset": "10",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert "total" in data
    assert captured["client_source"] == "claude-code"
    assert captured["since"] == "2026-05-01T00:00:00Z"
    assert captured["sort_by"] == "total_cost_usd"
    assert captured["sort_order"] == "asc"
    assert captured["limit"] == 25
    assert captured["offset"] == 10


def test_sessions_summary_endpoint_passes_filters(api_module, monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {
            "session_count": 3,
            "avg_duration_s": 120,
            "total_tokens": 5000,
            "total_cost_usd": 0.05,
            "avg_latency_ms": 250.0,
        }

    monkeypatch.setattr(api_module, "summarize_sessions", fake_summary)

    response = TestClient(api_module.app).get(
        "/sessions/summary",
        params={"client_source": "gemini-cli"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_count"] == 3
    assert data["total_tokens"] == 5000
    assert captured["client_source"] == "gemini-cli"


def test_usage_endpoint_passes_session_id(api_module, monkeypatch):
    captured = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(api_module, "fetch_recent_usage", fake_fetch)

    response = TestClient(api_module.app).get(
        "/usage", params={"session_id": "sess-123", "limit": "10"}
    )
    assert response.status_code == 200
    assert captured["session_id"] == "sess-123"


def test_usage_count_endpoint_passes_session_id(api_module, monkeypatch):
    captured = {}

    def fake_count(**kwargs):
        captured.update(kwargs)
        return 3

    monkeypatch.setattr(api_module, "count_usage", fake_count)

    response = TestClient(api_module.app).get(
        "/usage/count", params={"session_id": "sess-123"}
    )
    assert response.status_code == 200
    assert captured["session_id"] == "sess-123"
