from __future__ import annotations

import json
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
        lambda db_path, **fields: captured.update(
            {"db_path": db_path, "fields": fields}
        ),
    )

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
            "duration_ms": 8193,
        }
    )

    otlp_module._parse_gemini_record(record, attrs, "")

    assert captured["fields"]["provider"] == "google"
    assert captured["fields"]["model"] == "gemini-3-flash-preview"
    assert captured["fields"]["ttft_ms"] == 6845
    assert captured["fields"]["latency_ms"] == 8193
    assert not queue_path.exists()


def test_consume_gemini_ttft_missing_session_returns_none(
    otlp_module, monkeypatch, isolated_home: Path
):
    hook_dir = isolated_home / "gemini-hook"
    hook_dir.mkdir()

    monkeypatch.setattr(otlp_module, "GEMINI_HOOK_DIR", str(hook_dir))

    ttft_ms, latency_ms = otlp_module._consume_gemini_ttft("nonexistent-session")

    assert ttft_ms is None
    assert latency_ms is None


def test_consume_gemini_ttft_fifo_order(otlp_module, monkeypatch, isolated_home: Path):
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

    ttft1, lat1 = otlp_module._consume_gemini_ttft("session-3")
    assert ttft1 == 100
    assert lat1 == 200
    assert queue_path.exists()  # second entry remains

    ttft2, lat2 = otlp_module._consume_gemini_ttft("session-3")
    assert ttft2 == 300
    assert lat2 == 400
    assert not queue_path.exists()  # queue exhausted
