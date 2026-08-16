"""CLI-side tests for PR 3 login (docs/design/specs/pr3-cli-login-flow.md).

The server is a fake httpx (interface-compatible: .get for pre-flight, .post
for the exchange); stdin is fed via monkeypatched builtins.input.
"""

import json
import stat
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

    def __init__(
        self,
        *,
        exchange_status=200,
        exchange_payload=None,
        get_error=None,
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

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        if self.get_error is not None:
            raise self.get_error
        return SimpleNamespace(raise_for_status=lambda: None)

    def post(self, url, json=None, **kwargs):
        self.calls.append(("POST", url, json))
        status = self.exchange_statuses[
            min(self.post_index, len(self.exchange_statuses) - 1)
        ]
        self.post_index += 1
        return SimpleNamespace(status_code=status, json=lambda: self.exchange_payload)


def _run_login(
    cli_module,
    monkeypatch,
    *,
    inputs,
    no_browser=True,
    ssh_env=False,
    exchange_status=200,
    extra_args=(),
):
    fake = FakeHttpx(exchange_status=exchange_status)
    monkeypatch.setattr(cli_module, "httpx", fake)
    monkeypatch.delenv("LLMTRACKER_SERVER", raising=False)
    for key in ("SSH_CONNECTION", "SSH_TTY"):
        monkeypatch.delenv(key, raising=False)
    if ssh_env:
        monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 1234 10.0.0.2 22")
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: None)
    opened = []
    monkeypatch.setattr(cli_module.webbrowser, "open", lambda url: opened.append(url))

    responses = list(inputs)

    def fake_input(prompt=""):
        if not responses:
            raise EOFError
        return responses.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)

    args = ["login", "--server", "https://srv.example", *extra_args]
    if no_browser:
        args.append("--no-browser")
    return cli_module.run_login_command(args), fake, opened


def test_login_writes_credentials_0600(cli_module, isolated_home, monkeypatch, capsys):
    code, fake, opened = _run_login(
        cli_module, monkeypatch, inputs=["the-one-time-code"]
    )
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

    path = cli_module.credentials_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["server_url"] == "https://srv.example"
    assert data["email"] == "a@example.com"
    assert data["device_name"] == "testhost"
    assert data["cli_token"] == EXCHANGE_PAYLOAD["cli_token"]
    assert data["ingest_token"] == EXCHANGE_PAYLOAD["ingest_token"]
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600

    # Tokens are never printed to the terminal.
    assert "llmt_cli" not in captured.out
    assert "llmt_cli" not in captured.err
    assert "llmt_ingest" not in captured.out
    assert "llmt_ingest" not in captured.err


def test_login_retries_on_400_then_succeeds(
    cli_module, isolated_home, monkeypatch, capsys
):
    code, fake, _ = _run_login(
        cli_module,
        monkeypatch,
        inputs=["bad-code", "good-code"],
        exchange_status=[400, 200],
    )
    assert code == 0
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert [p[2]["code"] for p in posts] == ["BADCODE", "GOODCODE"]
    assert "paste it again" in capsys.readouterr().err


def test_login_three_failures_exit_1_no_credentials(
    cli_module, isolated_home, monkeypatch
):
    code, fake, _ = _run_login(
        cli_module,
        monkeypatch,
        inputs=["bad1", "bad2", "bad3"],
        exchange_status=400,
    )
    assert code == 1
    assert not cli_module.credentials_path().exists()
    assert len([c for c in fake.calls if c[0] == "POST"]) == 3


def test_login_empty_input_exit_1_no_credentials(
    cli_module, isolated_home, monkeypatch
):
    code, fake, _ = _run_login(cli_module, monkeypatch, inputs=["  "])
    assert code == 1
    assert not cli_module.credentials_path().exists()
    assert [c for c in fake.calls if c[0] == "POST"] == []


def test_login_ssh_skips_browser_but_prints_url(
    cli_module, isolated_home, monkeypatch, capsys
):
    code, _, opened = _run_login(
        cli_module,
        monkeypatch,
        inputs=["the-code"],
        no_browser=False,
        ssh_env=True,
    )
    assert code == 0
    assert opened == []  # no webbrowser.open over SSH
    assert "https://srv.example/auth/cli/start" in capsys.readouterr().out


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


def test_poll_summary_surfaces_api_error(cli_module, isolated_home, capsys):
    client = SimpleNamespace(
        get_run_summary=lambda **kwargs: (_ for _ in ()).throw(
            cli_module.ApiError("session rejected — run llm-tracker login")
        )
    )
    options = cli_module.RunOptions(wait_ms=0)
    result = cli_module.poll_summary(client, after_ts=0, options=options)
    assert result is None
    assert "llm-tracker login" in capsys.readouterr().err


def test_login_non_json_200_exits_clean(cli_module, isolated_home, monkeypatch):
    class BadJsonHttpx(FakeHttpx):
        def post(self, url, json=None, **kwargs):
            self.calls.append(("POST", url, json))
            return SimpleNamespace(
                status_code=200,
                json=lambda: (_ for _ in ()).throw(ValueError("not json")),
            )

    fake = BadJsonHttpx()
    monkeypatch.setattr(cli_module, "httpx", fake)
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "the-code")

    code = cli_module.run_login_command(
        ["login", "--server", "https://srv.example", "--no-browser"]
    )
    assert code == 1
    assert not cli_module.credentials_path().exists()


def test_login_warns_on_http_server(cli_module, isolated_home, monkeypatch, capsys):
    code, _, _ = _run_login(
        cli_module,
        monkeypatch,
        inputs=["the-code"],
        extra_args=["--server", "http://srv.example"],
    )
    assert code == 0
    assert "unencrypted" in capsys.readouterr().err


def test_load_credentials_warns_on_corrupt_file(cli_module, isolated_home, capsys):
    path = cli_module.credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert cli_module.load_credentials() is None
    assert "ignoring saved credentials" in capsys.readouterr().err


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
    assert cli_module.wire_agents_for_hosted(logs_endpoint=None) == []


def test_wire_agents_strips_otel_env_var(cli_module, isolated_home, monkeypatch):
    envs = []

    def fake_run(cmd, **kwargs):
        envs.append(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cli_module.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://local:4005/v1/logs")

    cli_module.wire_agents_for_hosted(logs_endpoint="https://api.example.com/v1/logs")
    assert envs
    assert all("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" not in env for env in envs)
    assert all("PATH" in env for env in envs)
