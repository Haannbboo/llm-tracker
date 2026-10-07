"""The per-device client service and its health payload.

These are the tests that used to live in ``tests/test_local_setup_health.py``:
agent detection and wiring now belong to the client, not the server.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from client import cli, service, setup

REPO_ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "http://localhost:4002/v1/logs"


@pytest.fixture
def device_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A device home with a recorded collector and no detected agents."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TOKENAGE_HOME", str(home / ".tokenage"))
    monkeypatch.setenv("TOKENAGE_CLIENT_COMMIT", "a" * 40)
    monkeypatch.delenv("TOKENAGE_ROOT", raising=False)
    monkeypatch.delenv("TOKENAGE_SERVER_ROOT", raising=False)
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    _write_json(
        home / ".tokenage" / "credentials.json",
        {"otlp_logs_endpoint": ENDPOINT},
    )
    return home


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data) -> None:
    _write(path, json.dumps(data))


def _claude_env(endpoint: str | None, **extra: str) -> str:
    env = {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_LOGS_EXPORTER": "otlp",
        "API_KEY": "super-secret",
        **extra,
    }
    if endpoint is not None:
        env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = endpoint
    return json.dumps({"env": env})


def test_health_reports_agent_otlp_config_status(
    device_home: Path,
) -> None:
    _write(device_home / ".claude" / "settings.json", _claude_env(ENDPOINT))
    _write(
        device_home / ".codex" / "config.toml",
        """[otel]
enabled = true
[otel.exporter.otlp-http]
endpoint = "http://localhost:9999/v1/logs"
protocol = "json"
api_key = "super-secret"
""",
    )

    payload = service.health_payload()

    assert payload["expected"]["otlp_logs_endpoint"] == ENDPOINT
    assert payload["expected"]["otlp_endpoint"] == "http://localhost:4002"
    assert payload["summary"] == {
        "total_agents": 4,
        "configured_agents": 2,
        "matching_agents": 1,
    }

    agents = payload["agents"]
    assert agents["claude"]["configured"] is True
    assert agents["claude"]["endpoint_matches"] is True
    assert agents["claude"]["configured_endpoint"] == ENDPOINT
    assert agents["codex"]["configured"] is True
    assert agents["codex"]["endpoint_matches"] is False
    assert agents["codex"]["configured_endpoint"] == "http://localhost:9999/v1/logs"
    assert agents["kilo"]["status"] == "missing_config"
    assert agents["kilo"]["configured"] is False
    assert agents["kilo"]["configured_endpoint"] is None
    assert agents["kilo"]["endpoint_matches"] is False
    assert "gemini" not in agents

    text = json.dumps(payload)
    assert "super-secret" not in text
    assert "api_key" not in text.lower()


def test_health_accepts_codex_otlp_http_enabled(device_home: Path) -> None:
    _write(
        device_home / ".codex" / "config.toml",
        """[otel]
environment = "dev"
[otel.exporter]
[otel.exporter.otlp-http]
endpoint = "http://localhost:4002/v1/logs"
enabled = true
api_key = "super-secret"
""",
    )

    payload = service.health_payload()

    assert payload["summary"]["configured_agents"] == 1
    assert payload["summary"]["matching_agents"] == 1
    assert payload["agents"]["codex"]["configured"] is True
    assert payload["agents"]["codex"]["endpoint_matches"] is True
    assert payload["agents"]["codex"]["configured_endpoint"] == ENDPOINT
    assert "super-secret" not in json.dumps(payload)


def test_health_accepts_codex_endpoint_only_otlp_http_config(
    device_home: Path,
) -> None:
    _write(
        device_home / ".codex" / "config.toml",
        """[otel]
environment = "dev"

[otel.exporter]
[otel.exporter.otlp-http]
endpoint = "http://localhost:4002/v1/logs"
protocol = "json"

[plugins."superpowers@openai-curated"]
enabled = true
""",
    )

    payload = service.health_payload()

    assert payload["summary"]["configured_agents"] == 1
    assert payload["summary"]["matching_agents"] == 1
    assert payload["agents"]["codex"]["configured"] is True
    assert payload["agents"]["codex"]["endpoint_matches"] is True


def test_health_rejects_codex_otel_explicit_false(device_home: Path) -> None:
    _write(
        device_home / ".codex" / "config.toml",
        """[otel]
enabled = false

[otel.exporter.otlp-http]
endpoint = "http://localhost:4002/v1/logs"
protocol = "json"
""",
    )

    payload = service.health_payload()

    assert payload["summary"]["configured_agents"] == 0
    assert payload["summary"]["matching_agents"] == 0
    assert payload["agents"]["codex"]["configured"] is False
    assert payload["agents"]["codex"]["endpoint_matches"] is False
    assert payload["agents"]["codex"]["configured_endpoint"] == ENDPOINT
    assert payload["agents"]["codex"]["status"] == "missing_config"


def test_health_rejects_codex_otlp_http_explicit_false(device_home: Path) -> None:
    _write(
        device_home / ".codex" / "config.toml",
        """[otel]
environment = "dev"

[otel.exporter.otlp-http]
enabled = false
endpoint = "http://localhost:4002/v1/logs"
protocol = "json"
""",
    )

    payload = service.health_payload()

    assert payload["summary"]["configured_agents"] == 0
    assert payload["summary"]["matching_agents"] == 0
    assert payload["agents"]["codex"]["configured"] is False
    assert payload["agents"]["codex"]["endpoint_matches"] is False
    assert payload["agents"]["codex"]["status"] == "missing_config"


def test_health_handles_missing_agent_configs(device_home: Path) -> None:
    payload = service.health_payload()

    assert payload["summary"] == {
        "total_agents": 4,
        "configured_agents": 0,
        "matching_agents": 0,
    }
    for agent in payload["agents"].values():
        assert agent["configured"] is False
        assert agent["endpoint_matches"] is False
        assert agent["configured_endpoint"] is None
        assert agent["status"] == "missing_config"
    assert payload["agents"]["kilo"]["expected_endpoint"] == ENDPOINT


def test_health_detects_claude_endpoint_without_protocol_key(
    device_home: Path,
) -> None:
    _write(
        device_home / ".claude" / "settings.json",
        json.dumps(
            {
                "env": {
                    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                    "OTEL_LOGS_EXPORTER": "otlp",
                    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": ENDPOINT,
                }
            }
        ),
    )
    payload = service.health_payload()
    assert payload["agents"]["claude"]["status"] == "ready"


def test_health_opencode_ready(device_home: Path) -> None:
    config_path = device_home / ".config" / "opencode" / "opencode.json"
    _write_json(
        config_path,
        {
            "plugin": [
                [
                    "/some/path/plugins/opencode/dist/index.js",
                    {"endpoint": ENDPOINT},
                ]
            ]
        },
    )

    agent = service.health_payload()["agents"]["opencode"]

    assert agent["status"] == "ready"
    assert agent["configured"] is True
    assert agent["endpoint_matches"] is True


def test_health_opencode_missing(device_home: Path) -> None:
    agent = service.health_payload()["agents"]["opencode"]
    assert agent["status"] == "missing_config"
    assert agent["configured"] is False


def test_health_opencode_wrong_endpoint(device_home: Path) -> None:
    config_path = device_home / ".config" / "opencode" / "opencode.json"
    _write_json(
        config_path,
        {
            "plugin": [
                [
                    "/some/path/plugins/opencode/dist/index.js",
                    {"endpoint": "http://localhost:9999/v1/logs"},
                ]
            ]
        },
    )

    agent = service.health_payload()["agents"]["opencode"]

    assert agent["status"] == "wrong_endpoint"
    assert agent["configured"] is True
    assert agent["endpoint_matches"] is False


def test_health_opencode_bare_plugin_uses_plugin_default_endpoint(
    device_home: Path,
) -> None:
    expected = "http://localhost:4102/v1/logs"
    _write_json(
        device_home / ".tokenage" / "credentials.json",
        {"otlp_logs_endpoint": expected},
    )
    config_path = device_home / ".config" / "opencode" / "opencode.json"
    _write_json(config_path, {"plugin": ["/some/path/plugins/opencode/dist/index.js"]})

    agent = service.health_payload()["agents"]["opencode"]

    assert agent["status"] == "wrong_endpoint"
    assert agent["configured"] is True
    assert agent["endpoint_matches"] is False
    assert agent["configured_endpoint"] == "http://localhost:4005/v1/logs"
    assert agent["expected_endpoint"] == expected


def test_health_opencode_ignores_kilo_plugin(device_home: Path) -> None:
    config_path = device_home / ".config" / "opencode" / "opencode.json"
    _write_json(
        config_path,
        {
            "plugin": [
                [
                    "/some/path/plugins/kilo/dist/index.js",
                    {"endpoint": ENDPOINT},
                ]
            ]
        },
    )

    agent = service.health_payload()["agents"]["opencode"]

    assert agent["status"] == "missing_config"
    assert agent["configured"] is False
    assert agent["endpoint_matches"] is False
    assert agent["configured_endpoint"] is None


def test_health_kilo_ready(device_home: Path) -> None:
    config_path = device_home / ".config" / "kilo" / "opencode.json"
    _write_json(
        config_path,
        {"plugin": [["/some/path/plugins/kilo/dist/index.js", {"endpoint": ENDPOINT}]]},
    )

    agent = service.health_payload()["agents"]["kilo"]

    assert agent["status"] == "ready"
    assert agent["configured"] is True
    assert agent["endpoint_matches"] is True
    assert agent["configured_endpoint"] == ENDPOINT


def test_health_kilo_wrong_endpoint(device_home: Path) -> None:
    config_path = device_home / ".config" / "kilo" / "opencode.json"
    _write_json(
        config_path,
        {
            "plugin": [
                [
                    "/some/path/plugins/kilo/dist/index.js",
                    {"endpoint": "http://localhost:9999/v1/logs"},
                ]
            ]
        },
    )

    agent = service.health_payload()["agents"]["kilo"]

    assert agent["status"] == "wrong_endpoint"
    assert agent["configured"] is True
    assert agent["endpoint_matches"] is False
    assert agent["configured_endpoint"] == "http://localhost:9999/v1/logs"


# --------------------------------------------------------------- service lifecycle


def test_status_reports_stopped_without_state(device_home: Path, capsys) -> None:
    data = service.service_status()
    assert data["running"] is False
    assert service.run_status(as_json=True) == 1
    served = json.loads(capsys.readouterr().out)
    assert served["running"] is False
    assert served["client_version"]


def test_status_reports_a_live_pid(device_home: Path, capsys) -> None:
    _write_json(
        service.state_path(),
        {"pid": os.getpid(), "started_at": 1, "last_check_at": 2},
    )
    assert service.running_state() is not None
    assert service.run_status(as_json=True) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["running"] is True
    assert data["pid"] == os.getpid()
    assert data["last_check_at"] == 2


def test_stale_state_is_not_running(device_home: Path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    _write_json(service.state_path(), {"pid": dead.pid, "started_at": 1})
    assert service.running_state() is None


def test_stop_terminates_the_process_and_clears_state(
    device_home: Path, capsys
) -> None:
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        _write_json(service.state_path(), {"pid": sleeper.pid, "started_at": 1})
        assert service.stop() == 0
        assert sleeper.wait(timeout=5) is not None
        assert not service.state_path().exists()
        assert "stopped" in capsys.readouterr().out
    finally:
        sleeper.kill()
        sleeper.wait()


def test_stop_without_state_is_idempotent(device_home: Path) -> None:
    assert service.stop() == 0


def test_start_is_a_noop_when_already_running(device_home: Path, capsys) -> None:
    _write_json(service.state_path(), {"pid": os.getpid(), "started_at": 1})
    assert service.start() == 0
    assert "already running" in capsys.readouterr().out


def test_run_foreground_daemon_starts_and_stops(device_home: Path) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT),
        "TOKENAGE_HOME": str(device_home / ".tokenage"),
        "HOME": str(device_home),
        "TOKENAGE_CLIENT_COMMIT": "a" * 40,
    }
    process = subprocess.Popen(
        [sys.executable, "-P", "-m", "client", "client", "run"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and service.running_state() is None:
            time.sleep(0.05)
        state = service.running_state()
        assert state is not None
        assert state["pid"] == process.pid
        assert state["last_check_at"] is not None

        assert service.stop() == 0
        assert process.wait(timeout=10) == 0
        assert not service.state_path().exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_cli_client_health_json(device_home: Path, capsys) -> None:
    assert cli.main(["client", "health", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agents"]["claude"]["status"] == "missing_config"
    assert set(payload["detected"]) == {"claude", "codex", "opencode", "kilo"}


def test_cli_client_status_stopped(device_home: Path, capsys) -> None:
    assert cli.main(["client", "status"]) == 1
    assert "not running" in capsys.readouterr().out


# ------------------------------------------------------------------- reporting


class FakePost:
    def __init__(self, *, status_code: int = 204, error: Exception | None = None):
        self.calls: list[dict] = []
        self.status_code = status_code
        self.error = error

    def __call__(self, url, *, json=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status_code, request=httpx.Request("POST", url))


def _signed_in(device_home: Path) -> None:
    _write_json(
        device_home / ".tokenage" / "credentials.json",
        {
            "server_url": "https://srv.example",
            "cli_token": "cli-token",
            "otlp_logs_endpoint": ENDPOINT,
        },
    )


def test_report_signed_in_posts_with_bearer_and_strips_paths(
    device_home: Path, monkeypatch
) -> None:
    _signed_in(device_home)
    fake = FakePost()
    monkeypatch.setattr(service.httpx, "post", fake)
    state = {"last_report_at": None, "last_report_status": None}

    service._report_once(state)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://srv.example/devices/status"
    assert call["headers"] == {"Authorization": "Bearer cli-token"}
    assert call["timeout"] == service.REPORT_TIMEOUT_SECONDS
    assert call["json"]["device_name"]
    assert "installation_key" not in call["json"]
    assert all("path" not in info for info in call["json"]["detected"].values())
    assert state["last_report_status"] == "ok"
    assert isinstance(state["last_report_at"], int)


def test_report_local_posts_with_installation_key_and_paths(
    device_home: Path, monkeypatch, tmp_path
) -> None:
    server_root = tmp_path / "server"
    (server_root / ".venv" / "bin").mkdir(parents=True)
    (server_root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        "server:\n  host: 127.0.0.1\n  api_port: 4444\n", encoding="utf-8"
    )
    monkeypatch.setenv("TOKENAGE_ROOT", str(server_root))
    monkeypatch.setenv("TOKENAGE_CONFIG", str(config))
    fake = FakePost()
    monkeypatch.setattr(service.httpx, "post", fake)
    state = {"last_report_at": None, "last_report_status": None}

    service._report_once(state)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "http://localhost:4444/devices/status"
    body = call["json"]
    key = (
        (device_home / ".tokenage" / "installation_key")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert body["installation_key"] == key
    assert "path" in body["detected"]["claude"]
    assert state["last_report_status"] == "ok"


def test_report_without_server_makes_no_request(device_home: Path, monkeypatch) -> None:
    fake = FakePost()
    monkeypatch.setattr(service.httpx, "post", fake)
    state = {"last_report_at": None, "last_report_status": None}

    service._report_once(state)

    assert fake.calls == []
    assert state == {"last_report_at": None, "last_report_status": None}


@pytest.mark.parametrize(
    "fake",
    [
        FakePost(error=httpx.ConnectError("down")),
        FakePost(status_code=500),
    ],
    ids=["connection-error", "http-500"],
)
def test_report_failure_marks_state_and_the_loop_continues(
    device_home: Path, monkeypatch, fake: FakePost
) -> None:
    _signed_in(device_home)
    monkeypatch.setattr(service.httpx, "post", fake)
    state = {"last_check_at": None, "last_report_at": None, "last_report_status": None}

    service._check_once(state)

    assert state["last_report_status"] == "failed"
    assert state["last_report_at"] is None
    assert state["last_check_at"] is not None


def test_status_exposes_the_last_report(device_home: Path, capsys) -> None:
    _write_json(
        service.state_path(),
        {
            "pid": os.getpid(),
            "started_at": 1,
            "last_check_at": 2,
            "last_report_at": 3,
            "last_report_status": "ok",
        },
    )

    assert service.run_status(as_json=True) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["last_report_at"] == 3
    assert data["last_report_status"] == "ok"
