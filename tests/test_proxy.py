import pytest
from decimal import Decimal


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
