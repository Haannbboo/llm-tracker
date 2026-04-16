from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


CONFIG_TEMPLATE = """
server:
  host: 127.0.0.1
  port: 4000
db:
  path: {db_path}
providers:
  test-provider:
    base_url: https://api.example.com/v1
    api_key: test-key
    models:
      - test-model
      - gpt-4.1
"""


@pytest.fixture
def proxy_module(tmp_path: Path):
    config_dir = tmp_path / ".llm-tracker"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        CONFIG_TEMPLATE.format(db_path=tmp_path / "usage.db"),
        encoding="utf-8",
    )

    previous_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    sys.modules.pop("src.proxy", None)

    try:
        module = importlib.import_module("src.proxy")
        yield module
    finally:
        sys.modules.pop("src.proxy", None)
        if previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous_home


def test_build_model_map_returns_provider_configs(proxy_module):
    model_map = proxy_module.build_model_map(
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

    assert model_map["alpha-1"] == proxy_module.ProviderConfig(
        name="alpha",
        base_url="https://alpha.example/v1",
        api_key="alpha-key",
    )
    assert model_map["beta-1"].name == "beta"


def test_extract_usage_supports_responses_format_and_details(proxy_module):
    usage = proxy_module.extract_usage(
        {
            "input_tokens": 11,
            "output_tokens": 7,
            "input_tokens_details": {"cached_tokens": 3},
            "output_tokens_details": {"reasoning_tokens": 5},
        }
    )

    assert usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "reasoning_tokens": 5,
        "cached_tokens": 3,
        "total_tokens": 18,
    }


def test_extract_stream_usage_reads_nested_response_payload(proxy_module):
    usage = proxy_module.extract_stream_usage(
        {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 9,
                    "output_tokens": 4,
                    "output_tokens_details": {"reasoning_tokens": 2},
                }
            },
        }
    )

    assert usage == {
        "prompt_tokens": 9,
        "completion_tokens": 4,
        "reasoning_tokens": 2,
        "cached_tokens": 0,
        "total_tokens": 13,
    }


def test_build_upstream_url_strips_duplicate_v1_prefix(proxy_module):
    url = proxy_module.build_upstream_url(
        "https://api.example.com/v1/",
        "/v1/chat/completions",
    )

    assert url == "https://api.example.com/v1/chat/completions"


def test_build_forward_headers_replaces_auth_and_filters_hop_by_hop_fields(proxy_module):
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

    headers = proxy_module.build_forward_headers(
        request,
        proxy_module.ProviderConfig(
            name="alpha",
            base_url="https://api.example.com/v1",
            api_key="provider-key",
        ),
    )

    assert headers["Authorization"] == "Bearer provider-key"
    assert headers["Content-Type"] == "application/json"
    assert headers["x-request-id"] == "abc123"
    assert headers["accept"] == "application/json"
    assert "host" not in headers
    assert "content-length" not in headers


def test_resolve_provider_supports_prefix_matches(proxy_module):
    provider = proxy_module.resolve_provider("gpt-4.1-mini")
    assert provider.name == "test-provider"


def test_build_usage_record_includes_provider_metadata(proxy_module):
    record = proxy_module.build_usage_record(
        provider=proxy_module.ProviderConfig(
            name="alpha",
            base_url="https://api.example.com/v1",
            api_key="provider-key",
        ),
        model="alpha-1",
        endpoint="/v1/responses",
        latency_ms=42,
        status=201,
        usage_fields={
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "reasoning_tokens": 1,
            "cached_tokens": 2,
            "total_tokens": 15,
        },
    )

    assert record["provider"] == "alpha"
    assert record["model"] == "alpha-1"
    assert record["endpoint"] == "/v1/responses"
    assert record["latency_ms"] == 42
    assert record["status"] == 201
    assert record["total_tokens"] == 15
    assert "ts" in record
