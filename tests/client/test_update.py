from __future__ import annotations

from pathlib import Path

import pytest

from client import cli, update


def _installed_components(tmp_path: Path) -> tuple[Path, Path]:
    server = tmp_path / "server"
    (server / "scripts").mkdir(parents=True)
    (server / "scripts" / "update.sh").write_text("#!/bin/sh\n")
    (server / "VERSION").write_text("0.2.19\n")
    client = tmp_path / "versions" / "client"
    client.mkdir(parents=True)
    return server, client


def test_update_check_delegates_server_check_and_does_not_claim_client_is_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    server, client = _installed_components(tmp_path)
    monkeypatch.setattr(update, "server_root", lambda: server)
    monkeypatch.setattr(update, "client_root", lambda: client)
    monkeypatch.setattr(update, "client_version", lambda: "0.1.0")
    monkeypatch.setattr(update, "client_commit", lambda: "a" * 40)
    calls: list[list[str]] = []

    def fake_run(command: list[str], env: dict[str, str] | None = None) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(update, "_run", fake_run)

    result = update.run_update(check=True, dry_run=False, scope="all")

    assert result == 0
    assert calls == [["bash", str(server / "scripts" / "update.sh"), "--check"]]
    output = capsys.readouterr().out
    assert "Installed client" in output
    assert "Client update availability cannot be checked" in output
    assert "up to date" not in output


def test_client_only_check_explains_availability_is_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _, client = _installed_components(tmp_path)
    monkeypatch.setattr(update, "server_root", lambda: None)
    monkeypatch.setattr(update, "client_root", lambda: client)
    monkeypatch.setattr(update, "client_version", lambda: "0.1.0")
    monkeypatch.setattr(update, "client_commit", lambda: "a" * 40)

    result = update.run_update(check=True, dry_run=False, scope="client")

    assert result == 0
    output = capsys.readouterr().out
    assert "Client update availability cannot be checked" in output
    assert "up to date" not in output


def test_update_completion_does_not_report_the_pre_update_client_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _, client = _installed_components(tmp_path)
    monkeypatch.setattr(update, "server_root", lambda: None)
    monkeypatch.setattr(update, "client_root", lambda: client)
    monkeypatch.setattr(update, "client_version", lambda: "0.1.0")
    monkeypatch.setattr(update, "client_commit", lambda: "a" * 40)
    monkeypatch.setattr(update, "update_client", lambda: 0)

    result = update.run_update(check=False, dry_run=False, scope="client")

    assert result == 0
    output = capsys.readouterr().out
    assert "✓ client updated" in output
    assert "✓ client  0.1.0" not in output


def test_client_update_runs_installer_with_login_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from client import auth

    monkeypatch.setattr(
        auth, "load_credentials", lambda: {"server_url": "https://host.test"}
    )
    monkeypatch.setattr(update.shutil, "which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(update, "_bin_dir", lambda: tmp_path / "bin")
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run(command: list[str], env: dict[str, str] | None = None) -> int:
        calls.append((command, env))
        if command[0] == "/usr/bin/curl":
            Path(command[command.index("-o") + 1]).write_text("#!/bin/sh\n")
        return 0

    monkeypatch.setattr(update, "_run", fake_run)

    assert update.update_client() == 0
    assert len(calls) == 2
    install_command, installer_env = calls[1]
    assert install_command[0] == "sh"
    assert installer_env is not None
    assert installer_env["LLM_TRACKER_SKIP_LOGIN"] == "1"
    assert installer_env["LLM_TRACKER_SERVER"] == "https://host.test"


def test_update_parser_no_longer_accepts_plugin_rebuild_flag() -> None:
    parser = cli._build_subcommand("update")

    with pytest.raises(SystemExit):
        parser.parse_args(["--rebuild-plugins"])
