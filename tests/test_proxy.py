import pytest
from decimal import Decimal


def test_proxy_registers_v1_and_compatibility_paths(proxy_module):
    post_paths = {
        route.path
        for route in proxy_module.app.routes
        if "POST" in getattr(route, "methods", set())
    }

    assert {
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/responses",
        "/responses",
        "/v1/messages",
        "/messages",
    }.issubset(post_paths)

    get_paths = {
        route.path
        for route in proxy_module.app.routes
        if "GET" in getattr(route, "methods", set())
    }

    assert {
        "/api/v1/models",
        "/v1/models",
        "/models",
        "/v1/models/{model_id}",
        "/models/{model_id}",
        "/v1/props",
        "/props",
        "/version",
    }.issubset(get_paths)


@pytest.mark.parametrize(
    ("base_url", "path", "expected"),
    [
        (
            "https://api.example.com/v1/",
            "/v1/chat/completions",
            "https://api.example.com/v1/chat/completions",
        ),
        (
            "https://api.example.com/openai",
            "v1/responses",
            "https://api.example.com/openai/responses",
        ),
        (
            "https://api.example.com",
            "/messages",
            "https://api.example.com/messages",
        ),
    ],
)
def test_build_upstream_url_normalizes_base_and_v1_prefix(
    proxy_module,
    base_url,
    path,
    expected,
):
    url = proxy_module.build_upstream_url(
        base_url,
        path,
    )

    assert url == expected


def test_build_forward_headers_filters_hop_by_hop_fields(proxy_module):
    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [
                (b"host", b"localhost:4000"),
                (b"authorization", b"Bearer caller-token"),
                (b"content-length", b"123"),
                (b"x-request-id", b"abc123"),
                (b"accept", b"application/json"),
            ],
        }
    )

    headers = proxy_module.build_forward_headers(request)

    assert headers["authorization"] == "Bearer caller-token"
    assert headers["x-request-id"] == "abc123"
    assert headers["accept"] == "application/json"
    assert "host" not in headers
    assert "content-length" not in headers


def test_parse_json_body_returns_empty_dict_for_empty_body(proxy_module):
    assert proxy_module.parse_json_body(b"") == {}


def test_parse_json_body_decodes_json_body(proxy_module):
    assert proxy_module.parse_json_body(b'{"model":"test-model","stream":true}') == {
        "model": "test-model",
        "stream": True,
    }


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (
            "opencode/1.14.24 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.13",
            "opencode",
        ),
        ("my-wrapper/1.0 anthropic-sdk/0.1", "my-wrapper"),
        (
            "codex-tui/0.124.0 (Mac OS 15.5.0; arm64) Superset/1.0.0 (codex-tui; 0.124.0)",
            "codex",
        ),
        ("curl/8.7.1", "curl"),
        ("plain-token-without-version", None),
        ("", None),
    ],
)
def test_parse_client_source_uses_leading_product_token(
    proxy_module, user_agent, expected
):
    assert proxy_module.parse_client_source(user_agent) == expected


def test_record_proxy_user_agent_writes_client_source(
    proxy_module, tmp_path, monkeypatch
):
    monkeypatch.setattr(proxy_module, "PROXY_USER_AGENT_DIR", str(tmp_path))
    proxy_module.RECORDED_PROXY_USER_AGENTS.clear()

    proxy_module.record_proxy_user_agent(
        "/v1/chat/completions",
        "opencode/1.14.24 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.13",
    )

    log_path = tmp_path / "requests.log"
    assert log_path.read_text(encoding="utf-8") == (
        "path=/v1/chat/completions client_source=opencode "
        "user_agent=opencode/1.14.24 ai-sdk/provider-utils/4.0.23 "
        "runtime/bun/1.3.13\n"
    )


def test_record_proxy_user_agent_ignores_filesystem_errors(proxy_module, monkeypatch):
    proxy_module.RECORDED_PROXY_USER_AGENTS.clear()

    def fail_makedirs(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(proxy_module.os, "makedirs", fail_makedirs)

    proxy_module.record_proxy_user_agent(
        "/v1/chat/completions",
        "opencode/1.14.24 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.13",
    )


@pytest.mark.anyio
async def test_forward_persists_parsed_client_source(proxy_module, monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, content):
            captured["url"] = url
            return FakeResponse()

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"model":"test-model","stream":false}',
            "more_body": False,
        }

    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        proxy_module, "resolve_provider_base_url_id", lambda provider: 7
    )
    monkeypatch.setattr(
        proxy_module,
        "log_usage",
        lambda usage, db_path=None: captured.update(
            {"db_path": db_path, "usage": usage}
        ),
    )
    monkeypatch.setattr(proxy_module, "record_proxy_user_agent", lambda path, ua: None)

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/responses",
            "headers": [
                (b"content-type", b"application/json"),
                (
                    b"user-agent",
                    b"opencode/1.14.24 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.13",
                ),
            ],
        },
        receive,
    )

    response = await proxy_module.forward(request, "/v1/responses")

    assert response.status_code == 200
    assert captured["usage"].client_source == "opencode"


def test_resolve_provider_supports_configured_model_matches(proxy_module):
    provider, upstream_model = proxy_module.resolve_provider("test-model")

    assert provider.name == "test-provider"
    assert upstream_model == "test-model"


def test_resolve_provider_supports_prefix_matches(proxy_module):
    provider, upstream_model = proxy_module.resolve_provider(
        "test-provider/gpt-4.1-mini"
    )
    assert provider.name == "test-provider"
    assert upstream_model == "gpt-4.1-mini"


def test_resolve_provider_supports_dot_prefix_matches(proxy_module):
    provider, upstream_model = proxy_module.resolve_provider(
        "test-provider.gpt-4.1-mini"
    )

    assert provider.name == "test-provider"
    assert upstream_model == "gpt-4.1-mini"


def test_resolve_provider_rejects_unknown_model(proxy_module):
    with pytest.raises(proxy_module.HTTPException) as exc_info:
        proxy_module.resolve_provider("missing-model")

    assert exc_info.value.status_code == 404
    assert "missing-model" in exc_info.value.detail


@pytest.mark.anyio
async def test_list_models_returns_configured_models(proxy_module):
    result = await proxy_module.list_models()

    assert result == {
        "object": "list",
        "data": [
            {"id": "test-model", "object": "model", "owned_by": "test-provider"},
            {"id": "gpt-4.1", "object": "model", "owned_by": "test-provider"},
        ],
    }


def test_proxy_metadata_describes_supported_endpoints(proxy_module):
    result = proxy_module.proxy_metadata()

    assert result["name"] == "llm-tracker-proxy"
    assert "/api/v1/models" in result["supported_endpoints"]
    assert "/v1/props" in result["supported_endpoints"]
    assert "/version" not in result["supported_endpoints"]


@pytest.mark.anyio
async def test_get_model_returns_configured_model(proxy_module):
    result = await proxy_module.get_model("test-model")

    assert result == {
        "id": "test-model",
        "object": "model",
        "owned_by": "test-provider",
    }


@pytest.mark.anyio
async def test_get_model_rejects_unknown_model(proxy_module):
    with pytest.raises(proxy_module.HTTPException) as exc_info:
        await proxy_module.get_model("missing-model")

    assert exc_info.value.status_code == 404
    assert "missing-model" in exc_info.value.detail


@pytest.mark.anyio
async def test_props_returns_proxy_metadata(proxy_module):
    result = await proxy_module.props()

    assert result == proxy_module.proxy_metadata()


@pytest.mark.anyio
async def test_version_returns_proxy_identity(proxy_module):
    result = await proxy_module.version()

    assert result == {
        "name": "llm-tracker-proxy",
        "version": "dev",
    }


@pytest.mark.anyio
async def test_forward_logs_base_url_id_from_provider_config(proxy_module, monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, content):
            captured["url"] = url
            return FakeResponse()

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"model":"test-model","stream":false}',
            "more_body": False,
        }

    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        proxy_module, "resolve_provider_base_url_id", lambda provider: 7
    )
    monkeypatch.setattr(
        proxy_module,
        "log_usage",
        lambda usage, db_path=None: captured.update(
            {"db_path": db_path, "usage": usage}
        ),
    )

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/responses",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )

    response = await proxy_module.forward(request, "/v1/responses")

    assert response.status_code == 200
    assert captured["url"] == "https://api.example.com/v1/responses"
    assert captured["usage"].base_url_id == 7
    assert captured["usage"].provider == "test-provider"
    assert captured["usage"].input_cost_usd == Decimal("0.00002")
    assert captured["usage"].output_cost_usd == Decimal("0.00003")
    assert captured["usage"].total_cost_usd == Decimal("0.00005")
    assert captured["usage"].status == 200
    assert captured["usage"].ttft_ms is None


@pytest.mark.anyio
async def test_streaming_forward_logs_first_chunk_latency(proxy_module, monkeypatch):
    captured = {}

    class FakeStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_bytes(self):
            yield b'data: {"type":"response.output_text.delta"}\n\n'
            yield (
                b'data: {"response":{"usage":{"input_tokens":10,"output_tokens":5}}}\n\n'
            )

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, headers, content):
            captured["method"] = method
            captured["url"] = url
            return FakeStreamResponse()

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"model":"test-model","stream":true}',
            "more_body": False,
        }

    # The streaming response path can consult monotonic time more than once
    # while the iterator and cleanup finish, so keep returning the last value.
    class FakeMonotonic:
        def __init__(self):
            self.values = [100.0, 100.025, 100.090]
            self.last = self.values[-1]

        def __call__(self):
            if self.values:
                self.last = self.values.pop(0)
            return self.last

    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(proxy_module.time, "monotonic", FakeMonotonic())
    monkeypatch.setattr(
        proxy_module, "resolve_provider_base_url_id", lambda provider: 7
    )
    monkeypatch.setattr(
        proxy_module,
        "log_usage",
        lambda usage, db_path=None: captured.update(
            {"db_path": db_path, "usage": usage}
        ),
    )

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/responses",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )

    response = await proxy_module.forward(request, "/v1/responses")
    chunks = [chunk async for chunk in response.body_iterator]

    assert response.status_code == 200
    assert b"".join(chunks).startswith(b'data: {"type":"response.output_text.delta"}')
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.example.com/v1/responses"
    assert captured["usage"].ttft_ms == 25
    assert captured["usage"].latency_ms == 90
    assert captured["usage"].prompt_tokens == 10
    assert captured["usage"].completion_tokens == 5
