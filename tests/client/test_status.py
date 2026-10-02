"""``llm-tracker status`` — the component report."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
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

    def runtime_version(*args, **kwargs):
        from types import SimpleNamespace

        info = status.local_server_info()
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "collector_bind": {
                    "host": str(status.local_config().get("host") or "127.0.0.1"),
                    "port": info["otlp_port"],
                }
            },
        )

    monkeypatch.setattr(status.httpx, "get", runtime_version)
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


def test_known_collector_with_missing_agent_config_is_unhealthy(
    tracker_home, monkeypatch, capsys
):
    monkeypatch.setattr(
        setup.shutil,
        "which",
        lambda name: "/usr/bin/codex" if name == "codex" else None,
    )
    _write(
        tracker_home / ".llm-tracker" / "credentials.json",
        json.dumps(
            {
                "server_url": "https://app.example.com",
                "otlp_logs_endpoint": "https://app.example.com/v1/logs",
            }
        ),
    )
    assert status.run_status(as_json=True) == 1
    data = json.loads(capsys.readouterr().out)
    codex = next(agent for agent in data["agents"] if agent["name"] == "codex")
    assert codex["configured"] is False
    assert codex["endpoint_matches"] is False


@pytest.mark.parametrize(
    "bind,expected_host",
    [
        ("192.0.2.10", "192.0.2.10"),
        ("::1", "::1"),
        ("::", "::1"),
        ("0.0.0.0", "127.0.0.1"),
    ],
)
@pytest.mark.parametrize("override", [None, "http://[::1]:9105/v1/logs"])
def test_status_probes_actual_bind_addresses(
    tracker_home, monkeypatch, bind, expected_host, override
):
    root = tracker_home / ".llm-tracker" / "src"
    _write(root / ".venv" / "bin" / "python", "#!/bin/sh\n")
    _write(
        tracker_home / ".llm-tracker" / "config.yaml",
        f"server:\n  host: '{bind}'\n  base_url: https://public.example\n  port: 9100\n",
    )
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(root))
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
    if override:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", override)
    from types import SimpleNamespace

    runtime_endpoint = override or "https://public.example:9102/v1/logs"
    requests = []
    monkeypatch.setattr(
        status.httpx,
        "get",
        lambda url, **kwargs: (
            requests.append(url)
            or SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "otlp_logs_endpoint": runtime_endpoint,
                    "collector_bind": {
                        "host": "::1" if override else bind,
                        "port": 9105 if override else 9102,
                    },
                },
            )
        ),
    )
    # The client's inherited override must not control runtime health probes.
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://stale.example:9999/v1/logs"
    )
    probes = []
    monkeypatch.setattr(status, "_supervisor_running", lambda *args: True)
    monkeypatch.setattr(
        status,
        "_port_listening",
        lambda host, port: probes.append((host, port)) or True,
    )
    data = status.collect()
    assert probes == [
        (expected_host, 9100),
        (expected_host, 9101),
        ("::1", 9105) if override else (expected_host, 9102),
    ]
    assert status.is_healthy(data)
    assert data["server"]["services"][-1]["port"] == (9105 if override else 9102)
    authority = f"[{expected_host}]" if ":" in expected_host else expected_host
    assert requests == [f"http://{authority}:9101/version"]


@pytest.mark.parametrize("agent", ["claude", "codex", "opencode", "kilo"])
@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:secret@collector.example/v1/logs?token=secret#secret",
        "https://collector.example/secret/v1/logs",
    ],
)
def test_status_redacts_collector_secrets_in_all_output(
    tracker_home, monkeypatch, capsys, agent, as_json, endpoint
):
    monkeypatch.setattr(
        setup.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name == agent else None,
    )
    _write(
        tracker_home / ".llm-tracker" / "credentials.json",
        json.dumps(
            {
                "server_url": "https://user:secret@api.example?token=secret",
                "otlp_logs_endpoint": "https://tracker.example/v1/logs",
            }
        ),
    )
    if agent == "claude":
        _write(
            tracker_home / ".claude" / "settings.json",
            json.dumps(
                {
                    "env": {
                        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                        "OTEL_LOGS_EXPORTER": "otlp",
                        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": endpoint,
                    }
                }
            ),
        )
    elif agent == "codex":
        _write(
            tracker_home / ".codex" / "config.toml",
            f'[otel.exporter.otlp-http]\nendpoint = "{endpoint}"\n',
        )
    else:
        _write(
            tracker_home / ".config" / agent / "opencode.json",
            json.dumps(
                {
                    "plugin": [
                        [
                            f"/tracker/plugins/{agent}/dist/index.js",
                            {"endpoint": endpoint},
                        ]
                    ]
                }
            ),
        )
    assert status.run_status(as_json=as_json) == 1
    output = capsys.readouterr()
    assert "secret" not in output.out + output.err
    assert "collector.example" in output.out
    state = setup.read_agent_states("https://tracker.example/v1/logs")[agent]
    assert state["configured_endpoint"] == endpoint
    assert state["endpoint_matches"] is False


def test_status_does_not_guess_collector_port_when_api_omits_hint(
    tracker_home, monkeypatch, capsys
):
    from types import SimpleNamespace

    root = tracker_home / ".llm-tracker" / "src"
    _write(root / ".venv" / "bin" / "python", "#!/bin/sh\n")
    _write(
        tracker_home / ".llm-tracker" / "config.yaml",
        "server:\n  port: 9300\n  otlp_port: 9302\n",
    )
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(root))
    monkeypatch.setattr(
        status.httpx,
        "get",
        lambda *a, **k: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"protocol_min": 1, "protocol_max": 1},
        ),
    )
    monkeypatch.setattr(status, "_supervisor_running", lambda *a: True)
    probes = []
    monkeypatch.setattr(
        status,
        "_port_listening",
        lambda host, port: probes.append((host, port)) or True,
    )
    assert status.run_status(as_json=False) == 0
    out = capsys.readouterr().out
    assert "otlp :? unknown" in out
    assert "collector configuration; its address is unknown" in out
    assert "server start" not in out
    assert probes == [("127.0.0.1", 9300), ("127.0.0.1", 9301)]
    assert status.collect()["server"]["services"][-1]["port"] is None


@pytest.mark.parametrize("public_hint", [False, True])
def test_status_uses_bind_metadata_independently_of_public_endpoint(
    tracker_home, monkeypatch, public_hint
):
    from types import SimpleNamespace

    root = tracker_home / ".llm-tracker" / "src"
    _write(root / ".venv" / "bin" / "python", "#!/bin/sh\n")
    _write(
        tracker_home / ".llm-tracker" / "config.yaml",
        "server:\n  host: 127.0.0.1\n  base_url: https://nas.example\n  port: 9400\n  otlp_port: 9402\n",
    )
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(root))
    actual_host = "nas.example" if public_hint else "127.0.0.1"
    payload = {"collector_bind": {"host": actual_host, "port": 9205}}
    if public_hint:
        payload["otlp_logs_endpoint"] = "https://nas.example:9205/v1/logs"
    monkeypatch.setattr(
        status.httpx,
        "get",
        lambda *a, **k: SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: payload
        ),
    )
    monkeypatch.setattr(status, "_supervisor_running", lambda *a: True)
    probes = []
    monkeypatch.setattr(
        status,
        "_port_listening",
        lambda host, port: probes.append((host, port)) or True,
    )
    data = status.collect()
    assert probes == [("127.0.0.1", 9400), ("127.0.0.1", 9401), (actual_host, 9205)]
    assert data["server"]["services"][-1]["state"] == "up"
    assert status.is_healthy(data)


def test_unavailable_api_leaves_collector_address_unknown(tracker_home, monkeypatch):
    root = tracker_home / ".llm-tracker" / "src"
    _write(root / ".venv" / "bin" / "python", "#!/bin/sh\n")
    monkeypatch.setenv("LLM_TRACKER_ROOT", str(root))

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("local API unavailable")

    monkeypatch.setattr(status.httpx, "get", unavailable)
    monkeypatch.setattr(status, "_supervisor_running", lambda *a: True)
    probes = []
    monkeypatch.setattr(
        status,
        "_port_listening",
        lambda host, port: probes.append((host, port)) or True,
    )
    data = status.collect()
    assert len(probes) == 2
    assert data["server"]["services"][-1]["state"] == "unknown"
    assert data["server"]["services"][-1]["port"] is None
    data["agents"][0].update(
        detected=True,
        configured=True,
        endpoint_matches=True,
        endpoint="https://tracker.example/v1/logs",
    )
    rendered = status.render(data)
    assert "collector address unknown" in rendered
    assert "(not reachable)" not in rendered
    data["server"]["services"][0]["state"] = "down"
    assert status._fix_hint(data) == "run llm-tracker server start"
