from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path


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
    return lambda usage, db_path=None: target.update(
        {"db_path": db_path, "usage": usage}
    )


def _set_global_model_cost(
    config_module, model: str, *, input: float, output: float, cache_read: float
):
    previous_model_costs = dict(config_module.MODEL_COSTS)
    previous_provider_model_costs = {
        provider: dict(costs)
        for provider, costs in config_module.PROVIDER_MODEL_COSTS.items()
    }
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS[model] = config_module.ModelCost(
        input=input,
        output=output,
        cache_read=cache_read,
    )
    config_module.PROVIDER_MODEL_COSTS.clear()
    return previous_model_costs, previous_provider_model_costs


def _restore_model_costs(
    config_module, previous_model_costs, previous_provider_model_costs
):
    config_module.MODEL_COSTS.clear()
    config_module.MODEL_COSTS.update(previous_model_costs)
    config_module.PROVIDER_MODEL_COSTS.clear()
    config_module.PROVIDER_MODEL_COSTS.update(previous_provider_model_costs)


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
        "log_usage",
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

    def fake_resolve_base_url_id(**kwargs):
        captured["resolve"] = kwargs
        return 11

    monkeypatch.setattr(otlp_module, "resolve_base_url_id", fake_resolve_base_url_id)
    monkeypatch.setattr(
        otlp_module,
        "log_usage",
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

    assert captured["resolve"] == {
        "base_url": "https://generativelanguage.googleapis.com",
        "provider_name": "Google",
        "source": "gemini_settings",
    }
    assert captured["usage"].base_url_id == 11
    assert captured["usage"].provider == "Google"
    assert captured["usage"].status == 429


def test_parse_gemini_record_persists_costs(otlp_module, config_module, monkeypatch):
    previous_model_costs, previous_provider_model_costs = _set_global_model_cost(
        config_module,
        "gemini-3-flash-preview",
        input=2.0,
        output=6.0,
        cache_read=0.5,
    )
    captured = {}
    monkeypatch.setattr(otlp_module, "log_usage", _capture_usage(captured))

    try:
        record_ts = datetime(2026, 4, 19, 20, 5, 1, 614000, tzinfo=timezone.utc)
        record = {"timeUnixNano": str(int(record_ts.timestamp() * 1_000_000_000))}
        attrs = _attrs(
            {
                "model": "gemini-3-flash-preview",
                "role": "main",
                "session.id": "session-1",
                "input_token_count": 793,
                "output_token_count": 1359,
                "total_token_count": 2152,
            }
        )

        otlp_module._parse_gemini_record(record, attrs, "session-1")

        assert captured["usage"].input_cost_usd == Decimal("0.001586")
        assert captured["usage"].output_cost_usd == Decimal("0.008154")
        assert captured["usage"].total_cost_usd == Decimal("0.00974")
    finally:
        _restore_model_costs(
            config_module, previous_model_costs, previous_provider_model_costs
        )


def test_parse_gemini_record_falls_back_to_http_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(otlp_module, "log_usage", _capture_usage(captured))

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
        "log_usage",
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
    assert captured["usage"].status is None


def test_parse_claude_record_persists_costs(otlp_module, config_module, monkeypatch):
    previous_model_costs, previous_provider_model_costs = _set_global_model_cost(
        config_module,
        "claude-test",
        input=3.0,
        output=15.0,
        cache_read=0.3,
    )
    captured = {}
    monkeypatch.setattr(otlp_module, "log_usage", _capture_usage(captured))

    try:
        response_ts = datetime(2026, 4, 22, 21, 0, 0, tzinfo=timezone.utc)
        response_record = {
            "timeUnixNano": str(int(response_ts.timestamp() * 1_000_000_000)),
            "attributes": _attrs(
                {
                    "event.name": "api_request",
                    "session.id": "claude-session-1",
                    "model": "claude-test",
                    "input_tokens": 120,
                    "output_tokens": 20,
                    "cache_read_tokens": 5,
                    "cache_creation_tokens": 0,
                    "duration_ms": 900,
                }
            ),
        }

        otlp_module._parse_log_record(
            response_record, "claude-code", "claude-session-1"
        )

        assert captured["usage"].input_cost_usd == Decimal("0.0003615")
        assert captured["usage"].output_cost_usd == Decimal("0.0003")
        assert captured["usage"].total_cost_usd == Decimal("0.0006615")
    finally:
        _restore_model_costs(
            config_module, previous_model_costs, previous_provider_model_costs
        )


def test_parse_claude_record_uses_otlp_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(otlp_module, "log_usage", _capture_usage(captured))

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
        "log_usage",
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
    assert captured["usage"].status is None


def test_parse_codex_record_persists_costs(otlp_module, config_module, monkeypatch):
    previous_model_costs, previous_provider_model_costs = _set_global_model_cost(
        config_module,
        "gpt-5.4",
        input=1.25,
        output=10.0,
        cache_read=0.125,
    )
    captured = {}
    monkeypatch.setattr(otlp_module, "log_usage", _capture_usage(captured))

    try:
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

        assert captured["usage"].input_cost_usd == Decimal("0.00061375")
        assert captured["usage"].output_cost_usd == Decimal("0.001")
        assert captured["usage"].total_cost_usd == Decimal("0.00161375")
    finally:
        _restore_model_costs(
            config_module, previous_model_costs, previous_provider_model_costs
        )


def test_parse_codex_record_uses_http_response_status_code(otlp_module, monkeypatch):
    captured = {}
    monkeypatch.setattr(otlp_module, "log_usage", _capture_usage(captured))

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
        "log_usage",
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
        "log_usage",
        lambda usage, db_path=None: captured.append(usage),
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
