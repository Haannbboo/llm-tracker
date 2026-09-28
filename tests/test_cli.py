"""The server operator CLI and the installed launcher that fronts both halves.

Everything a per-user client does — tracking, sign-in, agent wiring — is tested
in tests/client/ against the client package. What is left here is what only the
server can answer (`llm-tracker server token ...`) and the contract of
scripts/llm-tracker, the one installed command.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "llm-tracker"


def _run_launcher(tmp_path, *args):
    env = os.environ.copy()
    # A scrubbed home keeps the launcher's discovery off this machine, and no tty
    # plus a fixed width keeps the banner out of the captured output.
    env["LLM_TRACKER_HOME"] = str(tmp_path / "tracker-home")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["COLUMNS"] = "100"
    return subprocess.run(
        [str(LAUNCHER), *args],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )


# ------------------------------------------------------------- operator CLI


def test_parse_token_args_defaults_to_a_cli_token(cli_module, isolated_home):
    args = cli_module.parse_token_args(["create", "--email", "a@example.com"])

    assert args.action == "create"
    assert args.email == "a@example.com"
    assert args.kind == "cli"
    assert args.name is None


def test_run_token_command_prints_the_token_once(cli_module, isolated_home, capsys):
    from src.auth.tokens import resolve_token

    code = cli_module.run_token_command(
        ["create", "--email", "a@example.com", "--name", "laptop"]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "Minted cli token for a@example.com" in out
    token = out.strip().splitlines()[-1]
    assert token.startswith("llmt_cli_")
    assert resolve_token(token) is not None


def test_main_without_a_command_prints_usage(cli_module, isolated_home, capsys):
    assert cli_module.main([]) == 2
    assert "usage: llm-tracker server token create --email" in capsys.readouterr().err


# ------------------------------------------------------------ launcher wiring


def test_dev_scripts_live_under_scripts_dev():
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"

    assert not (scripts_dir / "dev-start.sh").exists()
    assert not (scripts_dir / "dev-stop.sh").exists()
    assert (scripts_dir / "dev" / "dev-start.sh").exists()
    assert (scripts_dir / "dev" / "dev-stop.sh").exists()


def test_llm_tracker_script_routes_to_client_and_server():
    content = LAUNCHER.read_text(encoding="utf-8")

    # Anything that is not a server command runs the client. `-P` matters: without
    # it a `python -m` run from inside some other checkout would import that
    # checkout's client instead of the installed one.
    assert 'exec "$python" -P -m client "$@"' in content
    # `llm-tracker server ...` is the server half: shell scripts, plus the
    # operator CLI for `server token`.
    assert "run_server() {" in content
    assert '-m src.cli "$@"' in content


def test_llm_tracker_server_routes_bootstrap_to_the_script(tmp_path):
    content = LAUNCHER.read_text(encoding="utf-8")

    assert 'exec bash "${root}/scripts/${name}.sh" "$@"' in content
    assert "bootstrap|start|stop|restart|status) shift; run_server_script" in content
    # The bare spellings still route, with a note on stderr — except `status`,
    # which is the component report now. Its old meaning is `server status`.
    assert "bootstrap|start|stop|restart|token)" in content
    assert 'alias_notice "$1"' in content

    result = _run_launcher(tmp_path, "server")
    assert result.returncode == 2
    assert "bootstrap" in result.stderr


def test_status_is_not_a_legacy_alias(tmp_path):
    """`llm-tracker status` reports components; the service view is `server status`."""
    result = _run_launcher(tmp_path, "status")

    assert result.returncode != 2 or "is now" not in result.stderr
    assert "is now" not in result.stderr
    assert "Service Status" not in result.stdout


def test_server_command_without_the_server_component_says_so(tmp_path):
    """A launcher copied outside any checkout is a client-only install."""
    launcher = tmp_path / "llm-tracker"
    launcher.write_text(LAUNCHER.read_text(encoding="utf-8"), encoding="utf-8")
    launcher.chmod(0o755)
    env = os.environ.copy()
    env["LLM_TRACKER_HOME"] = str(tmp_path / "tracker-home")
    env["LLM_TRACKER_BIN_DIR"] = str(tmp_path / "bin")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [str(launcher), "server", "status"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert result.returncode == 1
    assert "the server component is not installed on this machine" in result.stderr
    assert "install.sh" in result.stderr


def test_banner_is_suppressed_for_machine_readable_output(tmp_path):
    """`--json` output must stay parseable, so nothing decorates it."""
    result = _run_launcher(tmp_path, "status", "--json")

    assert result.returncode in (0, 1)
    assert "█" not in result.stdout
    assert "█" not in result.stderr
    # One compact line, so a caller can parse it directly.
    assert len(result.stdout.strip().splitlines()) == 1
    assert json.loads(result.stdout)["account"]["signed_in"] is False


def test_banner_prints_on_a_terminal(tmp_path):
    """Every human-facing command starts with the banner, on a real tty."""
    import pty

    env = os.environ.copy()
    env["LLM_TRACKER_HOME"] = str(tmp_path / "tracker-home")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["COLUMNS"] = "100"
    env.pop("NO_COLOR", None)

    controller, follower = pty.openpty()
    try:
        process = subprocess.Popen(
            [str(LAUNCHER), "--help"],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=follower,
            text=True,
        )
        os.close(follower)
        follower = None
        captured = _read_available(controller)
        process.wait(timeout=60)
    finally:
        if follower is not None:
            os.close(follower)
        os.close(controller)

    assert process.returncode == 0
    assert "\u2588" in captured  # the banner's block character
    # And it did not contaminate the child's stdout channel.
    assert "usage: llm-tracker" in process.stdout.read()


def _read_available(fd: str | int, limit: float = 5.0) -> str:
    import select

    chunks = []
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            break
        chunks.append(data.decode("utf-8", "replace"))
    return "".join(chunks)
