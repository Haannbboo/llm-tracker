from __future__ import annotations

import json
import time
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


def test_retired_gemini_logs_are_ignored_without_debug_dumps(
    otlp_module, monkeypatch, tmp_path: Path
):
    debug_file = tmp_path / "otlp-debug.json"
    captured = []
    monkeypatch.setattr(otlp_module, "CODEX_DEBUG_FILE", str(debug_file))
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        lambda **fields: captured.append(fields),
    )

    response = TestClient(otlp_module.app).post(
        "/v1/logs",
        json={
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "gemini-cli"},
                            }
                        ]
                    },
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "attributes": _attrs(
                                        {
                                            "event.name": "gemini_cli.api_response",
                                            "model": "gemini-3-flash-preview",
                                        }
                                    )
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert captured == []
    assert not debug_file.exists()
    assert not Path(f"{debug_file}.resource").exists()


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
    assert fields["total_tokens"] == 285  # prompt+completion+cache_creation
    assert fields["latency_ms"] == 1200
    assert fields["ttft_ms"] == 345
    assert fields["client_source"] == "opencode"
    assert fields["session_id"] == "oc-sess-1"
    assert fields["endpoint"] == "otlp"
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

    assert fields["total_tokens"] == 255  # prompt+completion+cache_creation
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


def test_prompt_length_tracker_records_and_consumes_matching_prompt_event(otlp_module):
    # This verifies the basic tracker contract: a prompt-only event stores the length,
    # and the later usage event for the same prompt/session consumes that exact value once.
    tracker = otlp_module.PromptLengthTracker({"codex.user_prompt"})

    prompt_attrs = _attrs(
        {
            "event.name": "codex.user_prompt",
            "session.id": "tracker-session-1",
            "prompt_id": "prompt-1",
            "prompt_length": 3210,
        }
    )
    tracker.record_prompt_event("codex", prompt_attrs, "tracker-session-1")

    response_attrs = _attrs(
        {
            "event.name": "codex.sse_event",
            "session.id": "tracker-session-1",
            "prompt_id": "prompt-1",
        }
    )

    assert (
        tracker.consume_for_usage_event("codex", response_attrs, "tracker-session-1")
        == 3210
    )
    assert (
        tracker.consume_for_usage_event("codex", response_attrs, "tracker-session-1")
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
                "event.name": "codex.sse_event",
                "event.kind": "response.completed",
                "conversation.id": "conv-inline",
                "model": "gpt-5.4",
                "prompt_length": 999,
                "input_token_count": 700,
                "output_token_count": 90,
            }
        ),
    }
    otlp_module._parse_log_record(response_record_1, "codex_cli_rs", "")

    response_ts_2 = datetime(2026, 4, 22, 21, 16, 0, tzinfo=timezone.utc)
    response_record_2 = {
        "timeUnixNano": str(int(response_ts_2.timestamp() * 1_000_000_000)),
        "attributes": _attrs(
            {
                "event.name": "codex.sse_event",
                "event.kind": "response.completed",
                "conversation.id": "conv-inline",
                "model": "gpt-5.4",
                "input_token_count": 710,
                "output_token_count": 95,
            }
        ),
    }
    otlp_module._parse_log_record(response_record_2, "codex_cli_rs", "")

    assert captured[0].prompt_length == 999
    assert captured[1].prompt_length == 0


def test_claude_tool_decision_missing_tool_use_id_gets_random_fallback(otlp_module):
    """A missing tool_use_id must not fall back to a shared "" PK, which would
    collide across unrelated sessions and silently drop tool calls."""
    record = {
        "attributes": _attrs(
            {"event.name": "tool_decision", "prompt.id": "p1", "tool_name": "Bash"}
        ),
        "timeUnixNano": "1000000000",
    }

    otlp_module._parse_log_record(record, "claude-code", "session-1")

    buffered = otlp_module._claude_tool_buffer["p1"]
    assert len(buffered) == 1
    assert buffered[0]["tool_use_id"]
    assert buffered[0]["tool_use_id"].startswith("generated:")


def test_claude_tool_decision_missing_tool_use_id_ids_are_unique(otlp_module):
    record = {
        "attributes": _attrs(
            {"event.name": "tool_decision", "prompt.id": "p1", "tool_name": "Bash"}
        ),
        "timeUnixNano": "1000000000",
    }

    otlp_module._parse_log_record(record, "claude-code", "session-1")
    otlp_module._parse_log_record(record, "claude-code", "session-1")

    ids = [entry["tool_use_id"] for entry in otlp_module._claude_tool_buffer["p1"]]
    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_receive_logs_evicts_stale_tool_buffer_entries(otlp_module):
    """Tool-call buffer entries older than 10 minutes must be swept so an
    aborted turn doesn't leak the entry for the life of the process."""
    client = TestClient(otlp_module.app)
    now_ms = int(time.time() * 1000)
    otlp_module._claude_tool_buffer["stale"] = [
        {"tool_name": "bash", "tool_use_id": "toolu_1", "ts": now_ms - 700_000}
    ]
    otlp_module._claude_tool_buffer["fresh"] = [
        {"tool_name": "bash", "tool_use_id": "toolu_2", "ts": now_ms}
    ]

    response = client.post("/v1/logs", json={})

    assert response.status_code == 200
    assert "stale" not in otlp_module._claude_tool_buffer
    assert "fresh" in otlp_module._claude_tool_buffer


# === Auth tests ===


def _minimal_otlp_body(
    service_name="claude-code", event_name="claude_code.api_request"
):
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                    ]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "attributes": _attrs(
                                    {
                                        "event.name": event_name,
                                        "input_tokens": 10,
                                        "output_tokens": 5,
                                        "model": "test-model",
                                        "status_code": 200,
                                    }
                                ),
                                "timeUnixNano": "1800000000000000000",
                            }
                        ]
                    }
                ],
            }
        ]
    }


def test_auth_disabled_no_token_records_usage(otlp_module, monkeypatch):
    """auth.enabled=false: POST /v1/logs with no token header records usage."""
    captured = []
    monkeypatch.setattr(
        otlp_module,
        "record_usage",
        lambda **fields: (
            captured.append(fields) or type("U", (), {"id": "u1", "session_id": "s1"})()
        ),
    )
    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", False)

    client = TestClient(otlp_module.app)
    response = client.post("/v1/logs", json=_minimal_otlp_body())

    assert response.status_code == 200
    assert len(captured) == 1


def test_auth_enabled_valid_ingest_token_records_user_id(
    otlp_module, monkeypatch, fresh_db
):
    """auth.enabled=true, valid ingest token: recorded usage carries user_id."""
    from src.auth.tokens import mint_token

    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", True)
    monkeypatch.setitem(otlp_module.CONFIG.get("otlp", {}), "max_body_bytes", 2_000_000)
    monkeypatch.setitem(
        otlp_module.CONFIG.get("otlp", {}), "rate_limit_per_minute", 300
    )

    token, user = mint_token("test@example.com", kind="ingest")

    captured = []

    def capture_usage(**fields):
        captured.append(fields)
        return type("U", (), {"id": "u1", "session_id": "s1"})()

    monkeypatch.setattr(otlp_module, "record_usage", capture_usage)

    client = TestClient(otlp_module.app)
    response = client.post(
        "/v1/logs",
        json=_minimal_otlp_body(),
        headers={"x-llm-tracker-token": token},
    )

    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["user_id"] == user.id


def test_auth_enabled_missing_header_returns_401(otlp_module, monkeypatch):
    """auth.enabled=true, missing header → 401, no row recorded."""
    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", True)

    captured = []
    monkeypatch.setattr(
        otlp_module, "record_usage", lambda **fields: captured.append(fields)
    )

    client = TestClient(otlp_module.app)
    response = client.post("/v1/logs", json=_minimal_otlp_body())

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid token"
    assert len(captured) == 0


def test_auth_enabled_wrong_kind_token_returns_401(otlp_module, monkeypatch, fresh_db):
    """auth.enabled=true, valid cli token → 401 (kind mismatch)."""
    from src.auth.tokens import mint_token

    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", True)

    token, _ = mint_token("test@example.com", kind="cli")

    captured = []
    monkeypatch.setattr(
        otlp_module, "record_usage", lambda **fields: captured.append(fields)
    )

    client = TestClient(otlp_module.app)
    response = client.post(
        "/v1/logs",
        json=_minimal_otlp_body(),
        headers={"x-llm-tracker-token": token},
    )

    assert response.status_code == 401
    assert len(captured) == 0


def test_auth_enabled_revoked_token_returns_401(otlp_module, monkeypatch, fresh_db):
    """auth.enabled=true, revoked ingest token → 401."""
    from src.auth.tokens import mint_token, revoke_token

    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", True)

    token, user = mint_token("test@example.com", kind="ingest")
    # Get token_id from the database
    from src.auth.tokens import resolve_token

    _, auth_token = resolve_token(token)
    revoke_token(auth_token.id, user.id)

    captured = []
    monkeypatch.setattr(
        otlp_module, "record_usage", lambda **fields: captured.append(fields)
    )

    client = TestClient(otlp_module.app)
    response = client.post(
        "/v1/logs",
        json=_minimal_otlp_body(),
        headers={"x-llm-tracker-token": token},
    )

    assert response.status_code == 401
    assert len(captured) == 0


def test_body_too_large_returns_413(otlp_module, monkeypatch):
    """Body larger than otlp.max_body_bytes → 413; record_usage is never called."""
    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", False)
    monkeypatch.setitem(otlp_module.CONFIG.get("otlp", {}), "max_body_bytes", 100)

    captured = []
    monkeypatch.setattr(
        otlp_module, "record_usage", lambda **fields: captured.append(fields)
    )

    client = TestClient(otlp_module.app)
    # Create a body larger than 100 bytes
    large_body = _minimal_otlp_body()
    large_body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"].append(
        {"key": "padding", "value": {"stringValue": "x" * 200}}
    )

    response = client.post("/v1/logs", json=large_body)

    assert response.status_code == 413
    assert len(captured) == 0


def test_body_too_large_streaming_cap_returns_413(otlp_module, monkeypatch):
    """Streaming body cap enforces limit when Content-Length is missing or understated."""
    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", False)
    monkeypatch.setitem(otlp_module.CONFIG.get("otlp", {}), "max_body_bytes", 100)

    captured = []
    monkeypatch.setattr(
        otlp_module, "record_usage", lambda **fields: captured.append(fields)
    )

    client = TestClient(otlp_module.app)
    large_body = _minimal_otlp_body()
    large_body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"].append(
        {"key": "padding", "value": {"stringValue": "x" * 200}}
    )
    body_bytes = json.dumps(large_body).encode()

    # Send with no Content-Length (chunked transfer)
    response = client.post(
        "/v1/logs",
        content=body_bytes,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert len(captured) == 0


def test_rate_limit_exceeded_returns_429(otlp_module, monkeypatch, fresh_db):
    """N+1th request within the window → 429; different token unaffected."""
    from src.auth.tokens import mint_token

    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", True)
    monkeypatch.setitem(otlp_module.CONFIG.get("otlp", {}), "rate_limit_per_minute", 2)

    token1, user1 = mint_token("user1@example.com", kind="ingest")
    token2, user2 = mint_token("user2@example.com", kind="ingest")

    captured = []

    def capture_usage(**fields):
        captured.append(fields)
        return type("U", (), {"id": "u1", "session_id": "s1"})()

    monkeypatch.setattr(otlp_module, "record_usage", capture_usage)

    client = TestClient(otlp_module.app)

    # First two requests from token1 should succeed
    for _ in range(2):
        response = client.post(
            "/v1/logs",
            json=_minimal_otlp_body(),
            headers={"x-llm-tracker-token": token1},
        )
        assert response.status_code == 200

    # Third request from token1 should be rate limited
    response = client.post(
        "/v1/logs",
        json=_minimal_otlp_body(),
        headers={"x-llm-tracker-token": token1},
    )
    assert response.status_code == 429

    # token2 should still work
    response = client.post(
        "/v1/logs",
        json=_minimal_otlp_body(),
        headers={"x-llm-tracker-token": token2},
    )
    assert response.status_code == 200


def test_health_routes_stay_unauthenticated(otlp_module, monkeypatch):
    """/health, /v1/metrics, /v1/traces stay unauthenticated regardless of auth.enabled."""
    monkeypatch.setitem(otlp_module.CONFIG.get("auth", {}), "enabled", True)

    client = TestClient(otlp_module.app)

    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.post("/v1/metrics", json={}).status_code == 200
    assert client.post("/v1/traces", json={}).status_code == 200
