"""CLI-side tests for PR 3 login (docs/design/specs/pr3-cli-login-flow.md).

The loopback listener and handler run for real; the server is a fake httpx
(interface-compatible: .get for pre-flight, .post for the exchange).
"""

import json
import stat
import threading
import urllib.request
from types import SimpleNamespace

import httpx
import pytest

EXCHANGE_PAYLOAD = {
    "user": {"id": "u1", "email": "a@example.com", "name": "Alice"},
    "device_name": "testhost",
    "cli_token": "llmt_cli abcdef",
    "ingest_token": "llmt_ingest abcdef",
    "otlp": {
        "endpoint": "https://api.example.com:4005",
        "logs_endpoint": "https://api.example.com:4005/v1/logs",
    },
}


class FakeHttpx:
    """Replaces cli_module.httpx for login tests."""

    def __init__(self, *, exchange_status=200, exchange_payload=None, get_error=None):
        self.calls = []
        self.exchange_status = exchange_status
        self.exchange_payload = exchange_payload or EXCHANGE_PAYLOAD
        self.get_error = get_error

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        if self.get_error is not None:
            raise self.get_error
        return SimpleNamespace(raise_for_status=lambda: None)

    def post(self, url, json=None, **kwargs):
        self.calls.append(("POST", url, json))
        return SimpleNamespace(
            status_code=self.exchange_status,
            json=lambda: self.exchange_payload,
        )


def _fixed_port(cli_module, monkeypatch) -> int:
    port = cli_module.find_free_loopback_port()
    monkeypatch.setattr(cli_module, "find_free_loopback_port", lambda: port)
    return port


def _run_login(cli_module, monkeypatch, *extra_args):
    fake = FakeHttpx()
    monkeypatch.setattr(cli_module, "httpx", fake)
    monkeypatch.delenv("LLMTRACKER_SERVER", raising=False)
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: None)
    port = _fixed_port(cli_module, monkeypatch)
    monkeypatch.setattr(
        cli_module.webbrowser,
        "open",
        lambda url: (_ for _ in ()).throw(
            AssertionError("browser should not open with --no-browser")
        ),
    )

    result = {}

    def run():
        result["code"] = cli_module.run_login_command(
            [
                "login",
                "--server",
                "https://srv.example",
                "--no-browser",
                "--timeout",
                "20",
                *extra_args,
            ]
        )

    thread = threading.Thread(target=run)
    thread.start()
    # Deliver the one-time code to the real loopback listener.
    for _ in range(200):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/?code=the-one-time-code", timeout=1
            ) as response:
                assert response.status == 200
            break
        except OSError:
            import time

            time.sleep(0.05)
    else:
        pytest.fail("loopback listener never came up")
    thread.join(timeout=10)
    return result.get("code"), fake, port


def test_login_writes_credentials_0600(cli_module, isolated_home, monkeypatch):
    code, fake, _ = _run_login(cli_module, monkeypatch)
    assert code == 0

    # Pre-flight hit /version; exchange hit /auth/cli/exchange with the code.
    assert ("GET", "https://srv.example/version") in fake.calls
    exchange_calls = [c for c in fake.calls if c[0] == "POST"]
    assert len(exchange_calls) == 1
    assert exchange_calls[0][1] == "https://srv.example/auth/cli/exchange"
    assert exchange_calls[0][2]["code"] == "the-one-time-code"

    path = cli_module.credentials_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["server_url"] == "https://srv.example"
    assert data["email"] == "a@example.com"
    assert data["device_name"] == "testhost"
    assert data["cli_token"] == EXCHANGE_PAYLOAD["cli_token"]
    assert data["ingest_token"] == EXCHANGE_PAYLOAD["ingest_token"]
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_login_timeout_writes_no_credentials(cli_module, isolated_home, monkeypatch):
    fake = FakeHttpx()
    monkeypatch.setattr(cli_module, "httpx", fake)
    monkeypatch.delenv("LLMTRACKER_SERVER", raising=False)
    _fixed_port(cli_module, monkeypatch)

    code = cli_module.run_login_command(
        ["login", "--server", "https://srv.example", "--no-browser", "--timeout", "1"]
    )
    assert code == 1
    assert not cli_module.credentials_path().exists()
    # No exchange attempt was made.
    assert [c for c in fake.calls if c[0] == "POST"] == []


def test_login_unreachable_server_fails_clean(cli_module, isolated_home, monkeypatch):
    fake = FakeHttpx(get_error=httpx.ConnectError("no route"))
    monkeypatch.setattr(cli_module, "httpx", fake)
    opened = []
    monkeypatch.setattr(cli_module.webbrowser, "open", lambda url: opened.append(url))

    code = cli_module.run_login_command(["login", "--server", "https://down.example"])
    assert code == 1
    assert opened == []  # pre-flight failed before any browser open
    assert not cli_module.credentials_path().exists()


def test_login_requires_server(cli_module, isolated_home, monkeypatch):
    monkeypatch.delenv("LLMTRACKER_SERVER", raising=False)
    code = cli_module.run_login_command(["login"])
    assert code == 2


def test_login_server_from_env(cli_module, isolated_home, monkeypatch):
    monkeypatch.setenv("LLMTRACKER_SERVER", "https://env.example")
    fake = FakeHttpx(get_error=httpx.ConnectError("stop here"))
    monkeypatch.setattr(cli_module, "httpx", fake)
    cli_module.run_login_command(["login"])
    assert ("GET", "https://env.example/version") in fake.calls


# ------------------------------------------------------ credentials + bearer


def test_usage_client_sends_bearer_from_credentials(cli_module, isolated_home):
    cli_module.save_credentials(
        {"server_url": "https://srv.example", "cli_token": "tok-1"}
    )
    client = cli_module.UsageApiClient()
    assert client.base_url == "https://srv.example"
    assert client.token == "tok-1"


def test_usage_client_without_credentials_unchanged(cli_module, isolated_home):
    client = cli_module.UsageApiClient()
    assert client.token is None
    assert client.base_url == cli_module.build_api_base_url()


def test_usage_client_401_surfaces_relogin_message(
    cli_module, isolated_home, monkeypatch
):
    cli_module.save_credentials({"server_url": "https://srv.example", "cli_token": "t"})

    def fake_get(url, params=None, headers=None, timeout=None):
        request = httpx.Request("GET", url)
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(cli_module.httpx, "get", fake_get)
    client = cli_module.UsageApiClient()
    with pytest.raises(cli_module.ApiError) as excinfo:
        client.get_high_watermark()
    assert "llm-tracker login" in str(excinfo.value)


def test_main_uses_watermark_path_only_with_credentials(
    cli_module, isolated_home, monkeypatch
):
    seen = {}

    def fake_run_with_tracking(*, command, options, client=None):
        seen["client"] = client
        return 0

    monkeypatch.setattr(cli_module, "run_with_tracking", fake_run_with_tracking)
    monkeypatch.setattr(
        cli_module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0)
    )

    # Without credentials: isolated path (client=None), exactly as before.
    assert cli_module.main(["fake-cmd"]) == 0
    assert seen["client"] is None

    # With credentials: watermark path with a bearer-attached client.
    cli_module.save_credentials(
        {"server_url": "https://srv.example", "cli_token": "tok-1"}
    )
    assert cli_module.main(["fake-cmd"]) == 0
    assert seen["client"] is not None
    assert seen["client"].base_url == "https://srv.example"


def test_watermark_401_message_reaches_stderr(
    cli_module, isolated_home, monkeypatch, capsys
):
    cli_module.save_credentials({"server_url": "https://srv.example", "cli_token": "t"})

    client = SimpleNamespace(
        get_high_watermark=lambda: (_ for _ in ()).throw(
            cli_module.ApiError("session rejected — run llm-tracker login")
        )
    )
    monkeypatch.setattr(
        cli_module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0)
    )
    options = cli_module.RunOptions(no_summary=True)
    code = cli_module.run_with_watermark_tracking(
        command=["fake-cmd"], client=client, options=options
    )
    assert code == 0
    assert "llm-tracker login" in capsys.readouterr().err


# ------------------------------------------------------------------ wiring


def test_wire_agents_for_hosted_invokes_scripts(cli_module, isolated_home, monkeypatch):
    calls = []

    def fake_which(name):
        return f"/usr/bin/{name}" if name in ("codex", "claude") else None

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cli_module.shutil, "which", fake_which)
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)

    wired = cli_module.wire_agents_for_hosted(
        logs_endpoint="https://api.example.com:4005/v1/logs",
        base_endpoint="https://api.example.com:4005",
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


def test_wire_agents_no_endpoint_noop(cli_module, isolated_home, monkeypatch):
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: "/usr/bin/" + name)
    assert (
        cli_module.wire_agents_for_hosted(logs_endpoint=None, base_endpoint=None) == []
    )
