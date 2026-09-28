"""``llm-tracker setup`` — the client owns agent configuration.

These tests run the real configure scripts, so they cover the whole path: the
client decides the endpoint, shells out, and the scripts write only their own
keys. The server scripts deliberately do not do this any more.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from client import auth, setup

ENDPOINT = "https://app.example.com/v1/logs"


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LLM_TRACKER_HOME", str(home / ".llm-tracker"))
    monkeypatch.delenv("LLM_TRACKER_ROOT", raising=False)
    monkeypatch.delenv("LLM_TRACKER_CONFIG", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
    monkeypatch.delenv("LLM_TRACKER_INGEST_TOKEN", raising=False)
    monkeypatch.setattr(
        setup.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"codex", "claude"} else None,
    )
    # An installed agent has its config directory. configure-codex-settings.py
    # deliberately refuses to create it.
    (home / ".codex").mkdir()
    (home / ".claude").mkdir()
    return home


def _sign_in(home: Path, endpoint: str = ENDPOINT) -> None:
    path = home / ".llm-tracker" / "credentials.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "server_url": "https://app.example.com",
                "email": "you@example.com",
                "cli_token": "llmt_cli_x",
                "ingest_token": "llmt_ingest_x",
                "otlp_logs_endpoint": endpoint,
            }
        ),
        encoding="utf-8",
    )


def test_setup_wires_detected_agents_at_the_signed_in_collector(
    machine: Path, capsys
) -> None:
    _sign_in(machine)
    assert setup.run_setup(disable=False) == 0
    out = capsys.readouterr().out
    assert f"collector   {ENDPOINT}" in out
    assert "wired       codex, claude" in out

    claude = json.loads((machine / ".claude" / "settings.json").read_text())
    assert claude["env"]["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == ENDPOINT
    # The token is required for an authenticated collector.
    assert (
        claude["env"]["OTEL_EXPORTER_OTLP_HEADERS"]
        == "x-llm-tracker-token=llmt_ingest_x"
    )

    codex = (machine / ".codex" / "config.toml").read_text()
    assert ENDPOINT in codex
    assert "llmt_ingest_x" in codex


def test_setup_is_idempotent(machine: Path) -> None:
    _sign_in(machine)
    assert setup.run_setup(disable=False) == 0
    claude_path = machine / ".claude" / "settings.json"
    first = claude_path.read_text()
    assert setup.run_setup(disable=False) == 0
    assert claude_path.read_text() == first


def test_setup_needs_a_collector(machine: Path, capsys) -> None:
    assert setup.run_setup(disable=False) == 1
    assert "No collector to wire agents to" in capsys.readouterr().err


def test_setup_uses_the_local_collector_when_the_server_is_installed(
    machine: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_root = machine / ".llm-tracker" / "src"
    (server_root / ".venv" / "bin").mkdir(parents=True)
    (server_root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
    (server_root / ".venv" / "bin" / "python").chmod(0o755)
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(server_root))
    (machine / ".llm-tracker" / "config.yaml").write_text(
        "server:\n  host: 127.0.0.1\n  otlp_port: 4102\n", encoding="utf-8"
    )
    assert setup.run_setup(disable=False) == 0
    assert "http://localhost:4102/v1/logs" in capsys.readouterr().out
    claude = json.loads((machine / ".claude" / "settings.json").read_text())
    assert claude["env"]["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == (
        "http://localhost:4102/v1/logs"
    )


def test_setup_disable_removes_only_our_keys(machine: Path, capsys) -> None:
    _sign_in(machine)
    settings = machine / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({"model": "opus", "env": {"MY_OWN": "keep"}}), encoding="utf-8"
    )
    assert setup.run_setup(disable=False) == 0
    assert setup.run_setup(disable=True) == 0
    assert "un-wired" in capsys.readouterr().out
    remaining = json.loads(settings.read_text())
    assert remaining == {"model": "opus", "env": {"MY_OWN": "keep"}}


def test_setup_disable_leaves_a_foreign_collector_alone(machine: Path, capsys) -> None:
    _sign_in(machine)
    settings = machine / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "env": {
                    "OTEL_LOGS_EXPORTER": "otlp",
                    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://other:9999/v1/logs",
                }
            }
        ),
        encoding="utf-8",
    )
    assert setup.run_setup(disable=True) == 0
    assert "left alone" in capsys.readouterr().err
    assert "http://other:9999/v1/logs" in settings.read_text()


def test_setup_with_no_agents_is_not_a_failure(machine: Path, capsys) -> None:
    monkeypatch_which = setup.shutil.which
    setup.shutil.which = lambda name: None
    try:
        assert setup.run_setup(disable=False) == 0
    finally:
        setup.shutil.which = monkeypatch_which
    assert "No tracked agents detected" in capsys.readouterr().out


def test_setup_strips_a_stale_local_otlp_override(
    machine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing OTEL override must not beat the endpoint we are wiring."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://stale:1/v1/logs")
    _sign_in(machine)
    assert setup.run_setup(disable=False) == 0
    claude = json.loads((machine / ".claude" / "settings.json").read_text())
    assert claude["env"]["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == ENDPOINT


def _sign_in_without_collector(home: Path) -> None:
    """A login made before the client started recording the collector."""
    path = home / ".llm-tracker" / "credentials.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "server_url": "https://app.example.com",
                "email": "you@example.com",
                "cli_token": "llmt_cli_x",
                "ingest_token": "llmt_ingest_x",
            }
        ),
        encoding="utf-8",
    )


def test_signed_in_client_asks_the_server_where_its_collector_is(
    machine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The OTLP port is not the API port, so only the server can say."""
    _sign_in_without_collector(machine)
    requested: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "protocol_min": 1,
                "protocol_max": 1,
                "otlp_logs_endpoint": ENDPOINT,
            }

    def fake_get(url, **kwargs):
        requested.append(url)
        return FakeResponse()

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    assert setup.run_setup(disable=False) == 0
    assert requested == ["https://app.example.com/version"]
    claude = json.loads((machine / ".claude" / "settings.json").read_text())
    assert claude["env"]["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == ENDPOINT
    # And the answer is remembered, so later commands need no network.
    remembered = json.loads(
        (machine / ".llm-tracker" / "credentials.json").read_text()
    )["otlp_logs_endpoint"]
    assert remembered == ENDPOINT
    monkeypatch.setattr(
        auth.httpx,
        "get",
        lambda *a, **k: pytest.fail("a remembered collector must not be looked up"),
    )
    assert auth.discover_collector() == ENDPOINT


def test_status_never_guesses_a_local_collector_when_signed_in_remotely(
    machine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A local fallback here would point agents away from their own server."""
    _sign_in_without_collector(machine)
    server_root = machine / ".llm-tracker" / "src"
    (server_root / ".venv" / "bin").mkdir(parents=True)
    (server_root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
    (server_root / ".venv" / "bin" / "python").chmod(0o755)
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(server_root))
    (machine / ".llm-tracker" / "config.yaml").write_text(
        "server:\n  host: 127.0.0.1\n  otlp_port: 4102\n", encoding="utf-8"
    )

    assert setup.intended_endpoint() is None

    # And setup refuses rather than wiring the local collector.
    monkeypatch.setattr(
        auth.httpx,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    assert setup.run_setup(disable=False) == 1
    assert not (machine / ".claude" / "settings.json").exists()


def test_logout_unwires_with_the_collector_it_recorded(
    machine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(machine)
    assert setup.run_setup(disable=False) == 0
    settings = machine / ".claude" / "settings.json"
    assert "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" in settings.read_text()

    assert auth.logout(keep_agents=False) == 0
    assert "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" not in settings.read_text()
    assert not (machine / ".llm-tracker" / "credentials.json").exists()
