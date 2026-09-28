"""Sign-in, credentials, and the installation proof.

The server is a fake httpx (interface-compatible: .get for pre-flight, .post
for the exchange); stdin is fed via monkeypatched builtins.input. Agent wiring
lives in client.setup and is exercised through the same entry point.
"""

from __future__ import annotations

import json
import stat
from types import SimpleNamespace

import httpx
import pytest

from client import auth, paths, setup, track
from protocol import CURRENT_GENERATION

EXCHANGE_PAYLOAD = {
    "user": {"id": "u1", "email": "a@example.com", "name": "Alice"},
    "device_id": "c0e1b327-5930-4457-a594-0fa8929a903b",
    "device_name": "testhost",
    "cli_token": "llmt_cli abcdef",
    "ingest_token": "llmt_ingest abcdef",
    "otlp": {
        "endpoint": "https://api.example.com:4005",
        "logs_endpoint": "https://api.example.com:4005/v1/logs",
    },
}


@pytest.fixture(autouse=True)
def client_home(tmp_path, monkeypatch):
    """Credentials, the installation proof, and agent config never touch real $HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LLM_TRACKER_HOME", str(tmp_path / "tracker"))


class FakeHttpx:
    """The two httpx calls login makes, faked. auth.httpx keeps the real module."""

    def __init__(
        self,
        *,
        exchange_status=200,
        exchange_payload=None,
        get_error=None,
        protocol_min=None,
        protocol_max=None,
    ):
        self.calls = []
        self.post_index = 0
        self.exchange_statuses = (
            list(exchange_status)
            if isinstance(exchange_status, (list, tuple))
            else [exchange_status]
        )
        self.exchange_payload = exchange_payload or EXCHANGE_PAYLOAD
        self.get_error = get_error
        self.protocol_min = CURRENT_GENERATION if protocol_min is None else protocol_min
        self.protocol_max = CURRENT_GENERATION if protocol_max is None else protocol_max

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        if self.get_error is not None:
            raise self.get_error
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "protocol_min": self.protocol_min,
                "protocol_max": self.protocol_max,
            },
        )

    def post(self, url, json=None, **kwargs):
        self.calls.append(("POST", url, dict(json or {})))
        status = self.exchange_statuses[
            min(self.post_index, len(self.exchange_statuses) - 1)
        ]
        self.post_index += 1
        return SimpleNamespace(status_code=status, json=lambda: self.exchange_payload)


def _install_fake_httpx(monkeypatch, fake: FakeHttpx) -> None:
    monkeypatch.setattr(auth.httpx, "get", fake.get)
    monkeypatch.setattr(auth.httpx, "post", fake.post)


def _run_login(
    monkeypatch,
    *,
    inputs,
    no_browser=True,
    ssh_env=False,
    exchange_status=200,
    extra_args=(),
):
    fake = FakeHttpx(exchange_status=exchange_status)
    _install_fake_httpx(monkeypatch, fake)
    monkeypatch.delenv("LLMTRACKER_SERVER", raising=False)
    for key in ("SSH_CONNECTION", "SSH_TTY"):
        monkeypatch.delenv(key, raising=False)
    if ssh_env:
        monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 1234 10.0.0.2 22")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    opened = []
    monkeypatch.setattr(auth.webbrowser, "open", lambda url: opened.append(url))

    responses = list(inputs)

    def fake_input(prompt=""):
        if not responses:
            raise EOFError
        return responses.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)

    server = "https://srv.example"
    for index, value in enumerate(extra_args):
        if value == "--server":
            server = extra_args[index + 1]

    code = auth.login(server, device_name_arg=None, no_browser=no_browser)
    return code, fake, opened


# ------------------------------------------------------------------- login


def test_login_writes_credentials_0600(monkeypatch, capsys):
    code, fake, opened = _run_login(monkeypatch, inputs=["the-one-time-code"])
    assert code == 0
    assert opened == []

    # The login URL is always printed.
    captured = capsys.readouterr()
    assert "https://srv.example/auth/cli/start" in captured.out

    # Pre-flight hit /version; exchange hit /auth/cli/exchange with the
    # normalized code (uppercase, hyphens and whitespace stripped).
    assert ("GET", "https://srv.example/version") in fake.calls
    exchange_calls = [c for c in fake.calls if c[0] == "POST"]
    assert len(exchange_calls) == 1
    assert exchange_calls[0][1] == "https://srv.example/auth/cli/exchange"
    assert exchange_calls[0][2]["code"] == "THEONETIMECODE"

    path = auth.credentials_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["server_url"] == "https://srv.example"
    assert data["email"] == "a@example.com"
    assert data["device_name"] == "testhost"
    assert data["cli_token"] == EXCHANGE_PAYLOAD["cli_token"]
    assert data["ingest_token"] == EXCHANGE_PAYLOAD["ingest_token"]
    assert data["otlp_logs_endpoint"] == EXCHANGE_PAYLOAD["otlp"]["logs_endpoint"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    # Tokens are never printed to the terminal.
    assert "llmt_cli" not in captured.out
    assert "llmt_cli" not in captured.err
    assert "llmt_ingest" not in captured.out
    assert "llmt_ingest" not in captured.err


def test_login_retries_on_400_then_succeeds(monkeypatch, capsys):
    code, fake, _ = _run_login(
        monkeypatch,
        inputs=["bad-code", "good-code"],
        exchange_status=[400, 200],
    )
    assert code == 0
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert [p[2]["code"] for p in posts] == ["BADCODE", "GOODCODE"]
    assert "paste it again" in capsys.readouterr().err


def test_login_three_failures_exit_1_no_credentials(monkeypatch):
    code, fake, _ = _run_login(
        monkeypatch,
        inputs=["bad1", "bad2", "bad3"],
        exchange_status=400,
    )
    assert code == 1
    assert not auth.credentials_path().exists()
    assert len([c for c in fake.calls if c[0] == "POST"]) == 3


def test_login_empty_input_exit_1_no_credentials(monkeypatch):
    code, fake, _ = _run_login(monkeypatch, inputs=["  "])
    assert code == 1
    assert not auth.credentials_path().exists()
    assert [c for c in fake.calls if c[0] == "POST"] == []


def test_login_ssh_skips_browser_but_prints_url(monkeypatch, capsys):
    code, _, opened = _run_login(
        monkeypatch,
        inputs=["the-code"],
        no_browser=False,
        ssh_env=True,
    )
    assert code == 0
    assert opened == []  # no webbrowser.open over SSH
    assert "https://srv.example/auth/cli/start" in capsys.readouterr().out


def test_login_unreachable_server_fails_clean(monkeypatch):
    fake = FakeHttpx(get_error=httpx.ConnectError("no route"))
    _install_fake_httpx(monkeypatch, fake)
    opened = []
    monkeypatch.setattr(auth.webbrowser, "open", lambda url: opened.append(url))

    code = auth.login("https://down.example", device_name_arg=None, no_browser=True)
    assert code == 1
    assert opened == []  # pre-flight failed before any browser open
    assert not auth.credentials_path().exists()


def test_login_requires_server(monkeypatch):
    monkeypatch.delenv("LLMTRACKER_SERVER", raising=False)
    assert auth.login(None, device_name_arg=None, no_browser=True) == 2


def test_login_server_from_env(monkeypatch):
    monkeypatch.setenv("LLMTRACKER_SERVER", "https://env.example")
    fake = FakeHttpx(get_error=httpx.ConnectError("stop here"))
    _install_fake_httpx(monkeypatch, fake)
    auth.login(None, device_name_arg=None, no_browser=True)
    assert ("GET", "https://env.example/version") in fake.calls


def test_login_non_json_200_exits_clean(monkeypatch):
    class BadJsonHttpx(FakeHttpx):
        def post(self, url, json=None, **kwargs):
            self.calls.append(("POST", url, dict(json or {})))
            return SimpleNamespace(
                status_code=200,
                json=lambda: (_ for _ in ()).throw(ValueError("not json")),
            )

    _install_fake_httpx(monkeypatch, BadJsonHttpx())
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "the-code")

    code = auth.login("https://srv.example", device_name_arg=None, no_browser=True)
    assert code == 1
    assert not auth.credentials_path().exists()


@pytest.mark.parametrize(
    ("server", "expected_code"),
    [
        ("http://srv.example", 2),
        ("HTTP://srv.example", 2),
        ("http://localhost:4004", 0),
        ("http://127.0.0.1", 0),
        ("http://localhost.attacker.example", 2),
    ],
)
def test_login_accepts_plain_http_only_for_loopback(monkeypatch, server, expected_code):
    code, _, _ = _run_login(
        monkeypatch,
        inputs=["the-code"],
        extra_args=["--server", server],
    )
    assert code == expected_code
    assert auth.credentials_path().exists() is (expected_code == 0)


def test_check_server_rejects_an_incompatible_protocol(monkeypatch, capsys):
    _install_fake_httpx(monkeypatch, FakeHttpx(protocol_min=99, protocol_max=99))

    assert auth.check_server("https://srv.example") == 1
    assert "incompatible" in capsys.readouterr().err


# ------------------------------------------------- credentials + installation


def test_load_credentials_raises_on_corrupt_file():
    path = auth.credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        auth.load_credentials()


def test_clear_credentials_reports_whether_there_were_any():
    assert auth.clear_credentials() is False
    auth.save_credentials({"server_url": "https://srv.example"})
    assert auth.clear_credentials() is True
    assert auth.load_credentials() is None


def test_installation_key_is_server_scoped():
    first = auth.installation_key("https://one.example.test")
    second = auth.installation_key("https://two.example.test")

    assert len(first) == 64
    assert first != second
    assert auth.installation_key("https://one.example.test") == first
    assert stat.S_IMODE(auth.installation_path().stat().st_mode) == 0o600


def test_logout_removes_credentials(monkeypatch, capsys):
    auth.save_credentials(
        {
            "server_url": "https://srv.example",
            "otlp_logs_endpoint": "https://srv.example/v1/logs",
        }
    )
    # The collector is passed on, so a foreign collector is left alone.
    seen: list[str | None] = []
    monkeypatch.setattr(
        setup,
        "disable_agents",
        lambda *, expected_endpoint: seen.append(expected_endpoint) or ["codex"],
    )

    assert auth.logout(keep_agents=False) == 0
    assert auth.load_credentials() is None
    assert seen == ["https://srv.example/v1/logs"]
    output = capsys.readouterr()
    assert "un-wired  codex" in output.out
    assert auth.logout(keep_agents=False) == 1
    assert "Not signed in" in capsys.readouterr().err


# --------------------------------------------------------- endpoint checking


@pytest.mark.parametrize(
    "raw",
    [
        "https://api.example.com:4005/v1/logs",
        "http://localhost:4005/v1/logs",
        "http://127.0.0.1:4002/v1/logs",
    ],
)
def test_valid_logs_endpoint_accepts_https_and_loopback(raw):
    assert auth.valid_logs_endpoint(raw) is True


@pytest.mark.parametrize(
    "raw",
    [
        "http://api.example.com:4005/v1/logs",
        "https://api.example.com:4005/v1/other",
        "https://user:pw@api.example.com/v1/logs",
        "https://api.example.com/v1/logs?x=1",
        "not a url",
    ],
)
def test_valid_logs_endpoint_rejects_everything_else(raw):
    assert auth.valid_logs_endpoint(raw) is False


# ------------------------------------------------------- credentials + bearer


def test_usage_client_sends_bearer_from_credentials():
    auth.save_credentials({"server_url": "https://srv.example", "cli_token": "tok-1"})
    client = track.UsageApiClient()
    assert client.base_url == "https://srv.example"
    assert client.token == "tok-1"


def test_usage_client_without_credentials_uses_the_local_api():
    client = track.UsageApiClient()
    assert client.token is None
    assert client.base_url == paths.local_server_info()["api_url"]


def test_usage_client_401_surfaces_relogin_message(monkeypatch):
    auth.save_credentials({"server_url": "https://srv.example", "cli_token": "t"})

    def fake_get(url, params=None, headers=None, timeout=None):
        request = httpx.Request("GET", url)
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(track.httpx, "get", fake_get)
    client = track.UsageApiClient()
    with pytest.raises(track.ApiError) as excinfo:
        client.get_high_watermark()
    assert "llm-tracker login" in str(excinfo.value)


# ------------------------------------------------------------------ wiring


def test_wire_agents_for_hosted_invokes_scripts(monkeypatch):
    calls = []

    def fake_which(name):
        return f"/usr/bin/{name}" if name in ("codex", "claude") else None

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(setup.shutil, "which", fake_which)
    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    wired = setup.wire_agents(
        logs_endpoint="https://api.example.com:4005/v1/logs",
        token=None,
    )
    assert wired == ["codex", "claude"]
    assert len(calls) == 2
    # Trailing argv matches the scripts' documented [PREFIX... PORT HOST
    # ENDPOINT] shape — the endpoint must land AFTER the port/host slot,
    # not in it.
    assert calls[0][-3:] == ["0", "localhost", "https://api.example.com:4005/v1/logs"]
    assert calls[1][-3:] == ["0", "localhost", "https://api.example.com:4005/v1/logs"]
    for cmd in calls:
        assert cmd[1].endswith("configure-codex-settings.py") or cmd[1].endswith(
            "configure-claude-settings.py"
        )


def test_wire_agents_passes_ingest_token_via_environment(monkeypatch):
    calls = []

    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    wired = setup.wire_agents(
        logs_endpoint="https://api.example.com:4005/v1/logs",
        token="ingest-secret",
    )

    assert wired == ["codex", "claude", "opencode", "kilo"]
    assert calls
    for cmd, kwargs in calls:
        assert all("ingest-secret" not in str(arg) for arg in cmd)
        assert kwargs["env"]["LLM_TRACKER_INGEST_TOKEN"] == "ingest-secret"


def test_wire_agents_strips_otel_env_var(monkeypatch):
    envs = []

    def fake_run(cmd, **kwargs):
        envs.append(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(setup.subprocess, "run", fake_run)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://local:4005/v1/logs")

    setup.wire_agents(logs_endpoint="https://api.example.com/v1/logs", token=None)
    assert envs
    assert all("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" not in env for env in envs)
    assert all("PATH" in env for env in envs)


def test_wire_agents_timeout_warns_and_skips(monkeypatch, capsys):
    def fake_run(cmd, **kwargs):
        raise setup.subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    wired = setup.wire_agents(
        logs_endpoint="https://api.example.com/v1/logs", token=None
    )
    assert wired == []
    assert "timed out" in capsys.readouterr().err
