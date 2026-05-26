import asyncio

from fastapi.testclient import TestClient


def test_usage_daily_endpoint_exists(api_module):
    # This just verifies the endpoint function is defined
    assert hasattr(api_module, "usage_daily")
    assert callable(api_module.usage_daily)


def test_lifespan_shutdown_cancels_stuck_evaluation_worker(api_module, monkeypatch):
    started = asyncio.Event()

    async def stuck_worker(**kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(api_module, "init_db", lambda: None)
    monkeypatch.setattr(api_module, "EVALUATION_WORKER_SHUTDOWN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(api_module, "run_evaluation_worker", stuck_worker)
    monkeypatch.setattr(
        api_module,
        "load_evaluation_worker_config",
        lambda: object(),
    )

    async def exercise_lifespan():
        async with api_module.lifespan(api_module.app):
            await asyncio.wait_for(started.wait(), timeout=1)

    asyncio.run(asyncio.wait_for(exercise_lifespan(), timeout=1))


def test_api_defines_bounded_evaluation_worker_shutdown(api_module):
    assert hasattr(api_module, "_stop_evaluation_worker")


def test_usage_high_watermark_endpoint(api_module, monkeypatch):
    monkeypatch.setattr(
        api_module, "get_usage_high_watermark_ts", lambda: 1718000000000000
    )

    result = asyncio.run(api_module.usage_high_watermark())

    assert result == {"ts": 1718000000000000}


def test_usage_run_summary_endpoint_passes_filters(api_module, monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {
            "window": {
                "after_ts": 1718000000000000,
                "until_ts": 1718100000000000,
                "row_count": 1,
            },
            "summary": {"requests": 1},
            "sessions": [],
            "client_sources": [],
            "models": [],
        }

    monkeypatch.setattr(api_module, "summarize_usage_window", fake_summary)

    result = asyncio.run(
        api_module.usage_run_summary(
            after_ts=1718000000000000,
            until_ts=1718100000000000,
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
        "after_ts": 1718000000000000,
        "until_ts": 1718100000000000,
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
    monkeypatch.setattr(
        api_module, "get_usage_high_watermark_ts", lambda: 1718000000000000
    )

    response = TestClient(api_module.app).get("/usage/high-watermark")

    assert response.status_code == 200
    assert response.json() == {"ts": 1718000000000000}


def test_usage_run_summary_route_parses_query_filters(api_module, monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {
            "window": {
                "after_ts": 1718000000000000,
                "until_ts": 1718100000000000,
                "row_count": 1,
            },
            "summary": {"requests": 1},
            "sessions": [],
            "client_sources": [],
            "models": [],
        }

    monkeypatch.setattr(api_module, "summarize_usage_window", fake_summary)

    response = TestClient(api_module.app).get(
        "/usage/run-summary",
        params={
            "after_ts": "1718000000000000",
            "until_ts": "1718100000000000",
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
        "after_ts": 1718000000000000,
        "until_ts": 1718100000000000,
        "since": "2026-04-17T00:00:00+00:00",
        "until": "2026-04-18T00:00:00+00:00",
        "client_source": "codex",
        "session_id": "conv-1",
        "provider": "openai",
        "model": "gpt-test",
        "include_rows": True,
    }
    assert response.json()["summary"]["requests"] == 1


def test_usage_ingest_route_is_not_available(api_module):
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

    assert response.status_code == 405


def test_get_config_returns_raw_content_for_malformed_yaml(
    api_module, isolated_home, monkeypatch
):
    config_path = isolated_home / ".llm-tracker" / "broken.yaml"
    config_path.write_text("providers:\n  broken: [\n", encoding="utf-8")
    monkeypatch.setattr(api_module, "CONFIG_PATH", str(config_path))

    result = asyncio.run(api_module.get_config())

    assert result["content"] == "providers:\n  broken: [\n"
    assert result["parsed"] == {}
    assert result["runtime"]["evaluation"]["evaluator"] == "codex"


def test_get_config_surfaces_runtime_evaluator(api_module, isolated_home, monkeypatch):
    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
evaluation:
  evaluator: claude
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_module, "CONFIG_PATH", str(config_path))

    result = asyncio.run(api_module.get_config())

    assert result["parsed"]["evaluation"]["evaluator"] == "claude"
    assert result["runtime"]["evaluation"]["evaluator"] == "claude"


def test_update_config_refreshes_runtime_config(
    api_module, config_module, isolated_home
):
    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    api_module.CONFIG_PATH = str(config_path)

    result = asyncio.run(
        api_module.update_config(
            api_module.ConfigUpdate(
                content="""
pricing:
  auto_fetch: false
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


def test_usage_endpoint_rejects_negative_offset(api_module, monkeypatch):
    fetch_called = False

    def fake_fetch(**kwargs):
        nonlocal fetch_called
        fetch_called = True
        return []

    monkeypatch.setattr(api_module, "fetch_recent_usage", fake_fetch)

    response = TestClient(api_module.app).get("/usage", params={"offset": "-1"})

    assert response.status_code == 422
    assert fetch_called is False


def test_usage_endpoint_rejects_unbounded_limit(api_module, monkeypatch):
    fetch_called = False

    def fake_fetch(**kwargs):
        nonlocal fetch_called
        fetch_called = True
        return []

    monkeypatch.setattr(api_module, "fetch_recent_usage", fake_fetch)

    response = TestClient(api_module.app).get("/usage", params={"limit": "1001"})

    assert response.status_code == 422
    assert fetch_called is False


def test_usage_endpoint_allows_zero_limit(api_module, monkeypatch):
    captured = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(api_module, "fetch_recent_usage", fake_fetch)

    response = TestClient(api_module.app).get("/usage", params={"limit": "0"})

    assert response.status_code == 200
    assert captured["limit"] == 0


def test_usage_endpoint_includes_cors_for_localhost_origin(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "fetch_recent_usage", lambda **kwargs: [])

    response = TestClient(api_module.app).get(
        "/usage",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_usage_endpoint_preflight_allows_localhost_origin(api_module):
    response = TestClient(api_module.app).options(
        "/usage",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-methods"] == "GET"


def test_usage_endpoint_does_not_include_cors_for_untrusted_origin(
    api_module, monkeypatch
):
    monkeypatch.setattr(api_module, "fetch_recent_usage", lambda **kwargs: [])

    response = TestClient(api_module.app).get(
        "/usage",
        headers={"Origin": "https://example.com"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_config_endpoint_does_not_include_cors_for_localhost_origin(api_module):
    response = TestClient(api_module.app).get(
        "/config",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_config_endpoint_preflight_does_not_allow_localhost_origin(api_module):
    response = TestClient(api_module.app).options(
        "/config",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers


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


def test_sessions_endpoint_selector_view_skips_count(api_module, monkeypatch):
    captured = {}
    count_called = False

    def fake_selector(**kwargs):
        captured.update(kwargs)
        return [
            {
                "session_id": "sess-1",
                "client_source": "codex",
                "request_count": 2,
                "started": "2026-05-09T10:00:00+00:00",
            }
        ]

    def fake_count(**kwargs):
        nonlocal count_called
        count_called = True
        return 999

    monkeypatch.setattr(api_module, "fetch_session_selector_rows", fake_selector)
    monkeypatch.setattr(api_module, "count_sessions", fake_count)

    response = TestClient(api_module.app).get(
        "/sessions",
        params={
            "view": "selector",
            "client_source": "codex",
            "since": "2026-05-01T00:00:00Z",
            "sort_by": "started",
            "sort_order": "desc",
            "limit": "50",
            "offset": "0",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "sessions": [
            {
                "session_id": "sess-1",
                "client_source": "codex",
                "request_count": 2,
                "started": "2026-05-09T10:00:00+00:00",
            }
        ],
        "total": None,
    }
    assert count_called is False
    assert captured["client_source"] == "codex"
    assert captured["since"] == "2026-05-01T00:00:00Z"
    assert captured["sort_by"] == "started"
    assert captured["sort_order"] == "desc"
    assert captured["limit"] == 50
    assert captured["offset"] == 0


def test_sessions_endpoint_rejects_unknown_view(api_module):
    response = TestClient(api_module.app).get("/sessions", params={"view": "compact"})

    assert response.status_code == 400
    assert "Invalid view" in response.json()["detail"]


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


# ---------------------------------------------------------------------------
# Slice 1: Session Evaluation API
# ---------------------------------------------------------------------------


def test_put_session_evaluation_creates_evaluation(api_module, monkeypatch):
    captured = {}

    def fake_upsert(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(api_module, "upsert_session_evaluation", fake_upsert)

    response = TestClient(api_module.app).put(
        "/sessions/sess-1/evaluation",
        json={
            "outcome": "solved",
            "source": "manual",
            "evidence": ["User marked solved"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert captured["session_id"] == "sess-1"
    assert captured["outcome"] == "solved"
    assert captured["source"] == "manual"
    assert captured["evidence"] == ["User marked solved"]


def test_put_session_evaluation_invalid_outcome_returns_400(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "upsert_session_evaluation", lambda **kw: None)

    response = TestClient(api_module.app).put(
        "/sessions/sess-1/evaluation",
        json={"outcome": "invalid_outcome"},
    )

    assert response.status_code == 400


def test_put_session_evaluation_invalid_source_returns_400(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "upsert_session_evaluation", lambda **kw: None)

    response = TestClient(api_module.app).put(
        "/sessions/sess-1/evaluation",
        json={"outcome": "solved", "source": "bogus_source"},
    )

    assert response.status_code == 400


def test_put_session_evaluation_rejects_llm_source(api_module, monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError("manual evaluation endpoint should not write LLM results")

    monkeypatch.setattr(api_module, "upsert_session_evaluation", fail_if_called)

    response = TestClient(api_module.app).put(
        "/sessions/sess-1/evaluation",
        json={
            "outcome": "solved",
            "source": "llm",
            "task_title": "Spoofed task title",
            "task_title_zh": "伪造任务标题",
            "evidence": ["caller supplied an LLM source"],
        },
    )

    assert response.status_code == 400
    assert "manual" in response.json()["detail"].lower()


def test_put_session_evaluation_returns_404_when_session_not_found(
    api_module, monkeypatch
):
    def raise_not_found(**kwargs):
        raise ValueError("Session not found: nonexistent")

    monkeypatch.setattr(api_module, "upsert_session_evaluation", raise_not_found)

    response = TestClient(api_module.app).put(
        "/sessions/nonexistent/evaluation",
        json={"outcome": "solved"},
    )

    assert response.status_code == 404


def test_get_session_evaluation_returns_evaluation(api_module, monkeypatch):
    fake_eval = {
        "session_id": "sess-1",
        "outcome": "solved",
        "source": "manual",
        "confidence": None,
        "task_title": "Fixed bug",
        "task_title_zh": "修复错误",
        "summary": None,
        "evidence": ["User marked solved"],
        "failure_reason": None,
        "evaluated_at": "2026-05-11T00:00:00+00:00",
    }
    monkeypatch.setattr(
        api_module, "get_session_evaluation", lambda sid, **kw: fake_eval
    )

    response = TestClient(api_module.app).get("/sessions/sess-1/evaluation")

    assert response.status_code == 200
    data = response.json()
    assert data["evaluation"]["outcome"] == "solved"
    assert data["evaluation"]["task_title"] == "Fixed bug"
    assert data["evaluation"]["task_title_zh"] == "修复错误"


def test_get_session_evaluation_returns_null_when_absent(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "get_session_evaluation", lambda sid, **kw: None)

    response = TestClient(api_module.app).get("/sessions/sess-1/evaluation")

    assert response.status_code == 200
    assert response.json()["evaluation"] is None


def test_delete_session_evaluation_removes_evaluation(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "delete_session_evaluation", lambda sid, **kw: True)

    response = TestClient(api_module.app).delete("/sessions/sess-1/evaluation")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"


def test_delete_session_evaluation_returns_404_when_absent(api_module, monkeypatch):
    monkeypatch.setattr(
        api_module, "delete_session_evaluation", lambda sid, **kw: False
    )

    response = TestClient(api_module.app).delete("/sessions/sess-1/evaluation")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Slice 4: Model Effectiveness API
# ---------------------------------------------------------------------------


def test_model_effectiveness_endpoint_passes_filters(api_module, monkeypatch):
    captured = {}

    def fake_aggregate(**kwargs):
        captured.update(kwargs)
        return {
            "groups": [
                {
                    "key": "gpt-5.5",
                    "session_count": 2,
                    "evaluated_count": 1,
                    "solved_count": 1,
                    "partial_count": 0,
                    "failed_count": 0,
                    "stuck_count": 0,
                    "unknown_count": 1,
                    "no_op_count": 0,
                    "solve_rate": 1.0,
                    "total_cost_usd": 0.5,
                    "cost_per_solved": 0.5,
                    "avg_duration_s": 120.0,
                }
            ]
        }

    monkeypatch.setattr(api_module, "aggregate_model_effectiveness", fake_aggregate)

    response = TestClient(api_module.app).get(
        "/model-effectiveness",
        params={
            "group_by": "model",
            "since": "2026-05-01T00:00:00Z",
            "until": "2026-05-11T23:59:59Z",
            "client_source": "codex",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["groups"][0]["key"] == "gpt-5.5"
    assert captured == {
        "group_by": "model",
        "since": "2026-05-01T00:00:00Z",
        "until": "2026-05-11T23:59:59Z",
        "client_source": "codex",
        "hide_noop": False,
    }


def test_model_effectiveness_endpoint_rejects_invalid_group_by(api_module, monkeypatch):
    monkeypatch.setattr(
        api_module, "aggregate_model_effectiveness", lambda **kwargs: {"groups": []}
    )

    response = TestClient(api_module.app).get(
        "/model-effectiveness",
        params={"group_by": "evaluation_source"},
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Slice 8: Daily Effectiveness Report API
# ---------------------------------------------------------------------------


def test_daily_effectiveness_endpoint_passes_date(api_module, monkeypatch):
    captured = {}

    def fake_report(**kwargs):
        captured.update(kwargs)
        return {
            "date": kwargs["date"],
            "summary": "You ran 2 AI sessions. 1 was evaluated. Total cost was $0.42.",
            "session_count": 2,
            "evaluated_count": 1,
            "classified_count": 1,
            "solved_count": 1,
            "partial_count": 0,
            "failed_count": 0,
            "stuck_count": 0,
            "no_op_count": 0,
            "unknown_count": 1,
            "total_cost_usd": 0.42,
            "highlights": ["codex / gpt-5.5 solved 1/1 evaluated sessions"],
            "needs_attention": [],
            "model_takeaways": ["codex / gpt-5.5 solved 1/1 evaluated sessions"],
            "groups": [],
        }

    monkeypatch.setattr(api_module, "daily_session_effectiveness_report", fake_report)

    response = TestClient(api_module.app).get(
        "/sessions/daily-effectiveness",
        params={"date": "2026-05-10"},
    )

    assert response.status_code == 200
    assert captured == {"date": "2026-05-10"}
    assert response.json()["date"] == "2026-05-10"


def test_daily_effectiveness_endpoint_rejects_invalid_date(api_module, monkeypatch):
    def fake_report(**kwargs):
        raise ValueError("Invalid date: not-a-date. Expected YYYY-MM-DD")

    monkeypatch.setattr(api_module, "daily_session_effectiveness_report", fake_report)

    response = TestClient(api_module.app).get(
        "/sessions/daily-effectiveness",
        params={"date": "not-a-date"},
    )

    assert response.status_code == 400
    assert "Invalid date" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Slice 7: Session Evaluation Jobs API
# ---------------------------------------------------------------------------


def test_evaluate_with_llm_queues_job(api_module, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        api_module,
        "require_available_evaluator_type",
        lambda evaluator_type: evaluator_type,
    )

    def fake_start(session_id, **kwargs):
        captured["session_id"] = session_id
        captured.update(kwargs)
        return {
            "job_id": "job-1",
            "kind": "session_evaluation",
            "session_id": session_id,
            "status": "queued",
            "trigger": "manual",
            "error": None,
        }

    monkeypatch.setattr(api_module, "start_session_evaluation_job", fake_start)

    response = TestClient(api_module.app).post("/sessions/sess-1/evaluate-with-llm")

    assert response.status_code == 202
    assert response.json() == {
        "job_id": "job-1",
        "kind": "session_evaluation",
        "session_id": "sess-1",
        "status": "queued",
        "trigger": "manual",
        "error": None,
    }
    assert captured["session_id"] == "sess-1"
    assert captured["trigger"] == "manual"
    assert captured["evaluator_type"] == "codex"


def test_evaluate_with_llm_accepts_evaluator_override(api_module, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        api_module,
        "require_available_evaluator_type",
        lambda evaluator_type: evaluator_type,
    )

    def fake_start(session_id, **kwargs):
        captured["session_id"] = session_id
        captured.update(kwargs)
        return {
            "job_id": "job-claude",
            "kind": "session_evaluation",
            "session_id": session_id,
            "status": "queued",
            "trigger": "manual",
            "evaluator_type": kwargs["evaluator_type"],
            "error": None,
        }

    monkeypatch.setattr(api_module, "start_session_evaluation_job", fake_start)

    response = TestClient(api_module.app).post(
        "/sessions/sess-1/evaluate-with-llm",
        json={"evaluator_type": "claude"},
    )

    assert response.status_code == 202
    assert response.json()["evaluator_type"] == "claude"
    assert captured["evaluator_type"] == "claude"


def test_evaluate_with_llm_rejects_unavailable_evaluator(api_module, monkeypatch):
    def reject(evaluator_type):
        raise ValueError(f"Evaluator not available: {evaluator_type}")

    monkeypatch.setattr(api_module, "require_available_evaluator_type", reject)

    response = TestClient(api_module.app).post(
        "/sessions/sess-1/evaluate-with-llm",
        json={"evaluator_type": "claude"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Evaluator not available: claude"


def test_evaluate_with_llm_returns_409_for_manual_evaluation(api_module, monkeypatch):
    def raise_manual(session_id, **kwargs):
        raise ValueError("Manual evaluation exists for session: sess-1")

    monkeypatch.setattr(api_module, "start_session_evaluation_job", raise_manual)
    monkeypatch.setattr(api_module, "require_available_evaluator_type", lambda t: t)

    response = TestClient(api_module.app).post("/sessions/sess-1/evaluate-with-llm")

    assert response.status_code == 409


def test_evaluate_with_llm_rejects_unsupported_source(api_module, monkeypatch):
    def raise_unsupported(session_id, **kwargs):
        raise ValueError("Unsupported session source: unknown")

    monkeypatch.setattr(api_module, "start_session_evaluation_job", raise_unsupported)
    monkeypatch.setattr(api_module, "require_available_evaluator_type", lambda t: t)

    response = TestClient(api_module.app).post(
        "/sessions/sess-unsupported/evaluate-with-llm"
    )

    assert response.status_code == 400


def test_poll_job_returns_progress_fields(api_module, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "get_evaluation_job_progress",
        lambda job_id: {
            "job_id": job_id,
            "kind": "session_evaluation",
            "session_id": "sess-1",
            "status": "queued",
            "trigger": "manual",
            "ahead_count": 1,
            "queue_position": 2,
            "error": None,
        },
    )

    response = TestClient(api_module.app).get("/poll/job-1")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-1",
        "kind": "session_evaluation",
        "session_id": "sess-1",
        "status": "queued",
        "trigger": "manual",
        "ahead_count": 1,
        "queue_position": 2,
        "error": None,
    }


def test_poll_job_returns_404_for_unknown_job(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "get_evaluation_job_progress", lambda job_id: None)

    response = TestClient(api_module.app).get("/poll/missing")

    assert response.status_code == 404


def test_active_evaluation_jobs_returns_visible_session_jobs(api_module, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "list_evaluator_agents",
        lambda: [
            {"id": "codex", "label": "Codex", "available": True},
            {"id": "claude", "label": "Claude Code", "available": False},
        ],
    )
    monkeypatch.setattr(
        api_module,
        "list_active_evaluation_jobs_with_progress",
        lambda session_ids=None: [
            {
                "job_id": "job-1",
                "session_id": "sess-1",
                "status": "running",
                "trigger": "auto",
                "ahead_count": 0,
                "queue_position": 1,
                "error": None,
            }
        ],
    )

    response = TestClient(api_module.app).get(
        "/evaluation-jobs/active",
        params={"session_ids": "sess-1,sess-2"},
    )

    assert response.status_code == 200
    assert response.json()["jobs"]["sess-1"]["status"] == "running"
    assert response.json()["evaluators"][1]["label"] == "Claude Code"


def test_session_evaluation_jobs_returns_history_and_evaluator_catalog(
    api_module, monkeypatch
):
    monkeypatch.setattr(
        api_module,
        "list_session_evaluation_jobs_with_progress",
        lambda session_id: [
            {
                "job_id": "job-failed",
                "kind": "session_evaluation",
                "session_id": session_id,
                "status": "failed",
                "trigger": "manual",
                "evaluator_type": "codex",
                "ahead_count": 0,
                "queue_position": None,
                "error": "Evaluator exited with code 1",
            }
        ],
    )
    monkeypatch.setattr(
        api_module,
        "list_evaluator_agents",
        lambda: [
            {"id": "codex", "label": "Codex", "available": True},
            {"id": "claude", "label": "Claude Code", "available": True},
        ],
    )

    response = TestClient(api_module.app).get("/sessions/sess-1/evaluation-jobs")

    assert response.status_code == 200
    assert response.json()["jobs"][0]["status"] == "failed"
    assert response.json()["jobs"][0]["evaluator_type"] == "codex"
    assert response.json()["evaluators"][1]["id"] == "claude"
    assert response.json()["global_evaluator_type"] == "codex"


def test_patch_evaluation_job_updates_queued_evaluator(api_module, monkeypatch):
    stored = {"evaluator_type": "codex"}

    monkeypatch.setattr(
        api_module,
        "require_available_evaluator_type",
        lambda evaluator_type: evaluator_type,
    )
    monkeypatch.setattr(
        api_module,
        "get_evaluation_job_progress",
        lambda job_id: {
            "job_id": job_id,
            "session_id": "sess-1",
            "status": "queued",
            "evaluator_type": stored["evaluator_type"],
            "ahead_count": 1,
            "queue_position": 2,
            "error": None,
        },
    )

    def fake_update(job_id, *, evaluator_type):
        stored["evaluator_type"] = evaluator_type
        return {
            "job_id": job_id,
            "session_id": "sess-1",
            "status": "queued",
            "evaluator_type": evaluator_type,
            "ahead_count": 1,
            "queue_position": 2,
            "error": None,
        }

    monkeypatch.setattr(
        api_module,
        "update_queued_evaluation_job_evaluator",
        fake_update,
    )

    response = TestClient(api_module.app).patch(
        "/evaluation-jobs/job-1",
        json={"evaluator_type": "claude"},
    )

    assert response.status_code == 200
    assert response.json()["evaluator_type"] == "claude"


def test_patch_evaluation_job_rejects_running_evaluator_change(api_module, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "require_available_evaluator_type",
        lambda evaluator_type: evaluator_type,
    )
    monkeypatch.setattr(
        api_module,
        "get_evaluation_job_progress",
        lambda job_id: {
            "job_id": job_id,
            "session_id": "sess-1",
            "status": "running",
            "evaluator_type": "codex",
            "ahead_count": 0,
            "queue_position": 1,
            "error": None,
        },
    )

    response = TestClient(api_module.app).patch(
        "/evaluation-jobs/job-1",
        json={"evaluator_type": "claude"},
    )

    assert response.status_code == 409


def test_patch_evaluation_job_returns_409_for_running_before_evaluator_validation(
    api_module, monkeypatch
):
    monkeypatch.setattr(
        api_module,
        "get_evaluation_job_progress",
        lambda job_id: {
            "job_id": job_id,
            "session_id": "sess-1",
            "status": "running",
            "evaluator_type": "codex",
            "ahead_count": 0,
            "queue_position": 1,
            "error": None,
        },
    )

    def reject(evaluator_type):
        raise ValueError(f"Evaluator not available: {evaluator_type}")

    monkeypatch.setattr(api_module, "require_available_evaluator_type", reject)

    response = TestClient(api_module.app).patch(
        "/evaluation-jobs/job-1",
        json={"evaluator_type": "claude"},
    )

    assert response.status_code == 409


def test_patch_evaluation_job_returns_404_for_missing_before_evaluator_validation(
    api_module, monkeypatch
):
    monkeypatch.setattr(api_module, "get_evaluation_job_progress", lambda job_id: None)

    def reject(evaluator_type):
        raise ValueError(f"Unsupported evaluator agent: {evaluator_type}")

    monkeypatch.setattr(api_module, "require_available_evaluator_type", reject)

    response = TestClient(api_module.app).patch(
        "/evaluation-jobs/missing",
        json={"evaluator_type": "invalid"},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Slice 9: PATCH /config/evaluation endpoint
# ---------------------------------------------------------------------------


def test_update_evaluation_config(api_module, monkeypatch):
    from unittest.mock import MagicMock

    mock_set = MagicMock()
    monkeypatch.setattr("src.api.set_evaluation_evaluator", mock_set)

    response = TestClient(api_module.app).patch(
        "/config/evaluation",
        json={"evaluator": "claude"},
    )

    assert response.status_code == 200
    assert response.json()["global_evaluator_type"] == "claude"
    mock_set.assert_called_once_with("claude")


def test_update_evaluation_config_returns_500_on_set_evaluator_error(
    api_module, monkeypatch
):
    def raise_error(evaluator):
        raise RuntimeError("Failed to persist evaluator config")

    monkeypatch.setattr("src.api.set_evaluation_evaluator", raise_error)

    response = TestClient(api_module.app).patch(
        "/config/evaluation",
        json={"evaluator": "claude"},
    )

    assert response.status_code == 500
    assert "Failed to persist evaluator config" in response.json()["detail"]


def test_update_evaluation_config_rejects_invalid_evaluator(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "set_evaluation_evaluator", lambda **kw: None)

    response = TestClient(api_module.app).patch(
        "/config/evaluation",
        json={"evaluator": "invalid-evaluator"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# SPA catch-all routing
# ---------------------------------------------------------------------------


def test_spa_deep_links_serve_index_html(api_module):
    """GET /dashboard, /logs, /settings return 200 with HTML, not 404."""
    from pathlib import Path

    frontend_dist = (
        Path(api_module.__file__).resolve().parent.parent / "frontend" / "dist"
    )
    if not (frontend_dist / "index.html").is_file():
        import pytest

        pytest.skip("frontend/dist/index.html not built")

    client = TestClient(api_module.app)

    for path in ("/dashboard", "/logs", "/settings"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert "text/html" in response.headers.get("content-type", "")


def test_spa_deep_links_do_not_hijack_api_routes(api_module, monkeypatch):
    """SPA middleware must not rewrite API routes to index.html."""
    monkeypatch.setattr(api_module, "fetch_recent_usage", lambda **kwargs: [])

    client = TestClient(api_module.app)
    response = client.get("/usage", params={"limit": "0"})

    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")
