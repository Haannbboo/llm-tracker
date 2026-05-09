from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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


def test_parse_usage_only_forces_stdout_and_quiet_child_without_json(cli_module):
    args = cli_module.parse_args(["--usage-only", "--", "codex", "exec", "hello"])
    options = cli_module.options_from_args(args)

    assert options.json_output is False
    assert options.summary_dest == "stdout"
    assert options.quiet_child_output is True
    assert args.command == ["codex", "exec", "hello"]


def test_parse_usage_only_with_json_outputs_json(cli_module):
    args = cli_module.parse_args(
        ["--usage-only", "--json", "--", "codex", "exec", "hello"]
    )
    options = cli_module.options_from_args(args)

    assert options.json_output is True
    assert options.summary_dest == "stdout"
    assert options.quiet_child_output is True
    assert args.command == ["codex", "exec", "hello"]


def test_main_rejects_usage_only_with_no_summary(cli_module, monkeypatch, capsys):
    launched = False

    def fake_run_with_tracking(**kwargs):
        nonlocal launched
        launched = True
        return 0

    monkeypatch.setattr(cli_module, "run_with_tracking", fake_run_with_tracking)

    code = cli_module.main(["--usage-only", "--no-summary", "--", "fake-command"])

    captured = capsys.readouterr()
    assert code == 2
    assert launched is False
    assert "--usage-only cannot be combined with --no-summary" in captured.err


def test_parse_json_only_is_not_supported_after_rename(cli_module):
    with pytest.raises(SystemExit) as exc:
        cli_module.parse_args(["--json-only", "--", "codex", "exec", "hello"])

    assert exc.value.code == 2


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


class FakeTempProcess:
    def poll(self):
        return None

    def terminate(self):
        return None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        return None


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


def test_run_with_isolated_tracking_summarizes_and_merges_run_db(
    cli_module, database_module, isolated_home, monkeypatch, capsys
):
    main_db = str(isolated_home / "main.db")
    database_module.init_db(main_db)
    monkeypatch.setitem(cli_module.CONFIG["db"], "url", f"sqlite:///{main_db}")

    started_services = []
    stopped_services = []
    run_db_urls = []
    child_envs = []

    def fake_start_temp_service(*, name, module, db_url):
        run_db_urls.append(db_url)
        port = 49153 if name == "otlp" else 49154
        service = cli_module.TempService(
            name=name, port=port, process=FakeTempProcess()
        )
        started_services.append((name, module, db_url))
        return service

    def fake_stop_temp_service(service):
        stopped_services.append(service.name)

    def fake_run(command, env=None):
        child_envs.append(env)
        run_db_url = run_db_urls[0]
        database_module.log_usage(
            database_module.Usage(
                ts="2026-05-03T18:00:00+00:00",
                provider="test-provider",
                model="test-model",
                client_source="claude-code",
                session_id="claude-session-1",
                endpoint="generate-otlp",
                prompt_tokens=10,
                prompt_length=100,
                completion_tokens=5,
                reasoning_tokens=0,
                cached_tokens=2,
                total_tokens=15,
                latency_ms=100,
                ttft_ms=20,
                tool_tokens=0,
                cache_creation_tokens=0,
                input_cost_usd=0.1,
                output_cost_usd=0.2,
                total_cost_usd=0.3,
                status=200,
                base_url_id=None,
            ),
            db_path=run_db_url,
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module, "start_temp_service", fake_start_temp_service)
    monkeypatch.setattr(cli_module, "stop_temp_service", fake_stop_temp_service)
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        options=cli_module.RunOptions(json_output=True, wait_ms=0),
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.err)
    main_summary = database_module.summarize_usage_window(after_id=0, db_path=main_db)

    assert code == 0
    assert summary["summary"]["requests"] == 1
    assert main_summary["summary"]["requests"] == 1
    assert child_envs[0]["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == (
        "http://127.0.0.1:49153/v1/logs"
    )
    assert "LLM_TRACKER_DB_URL" not in child_envs[0]
    assert started_services == [("otlp", "src.otlp", run_db_urls[0])]
    assert stopped_services == ["otlp"]


def test_isolated_tracking_starts_proxy_when_proxy_env_enabled(
    cli_module, database_module, isolated_home, monkeypatch, capsys
):
    main_db = str(isolated_home / "main.db")
    database_module.init_db(main_db)
    monkeypatch.setitem(cli_module.CONFIG["db"], "url", f"sqlite:///{main_db}")
    started = []
    child_envs = []

    def fake_start_temp_service(*, name, module, db_url):
        port = 49153 if name == "otlp" else 49154
        started.append((name, module, db_url))
        return cli_module.TempService(name=name, port=port, process=FakeTempProcess())

    def fake_run(command, env=None):
        child_envs.append(env)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module, "start_temp_service", fake_start_temp_service)
    monkeypatch.setattr(cli_module, "stop_temp_service", lambda service: None)
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        options=cli_module.RunOptions(json_output=True, wait_ms=0, proxy_env=True),
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.err)

    assert code == 0
    assert summary["summary"]["requests"] == 0
    assert [item[0] for item in started] == ["otlp", "proxy"]
    assert child_envs[0]["OPENAI_BASE_URL"] == "http://127.0.0.1:49154/v1"
    assert child_envs[0]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:49154"
    assert "LLM_TRACKER_DB_URL" not in child_envs[0]


def test_isolated_tracking_merges_usage_when_child_exits_nonzero(
    cli_module, database_module, isolated_home, monkeypatch, capsys
):
    main_db = str(isolated_home / "main.db")
    database_module.init_db(main_db)
    monkeypatch.setitem(cli_module.CONFIG["db"], "url", f"sqlite:///{main_db}")
    run_db_urls = []

    def fake_start_temp_service(*, name, module, db_url):
        run_db_urls.append(db_url)
        return cli_module.TempService(name=name, port=49153, process=FakeTempProcess())

    def fake_run(command, env=None):
        database_module.log_usage(
            database_module.Usage(
                ts="2026-05-03T18:01:00+00:00",
                provider="test-provider",
                model="test-model",
                client_source="claude-code",
                session_id="failed-child-session",
                endpoint="generate-otlp",
                prompt_tokens=20,
                prompt_length=200,
                completion_tokens=10,
                reasoning_tokens=0,
                cached_tokens=4,
                total_tokens=30,
                latency_ms=300,
                ttft_ms=40,
                tool_tokens=0,
                cache_creation_tokens=0,
                input_cost_usd=0.2,
                output_cost_usd=0.4,
                total_cost_usd=0.6,
                status=200,
                base_url_id=None,
            ),
            db_path=run_db_urls[0],
        )
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(cli_module, "start_temp_service", fake_start_temp_service)
    monkeypatch.setattr(cli_module, "stop_temp_service", lambda service: None)
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        options=cli_module.RunOptions(json_output=True, wait_ms=0),
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.err)
    main_summary = database_module.summarize_usage_window(after_id=0, db_path=main_db)

    assert code == 7
    assert summary["summary"]["requests"] == 1
    assert main_summary["summary"]["requests"] == 1


def test_isolated_tracking_merges_usage_written_during_service_shutdown(
    cli_module, database_module, isolated_home, monkeypatch, capsys
):
    main_db = str(isolated_home / "main.db")
    database_module.init_db(main_db)
    monkeypatch.setitem(cli_module.CONFIG["db"], "url", f"sqlite:///{main_db}")
    run_db_urls = []

    def fake_start_temp_service(*, name, module, db_url):
        run_db_urls.append(db_url)
        return cli_module.TempService(name=name, port=49153, process=FakeTempProcess())

    def fake_stop_temp_service(service):
        database_module.log_usage(
            database_module.Usage(
                ts="2026-05-03T18:02:00+00:00",
                provider="test-provider",
                model="test-model",
                client_source="claude-code",
                session_id="shutdown-flush-session",
                endpoint="generate-otlp",
                prompt_tokens=30,
                prompt_length=300,
                completion_tokens=15,
                reasoning_tokens=0,
                cached_tokens=6,
                total_tokens=45,
                latency_ms=400,
                ttft_ms=50,
                tool_tokens=0,
                cache_creation_tokens=0,
                input_cost_usd=0.3,
                output_cost_usd=0.6,
                total_cost_usd=0.9,
                status=200,
                base_url_id=None,
            ),
            db_path=run_db_urls[0],
        )

    def fake_run(command, env=None):
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module, "start_temp_service", fake_start_temp_service)
    monkeypatch.setattr(cli_module, "stop_temp_service", fake_stop_temp_service)
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        options=cli_module.RunOptions(json_output=True, wait_ms=0),
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.err)
    main_summary = database_module.summarize_usage_window(after_id=0, db_path=main_db)

    assert code == 0
    assert summary["summary"]["requests"] == 1
    assert summary["sessions"][0]["session_id"] == "shutdown-flush-session"
    assert main_summary["summary"]["requests"] == 1
    assert main_summary["sessions"][0]["session_id"] == "shutdown-flush-session"


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


def test_usage_only_writes_json_to_stdout_and_suppresses_child_output(
    cli_module, monkeypatch, capsys
):
    fake_client = FakeClient()
    run_kwargs = {}

    def fake_run(command, env=None, stdout=None, stderr=None):
        run_kwargs["stdout"] = stdout
        run_kwargs["stderr"] = stderr
        if stdout is not subprocess.DEVNULL:
            print("child stdout")
        if stderr is not subprocess.DEVNULL:
            print("child stderr", file=sys.stderr)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: None)

    code = cli_module.run_with_tracking(
        command=["fake-command"],
        client=fake_client,
        options=cli_module.RunOptions(
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


def test_build_child_command_overrides_codex_exec_otlp_endpoint(cli_module):
    command = ["codex", "exec", "say hello"]

    tracked = cli_module.build_child_command(
        command,
        otlp_logs_endpoint="http://127.0.0.1:49153/v1/logs",
    )

    assert tracked == [
        "codex",
        "-c",
        'otel.exporter.otlp-http.endpoint="http://127.0.0.1:49153/v1/logs"',
        "-c",
        'otel.exporter.otlp-http.protocol="json"',
        "exec",
        "say hello",
    ]


def test_build_child_command_leaves_non_codex_commands_unchanged(cli_module):
    command = ["fake-command", "--flag"]

    tracked = cli_module.build_child_command(
        command,
        otlp_logs_endpoint="http://127.0.0.1:49153/v1/logs",
    )

    assert tracked == command


def test_build_service_env_sets_db_override_without_mutating_child_env(
    cli_module, monkeypatch
):
    monkeypatch.setenv("LLM_TRACKER_DB_URL", "sqlite:///main-should-not-leak.db")
    service_env = cli_module.build_service_env("sqlite:///run.db")
    child_env = cli_module.build_child_env(
        cli_module.RunOptions(proxy_env=True),
        proxy_base_urls=("http://127.0.0.1:49152/v1", "http://127.0.0.1:49152"),
        otlp_logs_endpoint="http://127.0.0.1:49153/v1/logs",
    )

    assert service_env["LLM_TRACKER_DB_URL"] == "sqlite:///run.db"
    assert "LLM_TRACKER_DB_URL" not in child_env
    assert child_env["OPENAI_BASE_URL"] == "http://127.0.0.1:49152/v1"
    assert child_env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:49152"
    assert child_env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == (
        "http://127.0.0.1:49153/v1/logs"
    )


def test_database_usage_client_summarizes_usage(
    cli_module, database_module, isolated_home
):
    db_url = f"sqlite:///{isolated_home / 'run.db'}"
    database_module.init_db(db_url)
    client = cli_module.DatabaseUsageClient(db_url)

    database_module.log_usage(
        database_module.Usage(
            ts="2026-05-03T18:00:00+00:00",
            provider="test-provider",
            model="test-model",
            client_source="codex",
            session_id="codex-session-1",
            endpoint="generate-otlp",
            prompt_tokens=10,
            prompt_length=0,
            completion_tokens=5,
            reasoning_tokens=1,
            cached_tokens=2,
            total_tokens=15,
            latency_ms=100,
            ttft_ms=20,
            tool_tokens=None,
            cache_creation_tokens=None,
            input_cost_usd=0.1,
            output_cost_usd=0.2,
            total_cost_usd=0.3,
            status=200,
            base_url_id=None,
        ),
        db_path=db_url,
    )

    summary = client.get_run_summary(after_id=0)

    assert client.get_high_watermark() == 1
    assert summary["summary"]["requests"] == 1
    assert summary["sessions"][0]["session_id"] == "codex-session-1"


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


def test_run_command_bounds_summary_after_wait(
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


def test_dev_scripts_live_under_scripts_dev():
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"

    assert not (scripts_dir / "dev-start.sh").exists()
    assert not (scripts_dir / "dev-stop.sh").exists()
    assert (scripts_dir / "dev" / "dev-start.sh").exists()
    assert (scripts_dir / "dev" / "dev-stop.sh").exists()


def test_llm_tracker_script_exists_and_invokes_cli():
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "llm-tracker"

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "python" in content
    assert "-m" in content
    assert "src.cli" in content


def test_llm_tracker_script_supports_bootstrap_subcommand():
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "llm-tracker"
    content = script.read_text(encoding="utf-8")

    assert "bootstrap)" in content
    assert 'exec bash "${SCRIPTS_DIR}/bootstrap.sh" "$@"' in content


def test_install_symlinks_llm_tracker_cli_into_user_local_bin():
    from pathlib import Path

    install_script = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"
    content = install_script.read_text(encoding="utf-8")

    assert 'BIN_DIR="${HOME}/.local/bin"' in content
    assert 'CLI_LINK="${BIN_DIR}/llm-tracker"' in content
    assert 'CLI_SOURCE="${ROOT_DIR}/scripts/llm-tracker"' in content
    assert 'ln -sf "${CLI_SOURCE}" "${CLI_LINK}"' in content


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


def test_llm_tracker_script_injects_isolated_otlp_env_without_db_leak(
    isolated_home, tmp_path
):
    from pathlib import Path

    config_path = isolated_home / ".llm-tracker" / "config.yaml"
    config_path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 4999
  api_port: 4998
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
    env["LLM_TRACKER_DB_URL"] = "sqlite:///should-not-leak.db"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    try:
        result = subprocess.run(
            [
                str(script),
                "--json",
                "--wait-ms",
                "0",
                "--",
                sys.executable,
                "-c",
                (
                    "import os; "
                    "print(os.environ.get('LLM_TRACKER_DB_URL', '')); "
                    "print(os.environ.get('OTEL_EXPORTER_OTLP_LOGS_ENDPOINT', ''))"
                ),
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
        )
    except PermissionError:
        pytest.skip("local process or HTTP binding is not permitted in this sandbox")

    assert result.returncode == 0
    stdout_lines = result.stdout.splitlines()
    assert stdout_lines[0] == ""
    assert stdout_lines[1].startswith("http://127.0.0.1:")
    assert stdout_lines[1].endswith("/v1/logs")
    summary = json.loads(result.stderr)
    assert summary["summary"]["requests"] == 0
