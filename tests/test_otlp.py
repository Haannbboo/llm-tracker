from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _attrs(values: dict[str, int | str]) -> list[dict]:
    attrs = []
    for key, value in values.items():
        if isinstance(value, int):
            payload = {"intValue": value}
        else:
            payload = {"stringValue": value}
        attrs.append({"key": key, "value": payload})
    return attrs


def _capture_usage(target: dict):
    return lambda **fields: target.update({"usage": SimpleNamespace(**fields)})


def test_health_routes_return_service_status(otlp_module):
    client = TestClient(otlp_module.app)

    for path in ("/health", "/"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "llm-tracker-otlp"}


def test_parse_gemini_record_merges_hook_ttft(
    otlp_module, monkeypatch, isolated_home: Path
):
    hook_dir = isolated_home / "gemini-hook"
    hook_dir.mkdir()
    queue_path = hook_dir / "queue-session-1.jsonl"
    queue_path.write_text(
        json.dumps({"session_id": "session-1", "ttft_ms": 6845, "latency_ms": 8719})
        + "\n",
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(otlp_module, "GEMINI_HOOK_DIR", str(hook_dir))
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    record_ts = datetime(2026, 4, 19, 20, 5, 1, 614000, tzinfo=timezone.utc)
    record = {"timeUnixNano": str(int(record_ts.timestamp() * 1_000_000_000))}
    attrs = _attrs(
        {
            "model": "gemini-3-flash-preview",
            "role": "main",
            "session.id": "session-1",
            "prompt_length": 4321,
            "input_token_count": 793,
            "output_token_count": 1359,
            "total_token_count": 2152,
        }
    )

    otlp_module._parse_gemini_record(record, attrs, "session-1")

    assert captured["usage"].ttft_ms == 6845
    assert captured["usage"].latency_ms == 8719
    assert captured["usage"].prompt_length == 4321
    assert captured["usage"].client_source == "gemini-cli"
    assert captured["usage"].status is None


def test_parse_gemini_record_resolves_base_url_id_from_local_config(
    otlp_module, monkeypatch, isolated_home: Path
):
    settings = isolated_home / ".gemini" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({"base_url": "https://generativelanguage.googleapis.com"}),
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    record_ts = datetime(2026, 4, 19, 20, 5, 1, 614000, tzinfo=timezone.utc)
    record = {"timeUnixNano": str(int(record_ts.timestamp() * 1_000_000_000))}
    attrs = _attrs(
        {
            "model": "gemini-3-flash-preview",
            "role": "main",
            "session.id": "session-1",
            "status_code": 429,
            "input_token_count": 793,
            "output_token_count": 1359,
            "total_token_count": 2152,
        }
    )

    otlp_module._parse_gemini_record(record, attrs, "session-1")

    assert captured["usage"].base_url == "https://generativelanguage.googleapis.com"
    assert captured["usage"].base_url_provider == "Google"
    assert captured["usage"].base_url_source == "gemini_settings"
    assert captured["usage"].provider == "Google"
    assert captured["usage"].status == 429


def test_extract_gemini_fields_basic(otlp_module):
    attrs = _attrs(
        {
            "input_token_count": 100,
            "output_token_count": 50,
            "thoughts_token_count": 10,
            "tool_token_count": 5,
            "model": "gemini-2.5-pro",
            "role": "main",
            "duration_ms": 500,
            "status_code": 200,
            "total_token_count": 165,
        }
    )
    record = {"timeUnixNano": "1800000000000000000"}

    fields = otlp_module._extract_gemini_fields(record, attrs, "sess-1")

    assert fields["provider"] is not None
    assert fields["model"] == "gemini-2.5-pro"
    assert fields["prompt_tokens"] == 100
    assert fields["completion_tokens"] == 65
    assert fields["reasoning_tokens"] == 10
    assert fields["tool_tokens"] == 5
    assert fields["total_tokens"] == 165
    assert fields["latency_ms"] == 500
    assert fields["status"] == 200
    assert fields["client_source"] == "gemini-cli"
    assert fields["endpoint"] == "generate-otlp"


def test_extract_claude_fields_basic(otlp_module):
    attrs = _attrs(
        {
            "input_tokens": 80,
            "output_tokens": 40,
            "cache_read_tokens": 20,
            "cache_creation_tokens": 10,
            "model": "claude-sonnet-4-20250514",
            "status_code": 200,
            "duration_ms": 300,
            "session.id": "claude-sess-1",
        }
    )
    record = {"timeUnixNano": "1800000000000000000"}

    fields = otlp_module._extract_claude_fields(record, attrs, "sess-1")

    assert fields["model"] == "claude-sonnet-4-20250514"
    assert fields["prompt_tokens"] == 100
    assert fields["completion_tokens"] == 40
    assert fields["cached_tokens"] == 20
    assert fields["cache_creation_tokens"] == 10
    assert fields["client_source"] == "claude-code"
    assert fields["session_id"] == "claude-sess-1"


def test_extract_codex_fields_basic(otlp_module):
    attrs = _attrs(
        {
            "event.kind": "response.completed",
            "input_token_count": 200,
            "output_token_count": 100,
            "cached_token_count": 50,
            "reasoning_token_count": 30,
            "tool_token_count": 10,
            "duration_ms": 800,
            "http.response.status_code": 200,
            "model": "o3",
            "conversation.id": "codex-conv-1",
        }
    )
    record = {"timeUnixNano": "1800000000000000000"}
    otlp_module.codex_state["codex-conv-1"] = {
        "ts": 0,
        "duration_ms": 800,
        "ttft_ms": 200,
    }

    fields = otlp_module._extract_codex_fields(record, attrs, "codex_cli_rs")

    assert fields["model"] == "o3"
    assert fields["prompt_tokens"] == 200
    assert fields["completion_tokens"] == 100
    assert fields["cached_tokens"] == 50
    assert fields["reasoning_tokens"] == 30
    assert fields["tool_tokens"] == 10
    assert fields["latency_ms"] == 800
    assert fields["ttft_ms"] == 200
    assert fields["client_source"] == "codex"


def test_extract_opencode_fields_basic(otlp_module):
    attrs = _attrs(
        {
            "input_token_count": 150,
            "output_token_count": 80,
            "reasoning_token_count": 20,
            "cached_token_count": 30,
            "cache_creation_token_count": 5,
            "total_token_count": 285,
            "prompt_length": 4321,
            "model": "claude-sonnet-4-5",
            "provider": "anthropic",
            "duration_ms": 1200,
            "ttft_ms": 345,
            "session.id": "oc-sess-1",
            "message.id": "msg-1",
        }
    )
    record = {"timeUnixNano": "1800000000000000000"}

    fields = otlp_module._extract_opencode_fields(record, attrs, "oc-sess-1")

    assert fields["model"] == "claude-sonnet-4-5"
    assert fields["provider"] == "anthropic"
    assert fields["prompt_tokens"] == 180
    assert fields["completion_tokens"] == 100
    assert fields["reasoning_tokens"] == 20
    assert fields["cached_tokens"] == 30
    assert fields["cache_creation_tokens"] == 5
    assert fields["total_tokens"] == 280
    assert fields["latency_ms"] == 1200
    assert fields["ttft_ms"] == 345
    assert fields["client_source"] == "opencode"
    assert fields["session_id"] == "oc-sess-1"
    assert fields["endpoint"] == "generate-otlp"
    assert fields["tool_tokens"] is None
    assert fields["prompt_length"] == 4321


def test_extract_opencode_fields_normalizes_total_when_raw_total_excludes_cache(
    otlp_module,
):
    attrs = _attrs(
        {
            "input_token_count": 807_100,
            "output_token_count": 0,
            "reasoning_token_count": 0,
            "cached_token_count": 10_000_000,
            "total_token_count": 807_100,
            "model": "deepseek-v4-flash-free",
            "provider": "deepseek",
            "session.id": "oc-sess-cache",
        }
    )
    record = {"timeUnixNano": "1800000000000000000"}

    fields = otlp_module._extract_opencode_fields(record, attrs, "oc-sess-cache")

    assert fields["prompt_tokens"] == 10_807_100
    assert fields["cached_tokens"] == 10_000_000
    assert fields["total_tokens"] == 10_807_100


def test_parse_opencode_record_routes_to_record_usage(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    record = {"timeUnixNano": "1800000000000000000"}
    attrs = _attrs(
        {
            "event.name": "opencode.message_completed",
            "session.id": "oc-sess-1",
            "message.id": "msg-1",
            "model": "claude-sonnet-4-5",
            "provider": "anthropic",
            "input_token_count": 100,
            "output_token_count": 50,
            "reasoning_token_count": 10,
            "cached_token_count": 20,
            "total_token_count": 180,
            "duration_ms": 800,
            "ttft_ms": 250,
        }
    )
    record["attributes"] = attrs

    otlp_module._parse_log_record(record, "opencode", "oc-sess-1")

    assert captured["usage"].client_source == "opencode"
    assert captured["usage"].model == "claude-sonnet-4-5"
    assert captured["usage"].provider == "anthropic"
    assert captured["usage"].prompt_tokens == 120
    assert captured["usage"].completion_tokens == 60
    assert captured["usage"].reasoning_tokens == 10
    assert captured["usage"].cached_tokens == 20
    assert captured["usage"].latency_ms == 800
    assert captured["usage"].ttft_ms == 250


def test_parse_opencode_record_uses_otlp_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    record = {"timeUnixNano": "1800000000000000000"}
    attrs = _attrs(
        {
            "event.name": "opencode.message_completed",
            "session.id": "oc-sess-1",
            "message.id": "msg-1",
            "model": "claude-sonnet-4-5",
            "provider": "anthropic",
            "input_token_count": 0,
            "output_token_count": 0,
            "total_token_count": 0,
            "duration_ms": 800,
            "status_code": 429,
        }
    )
    record["attributes"] = attrs

    otlp_module._parse_log_record(record, "opencode", "oc-sess-1")

    assert captured["usage"].client_source == "opencode"
    assert captured["usage"].status == 429


def test_parse_opencode_record_uses_http_response_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    record = {"timeUnixNano": "1800000000000000000"}
    attrs = _attrs(
        {
            "event.name": "opencode.message_completed",
            "session.id": "oc-sess-1",
            "message.id": "msg-1",
            "model": "claude-sonnet-4-5",
            "provider": "anthropic",
            "duration_ms": 800,
            "http.response.status_code": 500,
        }
    )
    record["attributes"] = attrs

    otlp_module._parse_log_record(record, "opencode", "oc-sess-1")

    assert captured["usage"].client_source == "opencode"
    assert captured["usage"].status == 500


def test_extract_opencode_fields_derives_total_with_reasoning_when_missing(
    otlp_module,
):
    attrs = _attrs(
        {
            "input_token_count": 150,
            "output_token_count": 80,
            "reasoning_token_count": 20,
            "cache_creation_token_count": 5,
        }
    )
    record = {"timeUnixNano": "1800000000000000000"}

    fields = otlp_module._extract_opencode_fields(record, attrs, "oc-sess-1")

    assert fields["total_tokens"] == 250
    assert fields["prompt_length"] == 0


def test_extract_opencode_fields_resolves_base_url_for_event_provider(
    otlp_module, isolated_home: Path
):
    config_path = isolated_home / ".config" / "opencode" / "opencode.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "anthropic": {"options": {"baseURL": "https://api.anthropic.com"}},
                    "openai": {"options": {"baseURL": "https://api.openai.com/v1"}},
                }
            }
        ),
        encoding="utf-8",
    )
    attrs = _attrs(
        {
            "provider": "openai",
            "model": "gpt-5.4",
            "input_token_count": 10,
            "output_token_count": 5,
        }
    )
    record = {"timeUnixNano": "1800000000000000000"}

    fields = otlp_module._extract_opencode_fields(record, attrs, "oc-sess-1")

    assert fields["provider"] == "openai"
    assert fields["base_url"] == "https://api.openai.com/v1"
    assert fields["base_url_provider"] == "OpenAI"
    assert fields["base_url_source"] == "opencode_config"


def test_extract_gemini_fields_resolves_base_url_from_local_config(
    otlp_module, isolated_home: Path
):
    settings = isolated_home / ".gemini" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({"base_url": "https://generativelanguage.googleapis.com"}),
        encoding="utf-8",
    )

    record = {"timeUnixNano": "1800000000000000000"}
    attrs = _attrs({"model": "gemini-test", "status_code": 429})

    fields = otlp_module._extract_gemini_fields(record, attrs, "session-1")

    assert {
        "base_url": fields["base_url"],
        "provider_name": fields["base_url_provider"],
        "source": fields["base_url_source"],
    } == {
        "base_url": "https://generativelanguage.googleapis.com",
        "provider_name": "Google",
        "source": "gemini_settings",
    }


def test_parse_gemini_record_falls_back_to_http_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(otlp_module, "record_usage", _capture_usage(captured))

    record_ts = datetime(2026, 4, 19, 20, 5, 1, 614000, tzinfo=timezone.utc)
    record = {"timeUnixNano": str(int(record_ts.timestamp() * 1_000_000_000))}
    attrs = _attrs(
        {
            "model": "gemini-3-flash-preview",
            "role": "main",
            "session.id": "session-1",
            "http.status_code": 502,
            "input_token_count": 793,
            "output_token_count": 1359,
            "total_token_count": 2152,
        }
    )

    otlp_module._parse_gemini_record(record, attrs, "session-1")

    assert captured["usage"].status == 502


def test_parse_gemini_record_prefers_log_session_id_over_resource(
    otlp_module, monkeypatch
):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        lambda **fields: captured.setdefault("usage", SimpleNamespace(**fields)),
    )
    monkeypatch.setattr(
        otlp_module,
        "_consume_hook_ttft",
        lambda hook_dir, session_id: (None, None),
    )

    record = {
        "timeUnixNano": "1710000000000000000",
        "attributes": [
            {"key": "event.name", "value": {"stringValue": "gemini_cli.api_response"}},
            {"key": "model", "value": {"stringValue": "gemini-test"}},
            {"key": "session.id", "value": {"stringValue": "gemini-log-session"}},
            {"key": "input_token_count", "value": {"intValue": "10"}},
            {"key": "output_token_count", "value": {"intValue": "5"}},
            {"key": "total_token_count", "value": {"intValue": "15"}},
            {"key": "role", "value": {"stringValue": "main"}},
        ],
    }

    otlp_module._parse_log_record(record, "gemini-cli", "gemini-resource-session")

    assert captured["usage"].session_id == "gemini-log-session"


def test_parse_gemini_record_falls_back_to_resource_session_id(
    otlp_module, monkeypatch
):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        lambda **fields: captured.setdefault("usage", SimpleNamespace(**fields)),
    )
    monkeypatch.setattr(
        otlp_module,
        "_consume_hook_ttft",
        lambda hook_dir, session_id: (None, None),
    )

    record = {
        "timeUnixNano": "1710000000000000000",
        "attributes": [
            {"key": "event.name", "value": {"stringValue": "gemini_cli.api_response"}},
            {"key": "model", "value": {"stringValue": "gemini-test"}},
            {"key": "input_token_count", "value": {"intValue": "10"}},
            {"key": "output_token_count", "value": {"intValue": "5"}},
            {"key": "total_token_count", "value": {"intValue": "15"}},
            {"key": "role", "value": {"stringValue": "main"}},
        ],
    }

    otlp_module._parse_log_record(record, "gemini-cli", "gemini-resource-session")

    assert captured["usage"].session_id == "gemini-resource-session"


def test_prompt_length_tracker_records_and_consumes_matching_prompt_event(otlp_module):
    # This verifies the basic tracker contract: a prompt-only event stores the length,
    # and the later usage event for the same prompt/session consumes that exact value once.
    tracker = otlp_module.PromptLengthTracker({"gemini_cli.user_prompt"})

    prompt_attrs = _attrs(
        {
            "event.name": "gemini_cli.user_prompt",
            "session.id": "gemini-session-1",
            "prompt_id": "prompt-1",
            "prompt_length": 3210,
        }
    )
    tracker.record_prompt_event("gemini-cli", prompt_attrs, "gemini-session-1")

    response_attrs = _attrs(
        {
            "event.name": "gemini_cli.api_response",
            "session.id": "gemini-session-1",
            "prompt_id": "prompt-1",
        }
    )

    assert (
        tracker.consume_for_usage_event(
            "gemini-cli", response_attrs, "gemini-session-1"
        )
        == 3210
    )
    assert (
        tracker.consume_for_usage_event(
            "gemini-cli", response_attrs, "gemini-session-1"
        )
        == 0
    )


def test_parse_claude_record_uses_prompt_length_from_prior_prompt_event(
    otlp_module, monkeypatch
):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    prompt_record = {
        "timeUnixNano": "0",
        "attributes": _attrs(
            {
                "event.name": "user_prompt",
                "session.id": "claude-session-1",
                "prompt.id": "prompt-1",
                "prompt_length": 2468,
            }
        ),
    }
    otlp_module._parse_log_record(prompt_record, "claude-code", "claude-session-1")

    response_ts = datetime(2026, 4, 22, 21, 0, 0, tzinfo=timezone.utc)
    response_record = {
        "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "api_request",
                "session.id": "claude-session-1",
                "prompt.id": "prompt-1",
                "model": "claude-test",
                "input_tokens": 120,
                "output_tokens": 20,
                "cache_read_tokens": 5,
                "cache_creation_tokens": 0,
                "duration_ms": 900,
            }
        ),
    }

    otlp_module._parse_log_record(response_record, "claude-code", "claude-session-1")

    assert captured["usage"].prompt_length == 2468
    assert captured["usage"].client_source == "claude-code"
    assert captured["usage"].session_id == "claude-session-1"
    assert captured["usage"].status is None


def test_parse_claude_record_uses_otlp_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(otlp_module, "record_usage", _capture_usage(captured))

    response_ts = datetime(2026, 4, 22, 21, 0, 0, tzinfo=timezone.utc)
    response_record = {
        "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "api_request",
                "session.id": "claude-session-1",
                "prompt.id": "prompt-1",
                "model": "claude-test",
                "input_tokens": 120,
                "output_tokens": 20,
                "cache_read_tokens": 5,
                "cache_creation_tokens": 0,
                "duration_ms": 900,
                "status_code": 400,
            }
        ),
    }

    otlp_module._parse_log_record(response_record, "claude-code", "claude-session-1")

    assert captured["usage"].status == 400


def test_parse_codex_record_uses_prompt_length_from_prior_prompt_event(
    otlp_module, monkeypatch
):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    prompt_record = {
        "timeUnixNano": "0",
        "attributes": _attrs(
            {
                "event.name": "codex.user_prompt",
                "conversation.id": "conv-1",
                "model": "gpt-5.4",
                "prompt_length": 88,
            }
        ),
    }
    otlp_module._parse_log_record(prompt_record, "codex_cli_rs", "")

    response_ts = datetime(2026, 4, 22, 21, 5, 0, tzinfo=timezone.utc)
    response_record = {
        "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "codex.sse_event",
                "event.kind": "response.completed",
                "conversation.id": "conv-1",
                "model": "gpt-5.4",
                "input_token_count": 500,
                "output_token_count": 100,
                "cached_token_count": 10,
                "reasoning_token_count": 20,
                "tool_token_count": 5,
                "duration_ms": 2000,
            }
        ),
    }

    otlp_module._parse_log_record(response_record, "codex_cli_rs", "")

    assert captured["usage"].prompt_length == 88
    assert captured["usage"].client_source == "codex"
    assert captured["usage"].session_id == "conv-1"
    assert captured["usage"].status is None


def test_parse_codex_exec_record_uses_same_usage_parser(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    prompt_record = {
        "timeUnixNano": "0",
        "attributes": _attrs(
            {
                "event.name": "codex.user_prompt",
                "conversation.id": "exec-conv-1",
                "model": "gpt-5.5",
                "prompt_length": 42,
            }
        ),
    }
    otlp_module._parse_log_record(prompt_record, "codex_exec", "")

    response_ts = datetime(2026, 5, 3, 17, 0, 0, tzinfo=timezone.utc)
    response_record = {
        "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "codex.sse_event",
                "event.kind": "response.completed",
                "conversation.id": "exec-conv-1",
                "model": "gpt-5.5",
                "input_token_count": 21742,
                "output_token_count": 6,
                "cached_token_count": 6528,
                "reasoning_token_count": 0,
                "duration_ms": 12338,
            }
        ),
    }

    otlp_module._parse_log_record(response_record, "codex_exec", "")

    assert captured["usage"].client_source == "codex"
    assert captured["usage"].session_id == "exec-conv-1"
    assert captured["usage"].prompt_length == 42
    assert captured["usage"].prompt_tokens == 21742
    assert captured["usage"].completion_tokens == 6
    assert captured["usage"].cached_tokens == 6528


def test_usage_session_id_casts_codex_conversation_id_to_string(otlp_module):
    attrs = [{"key": "conversation.id", "value": {"intValue": "123"}}]

    assert (
        otlp_module._usage_session_id(
            service_name="codex_cli_rs",
            attrs=attrs,
            resource_session_id="ignored",
        )
        == "123"
    )


def test_parse_codex_record_persists_integer_conversation_id_as_string(
    otlp_module,
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(otlp_module, "record_usage", _capture_usage(captured))

    response_ts = datetime(2026, 4, 22, 21, 5, 0, tzinfo=timezone.utc)
    response_record = {
        "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "codex.sse_event",
                "event.kind": "response.completed",
                "conversation.id": 123,
                "model": "gpt-5.4",
                "input_token_count": 500,
                "output_token_count": 100,
            }
        ),
    }

    otlp_module._parse_log_record(response_record, "codex_cli_rs", "")

    assert captured["usage"].session_id == "123"


def test_parse_codex_record_uses_http_response_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(otlp_module, "record_usage", _capture_usage(captured))

    response_ts = datetime(2026, 4, 22, 21, 5, 0, tzinfo=timezone.utc)
    response_record = {
        "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "codex.sse_event",
                "event.kind": "response.completed",
                "conversation.id": "conv-1",
                "model": "gpt-5.4",
                "input_token_count": 500,
                "output_token_count": 100,
                "cached_token_count": 10,
                "reasoning_token_count": 20,
                "tool_token_count": 5,
                "duration_ms": 2000,
                "http.response.status_code": 429,
            }
        ),
    }

    otlp_module._parse_log_record(response_record, "codex_cli_rs", "")

    assert captured["usage"].status == 429


def test_parse_gemini_record_uses_prompt_length_from_prior_prompt_event(
    otlp_module, monkeypatch
):
    captured = {}
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        _capture_usage(captured),
    )

    prompt_record = {
        "timeUnixNano": "0",
        "attributes": _attrs(
            {
                "event.name": "gemini_cli.user_prompt",
                "session.id": "gemini-session-1",
                "prompt_id": "prompt-1",
                "prompt_length": 3210,
            }
        ),
    }
    otlp_module._parse_log_record(prompt_record, "gemini-cli", "gemini-session-1")

    response_ts = datetime(2026, 4, 22, 21, 10, 0, tzinfo=timezone.utc)
    response_record = {
        "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "gemini_cli.api_response",
                "session.id": "gemini-session-1",
                "prompt_id": "prompt-1",
                "model": "gemini-3-flash-preview",
                "role": "main",
                "input_token_count": 700,
                "output_token_count": 90,
                "total_token_count": 790,
            }
        ),
    }

    otlp_module._parse_log_record(response_record, "gemini-cli", "gemini-session-1")

    assert captured["usage"].prompt_length == 3210
    assert captured["usage"].status is None


def test_inline_prompt_length_is_not_queued_for_next_request(otlp_module, monkeypatch):
    captured = []
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        lambda **fields: captured.append(SimpleNamespace(**fields)),
    )

    response_ts_1 = datetime(2026, 4, 22, 21, 15, 0, tzinfo=timezone.utc)
    response_record_1 = {
        "timeUnixNano": str(int(response_ts_1.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "gemini_cli.api_response",
                "session.id": "gemini-session-inline",
                "model": "gemini-3-flash-preview",
                "role": "main",
                "prompt_length": 999,
                "input_token_count": 700,
                "output_token_count": 90,
                "total_token_count": 790,
            }
        ),
    }
    otlp_module._parse_log_record(
        response_record_1, "gemini-cli", "gemini-session-inline"
    )

    response_ts_2 = datetime(2026, 4, 22, 21, 16, 0, tzinfo=timezone.utc)
    response_record_2 = {
        "timeUnixNano": str(int(response_ts_2.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "gemini_cli.api_response",
                "session.id": "gemini-session-inline",
                "model": "gemini-3-flash-preview",
                "role": "main",
                "input_token_count": 710,
                "output_token_count": 95,
                "total_token_count": 805,
            }
        ),
    }
    otlp_module._parse_log_record(
        response_record_2, "gemini-cli", "gemini-session-inline"
    )

    assert captured[0].prompt_length == 999
    assert captured[1].prompt_length == 0


def test_consume_hook_ttft_missing_session_returns_none(
    otlp_module, monkeypatch, isolated_home: Path
):
    hook_dir = isolated_home / "gemini-hook"
    hook_dir.mkdir()

    monkeypatch.setattr(otlp_module, "GEMINI_HOOK_DIR", str(hook_dir))

    ttft_ms, latency_ms = otlp_module._consume_hook_ttft(
        otlp_module.GEMINI_HOOK_DIR, "nonexistent-session"
    )

    assert ttft_ms is None
    assert latency_ms is None


def test_consume_hook_ttft_fifo_order(otlp_module, monkeypatch, isolated_home: Path):
    hook_dir = isolated_home / "gemini-hook"
    hook_dir.mkdir()
    queue_path = hook_dir / "queue-session-3.jsonl"
    queue_path.write_text(
        json.dumps({"session_id": "session-3", "ttft_ms": 100, "latency_ms": 200})
        + "\n"
        + json.dumps({"session_id": "session-3", "ttft_ms": 300, "latency_ms": 400})
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(otlp_module, "GEMINI_HOOK_DIR", str(hook_dir))

    ttft1, lat1 = otlp_module._consume_hook_ttft(
        otlp_module.GEMINI_HOOK_DIR, "session-3"
    )
    assert ttft1 == 100
    assert lat1 == 200
    assert queue_path.exists()  # second entry remains

    ttft2, lat2 = otlp_module._consume_hook_ttft(
        otlp_module.GEMINI_HOOK_DIR, "session-3"
    )
    assert ttft2 == 300
    assert lat2 == 400
    assert not queue_path.exists()  # queue exhausted
