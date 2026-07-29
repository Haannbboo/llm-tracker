import json

import pytest
from fastapi.testclient import TestClient

from config.models import ProviderConfig


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
        "/v1/models/{model_id:path}",
        "/models/{model_id:path}",
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

    assert headers["x-request-id"] == "abc123"
    assert headers["accept"] == "application/json"
    assert "host" not in headers
    assert "content-length" not in headers
    assert "authorization" not in headers


def test_build_forward_headers_injects_provider_api_key(proxy_module):
    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [
                (b"host", b"localhost:4000"),
                (b"authorization", b"Bearer caller-token"),
                (b"x-request-id", b"abc123"),
            ],
        }
    )
    provider = proxy_module.ProviderConfig(
        name="test", base_url="https://api.test/v1", api_key="sk-test-key"
    )

    headers = proxy_module.build_forward_headers(request, provider)

    assert headers["authorization"] == "Bearer sk-test-key"
    assert headers["x-request-id"] == "abc123"


def test_build_forward_headers_passes_through_without_provider_key(proxy_module):
    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [
                (b"authorization", b"Bearer caller-token"),
                (b"x-request-id", b"abc123"),
            ],
        }
    )
    provider = proxy_module.ProviderConfig(name="test", base_url="https://api.test/v1")

    headers = proxy_module.build_forward_headers(request, provider)

    assert "authorization" not in headers
    assert headers["x-request-id"] == "abc123"


def test_parse_json_body_returns_empty_dict_for_empty_body(proxy_module):
    assert proxy_module.parse_json_body(b"") == {}


def test_parse_json_body_decodes_json_body(proxy_module):
    assert proxy_module.parse_json_body(b'{"model":"test-model","stream":true}') == {
        "model": "test-model",
        "stream": True,
    }


class TestComputePromptLength:
    def test_empty_body(self, proxy_module):
        assert proxy_module.compute_prompt_length({}) == 0

    def test_empty_messages(self, proxy_module):
        assert proxy_module.compute_prompt_length({"messages": []}) == 0

    def test_single_user_message(self, proxy_module):
        body = {"messages": [{"role": "user", "content": "Hello world"}]}
        assert proxy_module.compute_prompt_length(body) == 11

    def test_only_counts_user_after_last_assistant(self, proxy_module):
        body = {
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello! How can I help?"},
                {"role": "user", "content": "Bye"},
            ]
        }
        # "Hi" is before the last assistant, only "Bye" counts
        assert proxy_module.compute_prompt_length(body) == 3

    def test_tool_call_continuation_returns_zero(self, proxy_module):
        """Tool-call turns replay history with no new user input."""
        body = {
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "What is the weather?"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "tc_1"}]},
                {"role": "tool", "content": '{"temp":72}'},
            ]
        }
        assert proxy_module.compute_prompt_length(body) == 0

    def test_multiple_tool_rounds(self, proxy_module):
        """Each tool-call continuation reports 0; new user turn reports its length."""
        body = {
            "messages": [
                {"role": "user", "content": "Book a flight"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "tc_1"}]},
                {"role": "tool", "content": '{"found":true}'},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "tc_2"}]},
                {"role": "tool", "content": '{"booked":true}'},
                {"role": "assistant", "content": "Done!"},
                {"role": "user", "content": "Thanks!"},
            ]
        }
        # Only "Thanks!" after last assistant
        assert proxy_module.compute_prompt_length(body) == 7

    def test_multimodal_content(self, proxy_module):
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this"},
                        {"type": "image_url", "image_url": {"url": "data:..."}},
                    ],
                }
            ]
        }
        assert proxy_module.compute_prompt_length(body) == len("Describe this")

    def test_none_content(self, proxy_module):
        body = {"messages": [{"role": "user", "content": None}]}
        assert proxy_module.compute_prompt_length(body) == 0

    def test_no_user_messages(self, proxy_module):
        body = {
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "assistant", "content": "Hello!"},
            ]
        }
        assert proxy_module.compute_prompt_length(body) == 0

    def test_responses_api_input(self, proxy_module):
        body = {"input": [{"role": "user", "content": "test prompt"}]}
        assert proxy_module.compute_prompt_length(body) == len("test prompt")

    def test_messages_takes_precedence_over_input(self, proxy_module):
        body = {
            "messages": [{"role": "user", "content": "msg"}],
            "input": [{"role": "user", "content": "input"}],
        }
        assert proxy_module.compute_prompt_length(body) == 3


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
        proxy_module, "record_usage", lambda **fields: captured.update(fields)
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
    assert captured["client_source"] == "opencode"


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

    assert result["name"] == "llm-tracker-proxy"
    parts = result["version"].split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), (
        f"Expected x.y.z format, got {result['version']!r}"
    )


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
        proxy_module, "record_usage", lambda **fields: captured.update(fields)
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
    assert captured["base_url"] == "https://api.example.com/v1"
    assert captured["base_url_provider"] == "test-provider"
    assert captured["base_url_source"] == "proxy_config"
    assert captured["provider"] == "test-provider"
    assert captured["status"] == 200
    assert captured["ttft_ms"] is None


@pytest.mark.anyio
async def test_forward_computes_prompt_length_non_streaming(proxy_module, monkeypatch):
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
            return FakeResponse()

    body = json.dumps(
        {
            "model": "test-model",
            "stream": False,
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello world"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "Bye"},
            ],
        }
    ).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        proxy_module, "record_usage", lambda **fields: captured.update(fields)
    )
    monkeypatch.setattr(proxy_module, "record_proxy_user_agent", lambda path, ua: None)

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )

    await proxy_module.forward(request, "/v1/chat/completions")

    # Only "Bye" after last assistant; "Hello world" is before it
    assert captured["prompt_length"] == 3


@pytest.mark.anyio
async def test_streaming_forward_logs_first_chunk_latency(proxy_module, monkeypatch):
    captured = {}

    class FakeStreamResponse:
        def __init__(self, status_code=200):
            self.status_code = status_code

        async def aiter_bytes(self):
            yield b'data: {"type":"response.output_text.delta"}\n\n'
            yield (
                b'data: {"response":{"usage":{"input_tokens":10,"output_tokens":5}}}\n\n'
            )

        async def aread(self):
            return b""

    class FakeRequest:
        def __init__(self, method, url, headers, content):
            self.method = method
            self.url = url
            self.headers = headers
            self.content = content

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def build_request(self, method, url, headers=None, content=None):
            return FakeRequest(method, url, headers, content)

        async def send(self, request, stream=False):
            captured["method"] = request.method
            captured["url"] = request.url
            return FakeStreamResponse()

        async def aclose(self):
            pass

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
        proxy_module, "record_usage", lambda **fields: captured.update(fields)
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
    assert captured["ttft_ms"] == 25
    assert captured["latency_ms"] == 90
    assert captured["prompt_tokens"] == 10
    assert captured["completion_tokens"] == 5


@pytest.mark.anyio
async def test_forward_computes_prompt_length_streaming(proxy_module, monkeypatch):
    captured = {}

    class FakeStreamResponse:
        def __init__(self, status_code=200):
            self.status_code = status_code

        async def aiter_bytes(self):
            yield b'data: {"type":"response.output_text.delta"}\n\n'
            yield (
                b'data: {"response":{"usage":{"input_tokens":10,"output_tokens":5}}}\n\n'
            )

        async def aread(self):
            return b""

    class FakeRequest:
        def __init__(self, method, url, headers, content):
            self.method = method
            self.url = url
            self.headers = headers
            self.content = content

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def build_request(self, method, url, headers=None, content=None):
            return FakeRequest(method, url, headers, content)

        async def send(self, request, stream=False):
            return FakeStreamResponse()

        async def aclose(self):
            pass

    body = json.dumps(
        {
            "model": "test-model",
            "stream": True,
            "messages": [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "Hello"},
            ],
        }
    ).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

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
        proxy_module, "record_usage", lambda **fields: captured.update(fields)
    )

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )

    response = await proxy_module.forward(request, "/v1/chat/completions")
    _ = [chunk async for chunk in response.body_iterator]

    assert response.status_code == 200
    # Only "Hello" (5 chars), system message excluded
    assert captured["prompt_length"] == 5


@pytest.mark.anyio
async def test_streaming_forward_returns_upstream_error(proxy_module, monkeypatch):
    """Verify that non-2xx upstream responses return a JSONResponse with the correct status and body."""
    captured = {}

    class FakeErrorStreamResponse:
        status_code = 401

        async def aiter_bytes(self):
            yield b'{"error":{"message":"Missing Authentication header","code":401}}'

        async def aread(self):
            return b'{"error":{"message":"Missing Authentication header","code":401}}'

    class FakeRequest:
        def __init__(self, method, url, headers, content):
            self.method = method
            self.url = url
            self.headers = headers
            self.content = content

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def build_request(self, method, url, headers=None, content=None):
            return FakeRequest(method, url, headers, content)

        async def send(self, request, stream=False):
            captured["method"] = request.method
            captured["url"] = request.url
            return FakeErrorStreamResponse()

        async def aclose(self):
            pass

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"model":"test-model","stream":true}',
            "more_body": False,
        }

    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(proxy_module, "record_proxy_user_agent", lambda path, ua: None)

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )

    response = await proxy_module.forward(request, "/v1/chat/completions")

    assert response.status_code == 401
    assert (
        response.body
        == b'{"error":{"message":"Missing Authentication header","code":401}}'
    )


@pytest.mark.anyio
async def test_streaming_forward_closes_client_on_send_error(proxy_module, monkeypatch):
    """Verify that client.aclose() is called when client.send() raises."""
    closed = False

    class FakeRequest:
        def __init__(self, method, url, headers, content):
            self.method = method
            self.url = url
            self.headers = headers
            self.content = content

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def build_request(self, method, url, headers=None, content=None):
            return FakeRequest(method, url, headers, content)

        async def send(self, request, stream=False):
            raise RuntimeError("connection refused")

        async def aclose(self):
            nonlocal closed
            closed = True

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"model":"test-model","stream":true}',
            "more_body": False,
        }

    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(proxy_module, "record_proxy_user_agent", lambda path, ua: None)

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )

    with pytest.raises(RuntimeError, match="connection refused"):
        await proxy_module.forward(request, "/v1/chat/completions")

    assert closed, "client.aclose() was not called on send error"


@pytest.mark.anyio
async def test_streaming_forward_closes_client_on_aread_error(
    proxy_module, monkeypatch
):
    """Verify that client.aclose() is called when upstream.aread() raises on error status."""
    closed = False

    class FakeErrorStreamResponse:
        status_code = 502

        async def aiter_bytes(self):
            yield b""

        async def aread(self):
            raise RuntimeError("upstream read failed")

    class FakeRequest:
        def __init__(self, method, url, headers, content):
            self.method = method
            self.url = url
            self.headers = headers
            self.content = content

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def build_request(self, method, url, headers=None, content=None):
            return FakeRequest(method, url, headers, content)

        async def send(self, request, stream=False):
            return FakeErrorStreamResponse()

        async def aclose(self):
            nonlocal closed
            closed = True

    async def receive():
        return {
            "type": "http.request",
            "body": b'{"model":"test-model","stream":true}',
            "more_body": False,
        }

    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(proxy_module, "record_proxy_user_agent", lambda path, ua: None)

    request = proxy_module.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )

    with pytest.raises(RuntimeError, match="upstream read failed"):
        await proxy_module.forward(request, "/v1/chat/completions")

    assert closed, "client.aclose() was not called on aread error"


def test_resolve_provider_prioritizes_exact_matches(proxy_module, monkeypatch):
    """Verify that MODEL_MAP (explicit config) takes precedence over heuristic stripping."""
    # Setup mock config with a collision
    test_provider = ProviderConfig(
        name="openrouter", base_url="https://openrouter.ai/api/v1"
    )
    monkeypatch.setattr(proxy_module, "PROVIDER_MAP", {"openrouter": test_provider})
    monkeypatch.setattr(
        proxy_module, "MODEL_MAP", {"openrouter/owl-alpha": test_provider}
    )

    # Verify prioritization
    provider, upstream_model = proxy_module.resolve_provider("openrouter/owl-alpha")
    assert provider.name == "openrouter"
    assert upstream_model == "openrouter/owl-alpha"  # Should NOT be stripped


def test_get_model_supports_slashes_in_id(proxy_module, monkeypatch):
    """Verify that model info endpoint correctly captures IDs with slashes using path converter."""
    test_provider = ProviderConfig(
        name="openrouter", base_url="https://openrouter.ai/api/v1"
    )
    monkeypatch.setattr(
        proxy_module, "MODEL_MAP", {"openrouter/owl-alpha": test_provider}
    )

    client = TestClient(proxy_module.app)
    response = client.get("/v1/models/openrouter/owl-alpha")

    assert response.status_code == 200
    assert response.json()["id"] == "openrouter/owl-alpha"


def test_resolve_provider_falls_back_to_stripping(proxy_module, monkeypatch):
    """Verify that heuristic prefix stripping still works for unmapped models."""
    test_provider = ProviderConfig(name="openai", base_url="https://api.openai.com/v1")
    monkeypatch.setattr(proxy_module, "PROVIDER_MAP", {"openai": test_provider})
    monkeypatch.setattr(proxy_module, "MODEL_MAP", {})  # No explicit match

    # Verify fallback
    provider, upstream_model = proxy_module.resolve_provider("openai/gpt-4o")
    assert provider.name == "openai"
    assert upstream_model == "gpt-4o"  # Should be stripped


class TestExtractToolCalls:
    def test_chat_completions_tool_calls(self, proxy_module):
        result = proxy_module.extract_tool_calls(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"id": "call_abc", "function": {"name": "get_weather"}},
                                {"id": "call_def", "function": {"name": "search"}},
                            ]
                        }
                    }
                ]
            }
        )
        assert result == [
            {"tool_use_id": "call_abc", "tool_name": "get_weather"},
            {"tool_use_id": "call_def", "tool_name": "search"},
        ]

    def test_anthropic_messages_tool_use(self, proxy_module):
        result = proxy_module.extract_tool_calls(
            {
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_use", "id": "toolu_123", "name": "calculator"},
                ]
            }
        )
        assert result == [{"tool_use_id": "toolu_123", "tool_name": "calculator"}]

    def test_responses_api_function_call(self, proxy_module):
        result = proxy_module.extract_tool_calls(
            {
                "output": [
                    {"type": "message", "content": [{"type": "text", "text": "ok"}]},
                    {
                        "type": "function_call",
                        "call_id": "call_xyz",
                        "name": "file_read",
                    },
                ]
            }
        )
        assert result == [{"tool_use_id": "call_xyz", "tool_name": "file_read"}]

    def test_no_tool_calls_returns_empty(self, proxy_module):
        assert proxy_module.extract_tool_calls({}) == []
        assert (
            proxy_module.extract_tool_calls(
                {"choices": [{"message": {"content": "hi"}}]}
            )
            == []
        )


class TestStreamToolCallAccumulator:
    def test_openai_delta_accumulation(self, proxy_module):
        acc = proxy_module.StreamToolCallAccumulator()
        acc.accumulate(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {"name": "get_wea"},
                                }
                            ]
                        }
                    }
                ]
            }
        )
        acc.accumulate(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [{"index": 0, "function": {"name": "ther"}}]
                        }
                    }
                ]
            }
        )
        acc.accumulate(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 1,
                                    "id": "call_2",
                                    "function": {"name": "search"},
                                }
                            ]
                        }
                    }
                ]
            }
        )
        result = acc.get_tool_calls()
        assert len(result) == 2
        assert result[0] == {"tool_use_id": "call_1", "tool_name": "get_weather"}
        assert result[1] == {"tool_use_id": "call_2", "tool_name": "search"}

    def test_anthropic_content_block_start(self, proxy_module):
        acc = proxy_module.StreamToolCallAccumulator()
        acc.accumulate(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_abc",
                    "name": "bash",
                },
            }
        )
        assert acc.get_tool_calls() == [
            {"tool_use_id": "toolu_abc", "tool_name": "bash"}
        ]

    def test_empty_and_unrelated_payloads(self, proxy_module):
        acc = proxy_module.StreamToolCallAccumulator()
        acc.accumulate({"choices": [{"delta": {"content": "hello"}}]})
        acc.accumulate({"usage": {"prompt_tokens": 10}})
        assert acc.get_tool_calls() == []
