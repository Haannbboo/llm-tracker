from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


def test_parse_generic_command(cli_module):
    args = cli_module.parse_args(["--json", "--", "codex", "-m", "gpt-test"])

    assert args.json is True
    assert args.command == ["codex", "-m", "gpt-test"]


def test_parse_agent_alias_command(cli_module):
    args = cli_module.parse_args(["claude", "--dangerously-skip-permissions"])

    assert args.command == ["claude", "--dangerously-skip-permissions"]


def test_parse_default_wait_time_is_three_seconds(cli_module):
    args = cli_module.parse_args(["codex"])
    options = cli_module.options_from_args(args)

    assert args.wait_ms == 3000
    assert options.wait_ms == 3000


def test_parse_requires_command(cli_module):
    result = cli_module.main([])

    assert result == 2


class FakeClient:
    def __init__(self):
        self.before_calls = 0
        self.summary_calls = []

    def get_high_watermark(self):
        self.before_calls += 1
        return 10

    def get_run_summary(self, *, after_id, until_id=None):
        self.summary_calls.append({"after_id": after_id, "until_id": until_id})
        return {
            "window": {"after_id": after_id, "until_id": 11, "row_count": 1},
            "summary": {
                "requests": 1,
                "successful_requests": 1,
                "failed_requests": 0,
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "reasoning_tokens": 5,
                "cached_tokens": 50,
                "tool_tokens": 0,
                "cache_creation_tokens": 0,
                "total_tokens": 125,
                "cache_hit_rate": 0.5,
                "avg_latency_ms": 1000,
                "avg_ttft_ms": 200,
                "total_cost_usd": 0.12,
            },
            "sessions": [],
            "client_sources": [],
            "models": [],
        }


def test_run_command_preserves_child_exit_code(cli_module, monkeypatch, capsys):
    fake_client = FakeClient()
    calls = {}

    def fake_run(command, env=None):
        calls["command"] = command
        calls["env"] = env
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command", "--flag"],
        client=fake_client,
        options=cli_module.RunOptions(wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 7
    assert calls["command"] == ["fake-command", "--flag"]
    assert calls["env"] is None
    assert fake_client.before_calls == 1
    assert fake_client.summary_calls == [{"after_id": 10, "until_id": None}]
    assert "requests: 1" in captured.err


def test_run_command_handles_unavailable_api_before_child(
    cli_module, monkeypatch, capsys
):
    class BrokenClient:
        def get_high_watermark(self):
            raise cli_module.ApiError("api down")

    def fake_run(command, env=None):
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        client=BrokenClient(),
        options=cli_module.RunOptions(wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "llm-tracker API unavailable before command start" in captured.err
    assert "No summary could be produced." in captured.err


def test_high_watermark_malformed_response_raises_api_error(cli_module, monkeypatch):
    client = cli_module.UsageApiClient(base_url="http://example.test")
    monkeypatch.setattr(client, "_get_json", lambda path: {"missing": "id"})

    try:
        client.get_high_watermark()
    except cli_module.ApiError:
        pass
    else:
        raise AssertionError("expected ApiError")


def test_json_summary_defaults_to_stderr(cli_module, monkeypatch, capsys):
    fake_client = FakeClient()

    def fake_run(command, env=None):
        print("child stdout")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        client=fake_client,
        options=cli_module.RunOptions(json_output=True, wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "child stdout\n"
    parsed = json.loads(captured.err)
    assert parsed["summary"]["requests"] == 1


def test_no_summary_skips_summary_call(cli_module, monkeypatch, capsys):
    fake_client = FakeClient()

    def fake_run(command, env=None):
        return subprocess.CompletedProcess(command, 3)

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        client=fake_client,
        options=cli_module.RunOptions(no_summary=True, wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 3
    assert fake_client.before_calls == 1
    assert fake_client.summary_calls == []
    assert captured.out == ""
    assert captured.err == ""


def test_proxy_env_sets_base_urls_without_overwriting(cli_module, monkeypatch):
    monkeypatch.setitem(cli_module.CONFIG["server"], "host", "127.0.0.1")
    monkeypatch.setitem(cli_module.CONFIG["server"], "port", 4999)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://existing.example/v1")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    env = cli_module.build_child_env(cli_module.RunOptions(proxy_env=True))

    assert env["OPENAI_BASE_URL"] == "https://existing.example/v1"
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:4999"
    assert "OTEL_RESOURCE_ATTRIBUTES" not in env


def test_build_child_env_returns_none_without_proxy_env(cli_module, monkeypatch):
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=test-agent")

    env = cli_module.build_child_env(cli_module.RunOptions())

    assert env is None


def _write_codex_exec_session(
    path: Path,
    *,
    session_id: str = "exec-session-1",
    turn_id: str = "exec-turn-1",
    cwd: str,
    model: str = "gpt-5.5",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2026-05-03T17:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": "2026-05-03T17:00:00.000Z",
                "cwd": cwd,
                "originator": "codex_exec",
                "source": "exec",
            },
        },
        {
            "timestamp": "2026-05-03T17:00:01.000Z",
            "type": "turn_context",
            "payload": {
                "turn_id": turn_id,
                "cwd": cwd,
                "model": model,
            },
        },
        {
            "timestamp": "2026-05-03T17:00:12.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 21742,
                        "cached_input_tokens": 6528,
                        "output_tokens": 6,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 21748,
                    },
                    "total_token_usage": {
                        "input_tokens": 41898,
                        "cached_input_tokens": 24320,
                        "output_tokens": 254,
                        "reasoning_output_tokens": 169,
                        "total_tokens": 42152,
                    },
                },
            },
        },
        {
            "timestamp": "2026-05-03T17:00:12.100Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": turn_id,
                "duration_ms": 12338,
                "time_to_first_token_ms": 8263,
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(line, separators=(",", ":")) for line in lines) + "\n",
        encoding="utf-8",
    )


def test_extract_codex_exec_usage_from_session_jsonl(
    cli_module,
    isolated_home,
    tmp_path,
):
    codex_config = isolated_home / ".codex" / "config.toml"
    codex_config.parent.mkdir(parents=True, exist_ok=True)
    codex_config.write_text(
        'base_url = "https://free.codesonline.dev"\n',
        encoding="utf-8",
    )
    session_file = (
        isolated_home
        / ".codex"
        / "sessions"
        / "2026"
        / "05"
        / "03"
        / "rollout-2026-05-03T12-00-00-exec-session-1.jsonl"
    )
    _write_codex_exec_session(session_file, cwd=str(tmp_path))

    usage = cli_module.extract_codex_exec_usage_from_session(
        session_file,
        command_cwd=str(tmp_path),
    )

    assert usage == {
        "ts": "2026-05-03T17:00:12.100000+00:00",
        "provider": "codesonline",
        "model": "gpt-5.5",
        "client_source": "codex",
        "session_id": "exec-session-1",
        "endpoint": "generate-codex-session",
        "prompt_tokens": 21742,
        "prompt_length": 0,
        "completion_tokens": 6,
        "cached_tokens": 6528,
        "reasoning_tokens": 0,
        "tool_tokens": None,
        "cache_creation_tokens": None,
        "total_tokens": 21748,
        "latency_ms": 12338,
        "ttft_ms": 8263,
        "status": None,
        "base_url": "https://free.codesonline.dev",
        "base_url_source": "codex_config",
    }


def test_extract_codex_exec_usage_ignores_non_exec_session(
    cli_module,
    tmp_path,
):
    session_file = tmp_path / "session.jsonl"
    _write_codex_exec_session(session_file, cwd=str(tmp_path))
    lines = session_file.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["payload"]["originator"] = "codex-tui"
    lines[0] = json.dumps(first)
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    usage = cli_module.extract_codex_exec_usage_from_session(
        session_file,
        command_cwd=str(tmp_path),
    )

    assert usage is None


def test_run_command_records_codex_exec_session_fallback(
    cli_module,
    isolated_home,
    monkeypatch,
    tmp_path,
):
    class CodexExecClient:
        def __init__(self):
            self.recorded_usage = []
            self.summary_calls = []

        def get_high_watermark(self):
            return 10

        def get_run_summary(self, *, after_id, until_id=None, **filters):
            self.summary_calls.append(
                {"after_id": after_id, "until_id": until_id, **filters}
            )
            if filters.get("session_id") == "exec-session-1":
                return {
                    "window": {"after_id": after_id, "until_id": 10, "row_count": 0},
                    "summary": {"requests": 0},
                    "sessions": [],
                    "client_sources": [],
                    "models": [],
                }
            requests = len(self.recorded_usage)
            return {
                "window": {
                    "after_id": after_id,
                    "until_id": 10 + requests,
                    "row_count": requests,
                },
                "summary": {"requests": requests},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

        def record_usage(self, usage):
            self.recorded_usage.append(usage)

    def fake_run(command, env=None):
        _write_codex_exec_session(
            isolated_home
            / ".codex"
            / "sessions"
            / "2026"
            / "05"
            / "03"
            / "rollout-2026-05-03T12-00-00-exec-session-1.jsonl",
            cwd=os.getcwd(),
        )
        return subprocess.CompletedProcess(command, 0)

    client = CodexExecClient()
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["codex", "exec", "say hello"],
        client=client,
        options=cli_module.RunOptions(json_output=True, wait_ms=0),
    )

    assert code == 0
    assert len(client.recorded_usage) == 1
    assert client.recorded_usage[0]["session_id"] == "exec-session-1"
    assert client.recorded_usage[0]["prompt_tokens"] == 21742
    assert client.recorded_usage[0]["completion_tokens"] == 6
    assert {
        "after_id": 10,
        "until_id": None,
        "client_source": "codex",
        "session_id": "exec-session-1",
    } in client.summary_calls


def test_run_command_skips_codex_exec_fallback_when_otlp_record_exists(
    cli_module,
    isolated_home,
    monkeypatch,
):
    class CodexExecClient:
        def __init__(self):
            self.recorded_usage = []

        def get_high_watermark(self):
            return 10

        def get_run_summary(self, *, after_id, until_id=None, **filters):
            return {
                "window": {"after_id": after_id, "until_id": 11, "row_count": 1},
                "summary": {"requests": 1},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

        def record_usage(self, usage):
            self.recorded_usage.append(usage)

    def fake_run(command, env=None):
        _write_codex_exec_session(
            isolated_home
            / ".codex"
            / "sessions"
            / "2026"
            / "05"
            / "03"
            / "rollout-2026-05-03T12-00-00-exec-session-1.jsonl",
            cwd=os.getcwd(),
        )
        return subprocess.CompletedProcess(command, 0)

    client = CodexExecClient()
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["codex", "exec", "say hello"],
        client=client,
        options=cli_module.RunOptions(wait_ms=0),
    )

    assert code == 0
    assert client.recorded_usage == []


def test_api_client_passes_until_id_query_param(cli_module, monkeypatch):
    captured = {}
    client = cli_module.UsageApiClient(base_url="http://example.test")

    def fake_get_json(path, *, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"summary": {"requests": 0}}

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    client.get_run_summary(after_id=10, until_id=12)

    assert captured == {
        "path": "/usage/run-summary",
        "params": {"after_id": 10, "until_id": 12},
    }


def test_run_command_bounds_watermark_fallback_after_wait(
    cli_module,
    monkeypatch,
):
    class FallbackClient:
        def __init__(self):
            self.watermarks = [10, 12]
            self.summary_calls = []
            self.events = []

        def get_high_watermark(self):
            self.events.append("watermark")
            return self.watermarks.pop(0)

        def get_run_summary(self, *, after_id, until_id=None):
            self.events.append(f"summary:{until_id or 'open'}")
            self.summary_calls.append({"after_id": after_id, "until_id": until_id})
            if until_id is None:
                return {
                    "window": {
                        "after_id": after_id,
                        "until_id": after_id,
                        "row_count": 0,
                    },
                    "summary": {"requests": 0},
                    "sessions": [],
                    "client_sources": [],
                    "models": [],
                }
            return {
                "window": {"after_id": after_id, "until_id": until_id, "row_count": 1},
                "summary": {"requests": 1},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

    def fake_run(command, env=None):
        return subprocess.CompletedProcess(command, 0)

    client = FallbackClient()
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        client=client,
        options=cli_module.RunOptions(wait_ms=0),
    )

    assert code == 0
    assert client.summary_calls == [
        {"after_id": 10, "until_id": None},
        {"after_id": 10, "until_id": 12},
    ]
    assert client.events == [
        "watermark",
        "summary:open",
        "watermark",
        "summary:12",
    ]


def test_poll_summary_waits_until_deadline_for_later_run_rows(
    cli_module,
    monkeypatch,
):
    class DelayedClient:
        def __init__(self):
            self.requests = [1, 2]

        def get_run_summary(self, *, after_id, until_id=None):
            requests = self.requests.pop(0)
            return {
                "window": {
                    "after_id": after_id,
                    "until_id": 10 + requests,
                    "row_count": requests,
                },
                "summary": {"requests": requests},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

    monotonic_values = [0.0, 0.1, 0.4]
    monkeypatch.setattr(cli_module.time, "monotonic", lambda: monotonic_values.pop(0))
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    summary = cli_module.poll_summary(
        DelayedClient(),
        after_id=10,
        options=cli_module.RunOptions(wait_ms=300),
    )

    assert summary["summary"]["requests"] == 2


def test_poll_summary_falls_back_to_watermark_when_open_window_has_no_rows(
    cli_module,
    monkeypatch,
):
    class FallbackClient:
        def __init__(self):
            self.calls = []
            self.watermark_calls = 0

        def get_high_watermark(self):
            self.watermark_calls += 1
            return 12

        def get_run_summary(self, *, after_id, until_id=None):
            self.calls.append({"until_id": until_id})
            if until_id is None:
                return {
                    "window": {
                        "after_id": after_id,
                        "until_id": after_id,
                        "row_count": 0,
                    },
                    "summary": {"requests": 0},
                    "sessions": [],
                    "client_sources": [],
                    "models": [],
                }
            return {
                "window": {"after_id": after_id, "until_id": 11, "row_count": 1},
                "summary": {"requests": 1},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)
    client = FallbackClient()

    summary = cli_module.poll_summary(
        client,
        after_id=10,
        options=cli_module.RunOptions(wait_ms=0),
    )

    assert summary["summary"]["requests"] == 1
    assert client.watermark_calls == 1
    assert client.calls == [{"until_id": None}, {"until_id": 12}]


def test_write_json_summary_to_file(cli_module, tmp_path):
    target = tmp_path / "summary.json"
    summary = {
        "window": {"after_id": 1, "until_id": 2, "row_count": 1},
        "summary": {"requests": 1},
        "sessions": [],
        "client_sources": [],
        "models": [],
    }

    cli_module.write_summary(
        summary,
        cli_module.RunOptions(
            json_output=True,
            summary_dest="file",
            summary_file=str(target),
        ),
    )

    assert json.loads(target.read_text(encoding="utf-8"))["summary"]["requests"] == 1


def test_summary_write_failure_preserves_child_exit_code(
    cli_module, monkeypatch, capsys
):
    fake_client = FakeClient()

    def fake_run(command, env=None):
        return subprocess.CompletedProcess(command, 7)

    def fake_write_summary(summary, options):
        raise OSError("disk full")

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(cli_module, "write_summary", fake_write_summary)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        client=fake_client,
        options=cli_module.RunOptions(wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 7
    assert "llm-tracker summary output failed: disk full" in captured.err


def test_main_rejects_missing_summary_file_before_launch(
    cli_module, monkeypatch, capsys
):
    launched = False

    def fake_run_with_tracking(**kwargs):
        nonlocal launched
        launched = True
        return 0

    monkeypatch.setattr(cli_module, "run_with_tracking", fake_run_with_tracking)

    code = cli_module.main(["--summary-dest", "file", "--", "fake-command"])

    captured = capsys.readouterr()
    assert code == 2
    assert launched is False
    assert "--summary-file is required when --summary-dest=file" in captured.err


def test_run_command_maps_signal_return_code(cli_module, monkeypatch):
    fake_client = FakeClient()

    def fake_run(command, env=None):
        return subprocess.CompletedProcess(command, -15)

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        client=fake_client,
        options=cli_module.RunOptions(no_summary=True, wait_ms=0),
    )

    assert code == 143


def test_llm_tracker_script_exists_and_invokes_cli():
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "llm-tracker"

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "python" in content
    assert "-m" in content
    assert "src.cli" in content


def test_llm_tracker_script_invokes_cli_outside_repo_root(tmp_path):
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "llm-tracker"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [str(script)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "usage: llm-tracker [options] -- <command> [args...]" in result.stderr


def test_llm_tracker_script_tracks_child_with_http_api(isolated_home, tmp_path):
    from pathlib import Path

    class UsageApiHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            self.server.requests.append((parsed.path, parse_qs(parsed.query)))
            if parsed.path == "/usage/high-watermark":
                payload = {"id": 10}
            elif parsed.path == "/usage/run-summary":
                payload = {
                    "window": {"after_id": 10, "until_id": 11, "row_count": 1},
                    "summary": {
                        "requests": 1,
                        "successful_requests": 1,
                        "failed_requests": 0,
                        "prompt_tokens": 100,
                        "completion_tokens": 25,
                        "reasoning_tokens": 5,
                        "cached_tokens": 50,
                        "tool_tokens": 0,
                        "cache_creation_tokens": 0,
                        "total_tokens": 125,
                        "cache_hit_rate": 0.5,
                        "avg_latency_ms": 1000,
                        "avg_ttft_ms": 200,
                        "total_cost_usd": 0.12,
                    },
                    "sessions": [
                        {
                            "session_id": "conv-1",
                            "requests": 1,
                            "total_tokens": 125,
                            "cache_hit_rate": 0.5,
                            "total_cost_usd": 0.12,
                        }
                    ],
                    "client_sources": [],
                    "models": [],
                }
            else:
                self.send_response(404)
                self.end_headers()
                return

            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    try:
        server = http.server.HTTPServer(("127.0.0.1", 0), UsageApiHandler)
    except PermissionError:
        pytest.skip("local HTTP server binding is not permitted in this sandbox")
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api_port = server.server_address[1]

    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    config_path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 4999
  api_port: {api_port}
db:
  path: {isolated_home / "usage.db"}
models: {{}}
providers: {{}}
""",
        encoding="utf-8",
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "llm-tracker"
    env = os.environ.copy()
    env["HOME"] = str(isolated_home)
    env["LLM_TRACKER_CONFIG"] = str(config_path)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("OPENAI_BASE_URL", None)
    env.pop("ANTHROPIC_BASE_URL", None)
    env.pop("OTEL_RESOURCE_ATTRIBUTES", None)

    try:
        result = subprocess.run(
            [
                str(script),
                "--json",
                "--proxy-env",
                "--wait-ms",
                "0",
                "--",
                sys.executable,
                "-c",
                (
                    "import os; "
                    "print('child stdout'); "
                    "print(os.environ['OPENAI_BASE_URL']); "
                    "print(os.environ['ANTHROPIC_BASE_URL']); "
                    "print(os.environ.get('OTEL_RESOURCE_ATTRIBUTES', ''))"
                ),
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert result.returncode == 0
    stdout_lines = result.stdout.splitlines()
    assert len(stdout_lines) == 4
    assert stdout_lines == [
        "child stdout",
        "http://127.0.0.1:4999/v1",
        "http://127.0.0.1:4999",
        "",
    ]
    summary = json.loads(result.stderr)
    assert summary["summary"]["requests"] == 1
    assert summary["sessions"][0]["session_id"] == "conv-1"
    assert server.requests == [
        ("/usage/high-watermark", {}),
        ("/usage/run-summary", {"after_id": ["10"]}),
    ]
