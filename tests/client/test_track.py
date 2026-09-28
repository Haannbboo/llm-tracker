"""The tracking wrapper: args in, one usage summary out.

Isolated tracking is gone. Every run reads the high-watermark from the collector
that is already running, so there is no scratch service to start or merge.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from client import cli as client_cli
from client import track


class FakeClient:
    def __init__(self):
        self.before_calls = 0
        self.summary_calls = []

    def get_high_watermark(self):
        self.before_calls += 1
        return 10

    def get_run_summary(self, *, after_ts, until_ts=None):
        self.summary_calls.append({"after_ts": after_ts, "until_ts": until_ts})
        return {
            "window": {"after_ts": after_ts, "until_ts": 11, "row_count": 1},
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


@pytest.fixture
def fake_client(monkeypatch):
    """Every run builds its own client, so patch the constructor, not an arg."""
    client = FakeClient()
    monkeypatch.setattr(track, "UsageApiClient", lambda: client)
    return client


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(track.time, "sleep", lambda seconds: None)


def _options(argv: list[str]) -> track.RunOptions:
    args = client_cli._build_wrapper_parser().parse_args(argv)
    return track.options_from_args(args)


# ----------------------------------------------------------------- arguments


@pytest.mark.parametrize(
    ("argv", "expected", "expected_json"),
    [
        (
            ["--json", "--", "codex", "-m", "gpt-test"],
            ["codex", "-m", "gpt-test"],
            True,
        ),
        (
            ["claude", "--dangerously-skip-permissions"],
            ["claude", "--dangerously-skip-permissions"],
            False,
        ),
    ],
)
def test_main_passes_the_remaining_arguments_as_the_tracked_command(
    monkeypatch, argv, expected, expected_json
):
    seen = {}

    def fake_run_with_tracking(*, command, options):
        seen["command"] = command
        seen["json_output"] = options.json_output
        return 0

    monkeypatch.setattr(client_cli.track, "run_with_tracking", fake_run_with_tracking)

    assert client_cli.main(argv) == 0
    assert seen["command"] == expected
    assert seen["json_output"] is expected_json


def test_default_wait_time_is_three_seconds():
    assert _options(["codex"]).wait_ms == 3000


def test_usage_only_forces_stdout_and_quiet_child_without_json():
    options = _options(["--usage-only", "--", "codex", "exec", "hello"])

    assert options.json_output is False
    assert options.summary_dest == "stdout"
    assert options.quiet_child_output is True


def test_usage_only_with_json_outputs_json():
    options = _options(["--usage-only", "--json", "--", "codex", "exec", "hello"])

    assert options.json_output is True
    assert options.summary_dest == "stdout"
    assert options.quiet_child_output is True


def test_main_rejects_usage_only_with_no_summary(monkeypatch, capsys):
    launched = False

    def fake_run_with_tracking(**kwargs):
        nonlocal launched
        launched = True
        return 0

    monkeypatch.setattr(client_cli.track, "run_with_tracking", fake_run_with_tracking)

    code = client_cli.main(["--usage-only", "--no-summary", "--", "fake-command"])

    captured = capsys.readouterr()
    assert code == 2
    assert launched is False
    assert "--usage-only cannot be combined with --no-summary" in captured.err


def test_main_rejects_missing_summary_file_before_launch(monkeypatch, capsys):
    launched = False

    def fake_run_with_tracking(**kwargs):
        nonlocal launched
        launched = True
        return 0

    monkeypatch.setattr(client_cli.track, "run_with_tracking", fake_run_with_tracking)

    code = client_cli.main(["--summary-dest", "file", "--", "fake-command"])

    captured = capsys.readouterr()
    assert code == 2
    assert launched is False
    assert "--summary-file is required when --summary-dest=file" in captured.err


# ------------------------------------------------------------- child plumbing


def test_child_output_kwargs_only_quietens_when_asked():
    assert track.child_output_kwargs(track.RunOptions()) == {}
    assert track.child_output_kwargs(track.RunOptions(quiet_child_output=True)) == {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }


def test_build_child_env_returns_none_without_proxy_env(monkeypatch):
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=test-agent")

    env = track.build_child_env(track.RunOptions())

    assert env is None


def test_build_child_env_points_at_the_local_proxy_without_overwriting(
    monkeypatch,
):
    monkeypatch.setattr(
        track, "local_server_info", lambda: {"proxy_url": "http://localhost:4999"}
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://existing.example/v1")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    env = track.build_child_env(track.RunOptions(proxy_env=True))

    assert env["OPENAI_BASE_URL"] == "https://existing.example/v1"
    assert env["ANTHROPIC_BASE_URL"] == "http://localhost:4999"
    assert "OTEL_RESOURCE_ATTRIBUTES" not in env


def test_build_child_env_does_not_leak_the_db_override(monkeypatch):
    monkeypatch.setattr(
        track, "local_server_info", lambda: {"proxy_url": "http://localhost:49152"}
    )
    monkeypatch.setenv("LLM_TRACKER_DB_URL", "sqlite:///main-should-not-leak.db")

    env = track.build_child_env(track.RunOptions(proxy_env=True))

    assert env["OPENAI_BASE_URL"] == "http://localhost:49152/v1"
    assert env["ANTHROPIC_BASE_URL"] == "http://localhost:49152"
    assert "LLM_TRACKER_DB_URL" not in env


# ----------------------------------------------------------------- api client


def test_api_client_passes_until_ts_query_param(monkeypatch):
    captured = {}
    client = track.UsageApiClient(base_url="http://example.test")

    def fake_get_json(path, *, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"summary": {"requests": 0}}

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    client.get_run_summary(after_ts=10, until_ts=12)

    assert captured == {
        "path": "/usage/run-summary",
        "params": {"after_ts": 10, "until_ts": 12},
    }


def test_high_watermark_malformed_response_raises_api_error(monkeypatch):
    client = track.UsageApiClient(base_url="http://example.test")
    monkeypatch.setattr(client, "_get_json", lambda path: {"missing": "ts"})

    with pytest.raises(track.ApiError):
        client.get_high_watermark()


# ------------------------------------------------------------------ polling


def test_poll_summary_waits_until_deadline_for_later_run_rows(monkeypatch):
    class DelayedClient:
        def __init__(self):
            self.requests = [1, 2]

        def get_run_summary(self, *, after_ts, until_ts=None):
            requests = self.requests.pop(0)
            return {
                "window": {
                    "after_ts": after_ts,
                    "until_ts": 10 + requests,
                    "row_count": requests,
                },
                "summary": {"requests": requests},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

    monotonic_values = [0.0, 0.1, 0.4]
    monkeypatch.setattr(track.time, "monotonic", lambda: monotonic_values.pop(0))
    monkeypatch.setattr(track.time, "sleep", lambda seconds: None)

    summary = track.poll_summary(
        DelayedClient(),
        after_ts=10,
        options=track.RunOptions(wait_ms=300),
    )

    assert summary["summary"]["requests"] == 2


def test_poll_summary_falls_back_to_watermark_when_open_window_has_no_rows(
    monkeypatch,
):
    class FallbackClient:
        def __init__(self):
            self.calls = []
            self.watermark_calls = 0

        def get_high_watermark(self):
            self.watermark_calls += 1
            return 12

        def get_run_summary(self, *, after_ts, until_ts=None):
            self.calls.append({"until_ts": until_ts})
            if until_ts is None:
                return {
                    "window": {
                        "after_ts": after_ts,
                        "until_ts": after_ts,
                        "row_count": 0,
                    },
                    "summary": {"requests": 0},
                    "sessions": [],
                    "client_sources": [],
                    "models": [],
                }
            return {
                "window": {"after_ts": after_ts, "until_ts": 11, "row_count": 1},
                "summary": {"requests": 1},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

    monkeypatch.setattr(track.time, "sleep", lambda seconds: None)
    client = FallbackClient()

    summary = track.poll_summary(
        client,
        after_ts=10,
        options=track.RunOptions(wait_ms=0),
    )

    assert summary["summary"]["requests"] == 1
    assert client.watermark_calls == 1
    assert client.calls == [{"until_ts": None}, {"until_ts": 12}]


def test_poll_summary_surfaces_api_error(capsys):
    class RejectingClient:
        def get_run_summary(self, **kwargs):
            raise track.ApiError("session rejected — run llm-tracker login")

    result = track.poll_summary(
        RejectingClient(),
        after_ts=0,
        options=track.RunOptions(wait_ms=0),
    )

    assert result is None
    assert "llm-tracker login" in capsys.readouterr().err


# ----------------------------------------------------------------- run + exit


def test_run_command_preserves_child_exit_code(
    fake_client, no_sleep, monkeypatch, capsys
):
    calls = {}

    def fake_run(command, env=None):
        calls["command"] = command
        calls["env"] = env
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(track.subprocess, "run", fake_run)

    code = track.run_with_tracking(
        command=["fake-command", "--flag"],
        options=track.RunOptions(wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 7
    assert calls["command"] == ["fake-command", "--flag"]
    assert calls["env"] is None
    assert fake_client.before_calls == 1
    assert fake_client.summary_calls == [{"after_ts": 10, "until_ts": None}]
    assert "requests: 1" in captured.err


def test_run_command_handles_unavailable_api_before_child(monkeypatch, capsys):
    class BrokenClient:
        def get_high_watermark(self):
            raise track.ApiError("api down")

    monkeypatch.setattr(track, "UsageApiClient", lambda: BrokenClient())
    monkeypatch.setattr(
        track.subprocess,
        "run",
        lambda command, env=None: subprocess.CompletedProcess(command, 0),
    )

    code = track.run_with_tracking(
        command=["fake-command"],
        options=track.RunOptions(wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "llm-tracker API unavailable before command start" in captured.err
    assert "No summary could be produced." in captured.err


def test_run_command_reports_a_rejected_session(monkeypatch, capsys):
    class RejectedClient:
        def get_high_watermark(self):
            raise track.ApiError("session rejected — run llm-tracker login")

    monkeypatch.setattr(track, "UsageApiClient", lambda: RejectedClient())
    monkeypatch.setattr(
        track.subprocess,
        "run",
        lambda command, env=None: subprocess.CompletedProcess(command, 0),
    )

    code = track.run_with_tracking(
        command=["fake-cmd"],
        options=track.RunOptions(no_summary=True),
    )

    assert code == 0
    assert "llm-tracker login" in capsys.readouterr().err


def test_json_summary_defaults_to_stderr(fake_client, no_sleep, monkeypatch, capsys):
    def fake_run(command, env=None):
        print("child stdout")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(track.subprocess, "run", fake_run)

    code = track.run_with_tracking(
        command=["fake-command"],
        options=track.RunOptions(json_output=True, wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "child stdout\n"
    parsed = json.loads(captured.err)
    assert parsed["summary"]["requests"] == 1


def test_usage_only_writes_json_to_stdout_and_suppresses_child_output(
    fake_client, no_sleep, monkeypatch, capsys
):
    run_kwargs = {}

    def fake_run(command, env=None, stdout=None, stderr=None):
        run_kwargs["stdout"] = stdout
        run_kwargs["stderr"] = stderr
        if stdout is not subprocess.DEVNULL:
            print("child stdout")
        if stderr is not subprocess.DEVNULL:
            print("child stderr", file=sys.stderr)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(track.subprocess, "run", fake_run)

    code = track.run_with_tracking(
        command=["fake-command"],
        options=track.RunOptions(
            json_output=True,
            summary_dest="stdout",
            quiet_child_output=True,
            wait_ms=0,
        ),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert run_kwargs == {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    parsed = json.loads(captured.out)
    assert parsed["summary"]["requests"] == 1
    assert captured.err == ""


def test_no_summary_skips_summary_call(fake_client, monkeypatch, capsys):
    monkeypatch.setattr(
        track.subprocess,
        "run",
        lambda command, env=None: subprocess.CompletedProcess(command, 3),
    )

    code = track.run_with_tracking(
        command=["fake-command"],
        options=track.RunOptions(no_summary=True, wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 3
    assert fake_client.before_calls == 1
    assert fake_client.summary_calls == []
    assert captured.out == ""
    assert captured.err == ""


def test_run_command_maps_signal_return_code(fake_client, monkeypatch):
    monkeypatch.setattr(
        track.subprocess,
        "run",
        lambda command, env=None: subprocess.CompletedProcess(command, -15),
    )

    code = track.run_with_tracking(
        command=["fake-command"],
        options=track.RunOptions(no_summary=True, wait_ms=0),
    )

    assert code == 143


def test_run_command_bounds_summary_after_wait(fake_client, no_sleep, monkeypatch):
    class FallbackClient:
        def __init__(self):
            self.watermarks = [10, 12]
            self.summary_calls = []
            self.events = []

        def get_high_watermark(self):
            self.events.append("watermark")
            return self.watermarks.pop(0)

        def get_run_summary(self, *, after_ts, until_ts=None):
            self.events.append(f"summary:{until_ts or 'open'}")
            self.summary_calls.append({"after_ts": after_ts, "until_ts": until_ts})
            if until_ts is None:
                return {
                    "window": {
                        "after_ts": after_ts,
                        "until_ts": after_ts,
                        "row_count": 0,
                    },
                    "summary": {"requests": 0},
                    "sessions": [],
                    "client_sources": [],
                    "models": [],
                }
            return {
                "window": {"after_ts": after_ts, "until_ts": until_ts, "row_count": 1},
                "summary": {"requests": 1},
                "sessions": [],
                "client_sources": [],
                "models": [],
            }

    monkeypatch.setattr(
        track.subprocess,
        "run",
        lambda command, env=None: subprocess.CompletedProcess(command, 0),
    )
    client = FallbackClient()
    monkeypatch.setattr(track, "UsageApiClient", lambda: client)

    code = track.run_with_tracking(
        command=["fake-command"],
        options=track.RunOptions(wait_ms=0),
    )

    assert code == 0
    assert client.summary_calls == [
        {"after_ts": 10, "until_ts": None},
        {"after_ts": 10, "until_ts": 12},
    ]
    assert client.events == [
        "watermark",
        "summary:open",
        "watermark",
        "summary:12",
    ]


# ------------------------------------------------------------------- writing


def test_write_json_summary_to_file(tmp_path):
    target = tmp_path / "summary.json"
    summary = {
        "window": {"after_ts": 1, "until_ts": 2, "row_count": 1},
        "summary": {"requests": 1},
        "sessions": [],
        "client_sources": [],
        "models": [],
    }

    track.write_summary(
        summary,
        track.RunOptions(
            json_output=True,
            summary_dest="file",
            summary_file=str(target),
        ),
    )

    assert json.loads(target.read_text(encoding="utf-8"))["summary"]["requests"] == 1


def test_format_human_summary_reports_nothing_recorded():
    assert (
        track.format_human_summary({"summary": {"requests": 0}})
        == "No llm-tracker usage recorded for this command.\n"
    )


def test_format_human_summary_groups_by_session():
    rendered = track.format_human_summary(
        {
            "summary": {
                "requests": 2,
                "total_tokens": 1250,
                "cached_tokens": 500,
                "cache_hit_rate": 0.4,
                "avg_latency_ms": 1500,
                "avg_ttft_ms": None,
                "total_cost_usd": 0.1234,
            },
            "sessions": [
                {
                    "session_id": "sess-1",
                    "requests": 2,
                    "total_tokens": 1250,
                    "cache_hit_rate": 0.4,
                    "total_cost_usd": 0.1234,
                }
            ],
        }
    )

    assert "requests: 2, total tokens: 1,250, cached: 500 (40%)" in rendered
    assert "latency avg: 1.50s, ttft avg: n/a, cost: $0.1234" in rendered
    assert "sess-1  2 req  1,250 tok  40% cached  $0.1234" in rendered


def test_format_ms_scales_to_seconds():
    assert track._format_ms(None) == "n/a"
    assert track._format_ms(250) == "250ms"
    assert track._format_ms(1500) == "1.50s"


def test_summary_write_failure_preserves_child_exit_code(
    fake_client, no_sleep, monkeypatch, capsys
):
    monkeypatch.setattr(
        track.subprocess,
        "run",
        lambda command, env=None: subprocess.CompletedProcess(command, 7),
    )

    def fake_write_summary(summary, options):
        raise OSError("disk full")

    monkeypatch.setattr(track, "write_summary", fake_write_summary)

    code = track.run_with_tracking(
        command=["fake-command"],
        options=track.RunOptions(wait_ms=0),
    )

    captured = capsys.readouterr()
    assert code == 7
    assert "llm-tracker summary output failed: disk full" in captured.err
