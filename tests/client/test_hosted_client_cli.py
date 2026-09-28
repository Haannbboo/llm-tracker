"""The CLI surface, plus the login outcomes only an end-to-end run reaches.

``test_client_auth.py`` covers login, credentials, the installation proof, and
agent wiring through ``client.auth`` and ``client.setup`` directly. What is left
for this file is the argparse dispatch in ``client.cli`` and the outcomes that
only matter across a whole run: token rotation over two logins, a rejection
that must not be retried, and a bad payload that must not overwrite working
credentials.
"""

from __future__ import annotations

import json
import stat
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from client import auth, cli, paths, setup
from protocol import CURRENT_GENERATION

DEVICE_ID = "c0e1b327-5930-4457-a594-0fa8929a903b"


def _payload(index: int, *, logs_endpoint: str = "https://example.test/v1/logs") -> Any:
    return {
        "user": {"id": "u1", "email": "person@example.test"},
        "device_id": DEVICE_ID,
        "device_name": "machine",
        "cli_token": f"cli-{index}",
        "ingest_token": f"ingest-{index}",
        "otlp": {"logs_endpoint": logs_endpoint},
    }


class FakeHttpx:
    """The two httpx calls login makes. auth.httpx stays the real module."""

    def __init__(
        self,
        *,
        exchange: Callable[[int], tuple[int, Any]] | None = None,
        protocol_min: int = CURRENT_GENERATION,
        protocol_max: int = CURRENT_GENERATION,
    ) -> None:
        self.exchanges: list[dict[str, str]] = []
        self.protocol_min = protocol_min
        self.protocol_max = protocol_max
        self.exchange = exchange or (lambda index: (200, _payload(index)))

    def get(self, url, **_kwargs):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "protocol_min": self.protocol_min,
                "protocol_max": self.protocol_max,
            },
        )

    def post(self, url, *, json: dict[str, str], **_kwargs):
        self.exchanges.append(dict(json))
        status, payload = self.exchange(len(self.exchanges))
        return SimpleNamespace(status_code=status, json=lambda: payload)


def _install_fake_httpx(monkeypatch, fake: FakeHttpx) -> None:
    monkeypatch.setattr(auth.httpx, "get", fake.get)
    monkeypatch.setattr(auth.httpx, "post", fake.post)


@pytest.fixture(autouse=True)
def client_home(tmp_path, monkeypatch):
    """Credentials, the installation proof, and agent config never touch real $HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LLM_TRACKER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LLM_TRACKER_CLIENT_COMMIT", "a" * 40)
    monkeypatch.delenv("LLMTRACKER_SERVER", raising=False)
    # Nothing is detected on PATH, so a login wires no real agent config.
    monkeypatch.setattr(setup.shutil, "which", lambda _name: None)


# -------------------------------------------------------------- cli.py surface


def test_check_server_checks_protocol_without_writing(monkeypatch, capsys):
    fake = FakeHttpx()
    _install_fake_httpx(monkeypatch, fake)

    assert cli.main(["check-server", "--server", "https://example.test"]) == 0
    assert not auth.credentials_path().parent.exists()

    fake.protocol_min = CURRENT_GENERATION + 1
    fake.protocol_max = CURRENT_GENERATION + 1
    assert cli.main(["check-server", "--server", "https://example.test"]) == 1
    assert "incompatible" in capsys.readouterr().err
    # A refused box must leave no trace to sign in against later.
    assert not auth.credentials_path().parent.exists()


# ------------------------------------------------------------------ full login


def test_login_rotates_tokens_and_reuses_device_identity(monkeypatch, capsys):
    fake = FakeHttpx()
    _install_fake_httpx(monkeypatch, fake)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "ab-cd")

    for _ in range(2):
        assert (
            cli.main(["login", "--server", "https://example.test", "--no-browser"]) == 0
        )

    first, second = fake.exchanges
    assert first["code"] == "ABCD"
    assert first["client_version"] == paths.client_version()
    assert first["client_commit"] == "a" * 40
    assert "device_id" not in first
    # Same machine, same server: the identity is derived locally and the old
    # tokens ride along so the server can hold the device still across rotation.
    assert second["installation_key"] == first["installation_key"]
    assert "device_id" not in second
    assert second["prior_cli_token"] == "cli-1"
    assert second["prior_ingest_token"] == "ingest-1"

    credentials = json.loads(auth.credentials_path().read_text(encoding="utf-8"))
    assert credentials["cli_token"] == "cli-2"
    assert credentials["device_id"] == DEVICE_ID
    assert stat.S_IMODE(auth.credentials_path().stat().st_mode) == 0o600
    assert stat.S_IMODE(auth.installation_path().stat().st_mode) == 0o600
    output = capsys.readouterr()
    assert "cli-" not in output.out + output.err
    assert "ingest-" not in output.out + output.err
    assert first["installation_key"] not in output.out + output.err


def test_installation_key_follows_the_normalized_server_url():
    # Case, the default port, and a trailing slash all name one server, so they
    # must all derive one installation proof rather than three.
    assert auth.normalize_server_url("https://ONE.example.test:443/") == (
        "https://one.example.test"
    )
    key = auth.installation_key(
        auth.normalize_server_url("https://ONE.example.test:443/")
    )
    assert key == auth.installation_key("https://one.example.test")
    assert key != auth.installation_key("https://two.example.test")
    assert len(key) == 64


def test_concurrent_first_logins_publish_one_complete_installation_key(monkeypatch):
    barrier = threading.Barrier(2)
    link = auth.os.link

    def concurrent_link(source, destination):
        # Both first logins are inside publication when it happens, so whoever
        # loses the os.link race must read the winner's complete file.
        barrier.wait(timeout=5)
        return link(source, destination)

    monkeypatch.setattr(auth.os, "link", concurrent_link)
    with ThreadPoolExecutor(max_workers=2) as pool:
        keys = list(pool.map(auth.installation_key, ["https://one.test"] * 2))

    assert keys[0] == keys[1]
    assert len(keys[0]) == 64
    data = json.loads(auth.installation_path().read_text())
    assert len(data["installation_key"]) >= 43
    assert not list(auth.installation_path().parent.glob(".*tmp"))


def test_malformed_field_rejection_reports_the_reason_once(monkeypatch, capsys):
    fake = FakeHttpx(
        exchange=lambda _index: (422, {"detail": "invalid client_version"})
    )
    _install_fake_httpx(monkeypatch, fake)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "ab-cd")

    assert cli.main(["login", "--server", "https://example.test", "--no-browser"]) == 1
    # One attempt only — a 422 is not a mistyped code, so re-pasting is futile.
    assert len(fake.exchanges) == 1
    assert "invalid client_version" in capsys.readouterr().err


def test_invalid_otlp_endpoint_does_not_replace_existing_tokens(monkeypatch):
    fake = FakeHttpx(
        exchange=lambda index: (
            200,
            _payload(index, logs_endpoint="http://public.example.test/v1/logs"),
        )
    )
    _install_fake_httpx(monkeypatch, fake)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "code")
    auth.save_credentials(
        {"server_url": "https://example.test", "cli_token": "prior", "user_id": "u1"}
    )

    assert cli.main(["login", "--server", "https://example.test", "--no-browser"]) == 1
    assert auth.load_credentials() == {
        "server_url": "https://example.test",
        "cli_token": "prior",
        "user_id": "u1",
    }


# --------------------------------------------------------------------- wiring


def test_wiring_skips_a_script_that_reports_no_config(monkeypatch, capsys):
    # A `codex` on PATH with no ~/.codex yet: the configure script exits 0
    # after announcing a skip, which must not read as "wired".
    monkeypatch.setattr(
        setup.shutil, "which", lambda name: "/usr/bin/x" if name == "codex" else None
    )

    assert (
        setup.wire_agents(
            logs_endpoint="https://example.test/v1/logs", token="ingest-1"
        )
        == []
    )
    assert "skipping" in capsys.readouterr().err
