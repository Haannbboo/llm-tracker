"""``llm-tracker status`` — the component report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from client import setup, status


@pytest.fixture
def tracker_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tracker home with no server, no credentials and no agents."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LLM_TRACKER_HOME", str(home / ".llm-tracker"))
    monkeypatch.delenv("LLM_TRACKER_ROOT", raising=False)
    monkeypatch.delenv("LLM_TRACKER_CONFIG", raising=False)
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    return home


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_status_on_a_bare_client_only_machine(tracker_home: Path, capsys) -> None:
    code = status.run_status(as_json=False)
    out = capsys.readouterr().out
    # Not being signed in is a fact, not a fault: nothing installed is broken.
    assert code == 0
    assert "not signed in" in out
    assert "run llm-tracker login --server <url>" in out
    assert "services" not in out  # no server component, so no service rows
    assert "dashboard" not in out


def test_status_json_shape(tracker_home: Path, capsys) -> None:
    status.run_status(as_json=True)
    data = json.loads(capsys.readouterr().out.strip())
    assert data["client"]["version"]
    assert "commit" in data["client"]
    assert data["server"] == {"installed": False}
    assert data["account"]["signed_in"] is False
    assert data["dashboard"] is None
    assert [agent["name"] for agent in data["agents"]] == [
        "codex",
        "claude",
        "opencode",
        "kilo",
    ]
    assert all(agent["detected"] is False for agent in data["agents"])


def test_status_reports_a_signed_in_client(
    tracker_home: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials = tracker_home / ".llm-tracker" / "credentials.json"
    _write(
        credentials,
        json.dumps(
            {
                "server_url": "https://app.example.com",
                "email": "you@example.com",
                "device_name": "hanbo-macbook",
                "cli_token": "llmt_cli_x",
                "otlp_logs_endpoint": "https://app.example.com/v1/logs",
            }
        ),
    )
    assert status.run_status(as_json=False) == 0
    out = capsys.readouterr().out
    assert "signed in as you@example.com → https://app.example.com" in out
    assert "hanbo-macbook" in out  # device is only shown without a server
    assert "not signed in" not in out


def test_status_reports_agents_pointing_at_the_wrong_collector(
    tracker_home: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        setup.shutil,
        "which",
        lambda name: "/usr/bin/claude" if name == "claude" else None,
    )
    _write(
        tracker_home / ".llm-tracker" / "credentials.json",
        json.dumps(
            {
                "server_url": "https://app.example.com",
                "email": "you@example.com",
                "cli_token": "llmt_cli_x",
                "otlp_logs_endpoint": "https://app.example.com/v1/logs",
            }
        ),
    )
    _write(
        tracker_home / ".claude" / "settings.json",
        json.dumps(
            {
                "env": {
                    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                    "OTEL_LOGS_EXPORTER": "otlp",
                    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://elsewhere:4005/v1/logs",
                }
            }
        ),
    )
    assert status.run_status(as_json=False) == 1
    out = capsys.readouterr().out
    assert "wrong collector" in out
    assert "run llm-tracker setup" in out


def test_status_lists_wired_agents_with_their_collector(
    tracker_home: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        setup.shutil,
        "which",
        lambda name: "/usr/bin/claude" if name == "claude" else None,
    )
    _write(
        tracker_home / ".llm-tracker" / "credentials.json",
        json.dumps(
            {
                "server_url": "https://app.example.com",
                "email": "you@example.com",
                "cli_token": "llmt_cli_x",
                "otlp_logs_endpoint": "https://app.example.com/v1/logs",
            }
        ),
    )
    _write(
        tracker_home / ".claude" / "settings.json",
        json.dumps(
            {
                "env": {
                    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                    "OTEL_LOGS_EXPORTER": "otlp",
                    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://app.example.com/v1/logs",
                }
            }
        ),
    )
    assert status.run_status(as_json=False) == 0
    out = capsys.readouterr().out
    assert "claude → https://app.example.com/v1/logs" in out


def test_status_reports_stopped_server_services(
    tracker_home: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_root = tracker_home / ".llm-tracker" / "src"
    (server_root / ".venv" / "bin").mkdir(parents=True)
    (server_root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
    (server_root / ".venv" / "bin" / "python").chmod(0o755)
    (server_root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(server_root))
    _write(
        tracker_home / ".llm-tracker" / "config.yaml",
        "server:\n  host: 127.0.0.1\n  port: 4000\n  api_port: 4001\n  otlp_port: 4002\n",
    )
    monkeypatch.setattr(status, "_supervisor_running", lambda program, root: False)
    monkeypatch.setattr(
        status, "_port_listening", lambda host, port, timeout=1.0: False
    )

    assert status.run_status(as_json=False) == 1
    out = capsys.readouterr().out
    assert "server 9.9.9 (self-hosted)" in out
    assert "proxy :4000 down" in out
    assert "api :4001 down" in out
    assert "otlp :4002 down" in out
    assert "run llm-tracker server start" in out


def test_status_reports_running_server_services(
    tracker_home: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_root = tracker_home / ".llm-tracker" / "src"
    (server_root / ".venv" / "bin").mkdir(parents=True)
    (server_root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
    (server_root / ".venv" / "bin" / "python").chmod(0o755)
    (server_root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(server_root))
    _write(
        tracker_home / ".llm-tracker" / "config.yaml",
        "server:\n  host: 127.0.0.1\n  port: 4000\n  api_port: 4001\n  otlp_port: 4002\n",
    )
    monkeypatch.setattr(status, "_supervisor_running", lambda program, root: True)
    monkeypatch.setattr(status, "_port_listening", lambda host, port, timeout=1.0: True)

    assert status.run_status(as_json=False) == 0
    out = capsys.readouterr().out
    assert "proxy :4000 up · api :4001 up · otlp :4002 up" in out
    assert "dashboard   http://localhost:4001" in out
    assert "fix" not in out


def test_status_supervision_alone_is_not_enough(
    tracker_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A RUNNING supervisord program whose port is dead is not up."""
    server_root = tracker_home / ".llm-tracker" / "src"
    (server_root / ".venv" / "bin").mkdir(parents=True)
    (server_root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
    (server_root / ".venv" / "bin" / "python").chmod(0o755)
    (server_root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(server_root))
    monkeypatch.setattr(status, "_supervisor_running", lambda program, root: True)
    monkeypatch.setattr(
        status, "_port_listening", lambda host, port, timeout=1.0: False
    )
    data = status.collect()
    assert [service["state"] for service in data["server"]["services"]] == [
        "down",
        "down",
        "down",
    ]
    assert status.is_healthy(data) is False


def test_unknown_collector_is_not_reported_as_broken(
    tracker_home: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A machine that signed in before its server published a collector cannot
    tell whether an agent is right, so it must not call the agent broken."""
    monkeypatch.setattr(
        setup.shutil,
        "which",
        lambda name: "/usr/bin/claude" if name == "claude" else None,
    )
    _write(
        tracker_home / ".llm-tracker" / "credentials.json",
        json.dumps(
            {
                "server_url": "https://app.example.com",
                "email": "you@example.com",
                "cli_token": "llmt_cli_x",
            }
        ),
    )
    _write(
        tracker_home / ".claude" / "settings.json",
        json.dumps(
            {
                "env": {
                    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                    "OTEL_LOGS_EXPORTER": "otlp",
                    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://app.example.com/v1/logs",
                }
            }
        ),
    )
    assert status.run_status(as_json=False) == 0
    out = capsys.readouterr().out
    assert "(target unknown)" in out
    assert "wrong collector" not in out
    assert "none wired" not in out
    # It is still actionable: setup is what discovers the collector.
    assert "run llm-tracker setup" in out

    data = status.collect()
    claude = next(agent for agent in data["agents"] if agent["name"] == "claude")
    assert claude["endpoint_matches"] is None
    assert claude["configured"] is True
