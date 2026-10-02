import pytest


def test_detect_port_issues_flags_preflight_conflict(runtime_ports_module):
    service_ports = [
        runtime_ports_module.ServicePort(
            service="API",
            program="llm-tracker-api",
            host="127.0.0.1",
            port=4001,
        )
    ]
    listeners_by_port = {
        4001: [runtime_ports_module.PortListener(pid=18431, command="QQ")]
    }

    issues = runtime_ports_module.detect_port_issues(
        service_ports=service_ports,
        supervisor_states={},
        listeners_by_port=listeners_by_port,
    )

    assert len(issues) == 1
    assert issues[0] == runtime_ports_module.PortIssue(
        service="API",
        program="llm-tracker-api",
        host="127.0.0.1",
        port=4001,
        kind="occupied_by_other_process",
        listener_pid=18431,
        listener_command="QQ",
        expected_pid=None,
    )


def test_detect_port_issues_flags_running_service_owned_by_other_process(
    runtime_ports_module,
):
    service_ports = [
        runtime_ports_module.ServicePort(
            service="API",
            program="llm-tracker-api",
            host="127.0.0.1",
            port=4001,
        )
    ]
    supervisor_states = {
        "llm-tracker-api": runtime_ports_module.SupervisorProgramState(
            status="RUNNING",
            pid=76037,
        )
    }
    listeners_by_port = {
        4001: [runtime_ports_module.PortListener(pid=18431, command="QQ")]
    }

    issues = runtime_ports_module.detect_port_issues(
        service_ports=service_ports,
        supervisor_states=supervisor_states,
        listeners_by_port=listeners_by_port,
    )

    assert len(issues) == 1
    assert issues[0] == runtime_ports_module.PortIssue(
        service="API",
        program="llm-tracker-api",
        host="127.0.0.1",
        port=4001,
        kind="occupied_by_unexpected_process",
        listener_pid=18431,
        listener_command="QQ",
        expected_pid=76037,
    )


def test_detect_port_issues_allows_running_service_on_expected_port(
    runtime_ports_module,
):
    service_ports = [
        runtime_ports_module.ServicePort(
            service="API",
            program="llm-tracker-api",
            host="127.0.0.1",
            port=4001,
        )
    ]
    supervisor_states = {
        "llm-tracker-api": runtime_ports_module.SupervisorProgramState(
            status="RUNNING",
            pid=76037,
        )
    }
    listeners_by_port = {
        4001: [runtime_ports_module.PortListener(pid=76037, command="Python")]
    }

    issues = runtime_ports_module.detect_port_issues(
        service_ports=service_ports,
        supervisor_states=supervisor_states,
        listeners_by_port=listeners_by_port,
    )

    assert issues == []


def test_get_blocking_port_issues_ignores_not_listening(runtime_ports_module):
    issues = [
        runtime_ports_module.PortIssue(
            service="API",
            program="llm-tracker-api",
            host="127.0.0.1",
            port=4004,
            kind="not_listening",
            listener_pid=None,
            listener_command=None,
            expected_pid=342,
        )
    ]

    assert runtime_ports_module.get_blocking_port_issues(issues) == []


def test_get_configured_service_ports_prefers_otlp_endpoint_env(
    runtime_ports_module, monkeypatch
):
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "http://127.0.0.1:49153/v1/logs",
    )

    service_ports = runtime_ports_module.get_configured_service_ports(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 4000,
                "api_port": 4001,
                "otlp_port": 4005,
            }
        }
    )

    assert service_ports[-1] == runtime_ports_module.ServicePort(
        "OTLP",
        "llm-tracker-otlp",
        "127.0.0.1",
        49153,
    )


def test_get_configured_service_ports_uses_configured_otlp_port_without_env(
    runtime_ports_module, monkeypatch
):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)

    service_ports = runtime_ports_module.get_configured_service_ports(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 4000,
                "api_port": 4001,
                "otlp_port": 4005,
            }
        }
    )

    assert service_ports[-1] == runtime_ports_module.ServicePort(
        "OTLP",
        "llm-tracker-otlp",
        "127.0.0.1",
        4005,
    )


def test_auto_assign_ports_rewrites_config_when_defaults_are_busy(tmp_path):
    import importlib.util
    import socket

    import yaml

    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "auto-assign-ports.py"
    spec = importlib.util.spec_from_file_location("auto_assign_ports", script_path)
    auto_assign_ports = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(auto_assign_ports)

    listeners = []
    busy_ports = []
    for _ in range(3):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        busy_ports.append(sock.getsockname()[1])
        listeners.append(sock)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "server:\n"
        "  host: 127.0.0.1\n"
        f"  port: {busy_ports[0]}\n"
        f"  api_port: {busy_ports[1]}\n"
        f"  otlp_port: {busy_ports[2]}\n",
        encoding="utf-8",
    )

    try:
        code = auto_assign_ports.main(
            [
                "--config",
                str(config_path),
                "--start-port",
                str(min(busy_ports)),
                "--search-limit",
                "200",
            ]
        )
    finally:
        for sock in listeners:
            sock.close()

    assert code == 0
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["server"]["port"] not in busy_ports
    assert config["server"]["api_port"] not in busy_ports
    assert config["server"]["otlp_port"] not in busy_ports
    assert (
        len(
            {
                config["server"]["port"],
                config["server"]["api_port"],
                config["server"]["otlp_port"],
            }
        )
        == 3
    )


def test_start_auto_assigns_ports_only_for_newly_created_config():
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    start_script = (repo_root / "scripts" / "start.sh").read_text(encoding="utf-8")

    assert "CONFIG_WAS_CREATED=0" in start_script
    assert "CONFIG_WAS_CREATED=1" in start_script
    assert 'if [[ "${CONFIG_WAS_CREATED}" -eq 1 ]]; then' in start_script
    assert 'printf "%s\\n" "${PORT_CHECK_OUTPUT}"' in start_script
    assert "exit 1" in start_script


def test_check_service_ports_strict_mode_reports_only_blocking_issues():
    checker_path = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "scripts"
        / "check-service-ports.py"
    )
    source = checker_path.read_text(encoding="utf-8")

    assert "output_issues = blocking_issues if args.strict else issues" in source
    assert "if not output_issues:" in source


def test_start_and_restart_never_configure_agents():
    """Agent wiring is the client's job: `llm-tracker setup` / `llm-tracker login`."""
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    start_script = (repo_root / "scripts" / "start.sh").read_text(encoding="utf-8")
    restart_script = (repo_root / "scripts" / "restart.sh").read_text(encoding="utf-8")

    for script in (start_script, restart_script):
        for configurator in (
            "configure-codex-settings.py",
            "configure-claude-settings.py",
            "configure-opencode-plugin.py",
            "configure-kilo-plugin.py",
        ):
            assert configurator not in script
        assert "command -v codex" not in script
        assert "command -v claude" not in script
        assert "gemini" not in script


def test_restart_persists_otlp_port_before_restarting_collector(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    root = tmp_path / "checkout"
    scripts = root / "scripts"
    (scripts / "lib").mkdir(parents=True)
    shutil.copy(repo_root / "scripts" / "restart.sh", scripts / "restart.sh")
    shutil.copy(
        repo_root / "scripts" / "lib" / "terminal.sh", scripts / "lib" / "terminal.sh"
    )
    (scripts / "migrate_schema.py").write_text("pass\n")
    (scripts / "read-otlp-config.py").write_text("print('5505 localhost')\n")

    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    python = venv_bin / "python"
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    python.chmod(0o755)
    supervisorctl = venv_bin / "supervisorctl"
    supervisorctl.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$SUPERVISOR_LOG"\n'
        'if [ "$3" = status ]; then printf \'%s\\n\' "$4 RUNNING pid 123, uptime 0:00:01"; fi\n'
    )
    supervisorctl.chmod(0o755)

    home = tmp_path / "home with spaces"
    config_dir = home / ".llm-tracker"
    config_dir.mkdir(parents=True)
    (config_dir / "supervisord.conf").write_text("[supervisord]\n")
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        "server:\n  host: 127.0.0.1\n  port: 4100\n  otlp_port: 4002\n"
        "db:\n  path: keep.db\n",
        encoding="utf-8",
    )
    config_path.chmod(0o600)
    supervisor_log = tmp_path / "supervisor.log"

    result = subprocess.run(
        ["bash", str(scripts / "restart.sh"), "--otlp-port", "5505"],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "HOME": str(home),
            "SUPERVISOR_LOG": str(supervisor_log),
            "NO_COLOR": "1",
        },
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["server"]["otlp_port"] == 5505
    assert config["server"]["port"] == 4100
    assert config["db"]["path"] == "keep.db"
    assert config_path.stat().st_mode & 0o777 == 0o600
    calls = supervisor_log.read_text(encoding="utf-8").splitlines()
    assert any(call.endswith("restart llm-tracker-otlp") for call in calls)
    assert any(call.endswith("signal HUP llm-tracker-api") for call in calls)
    assert "OTLP port saved as 5505" in result.stdout


def test_start_checks_port_conflicts_before_migrations():
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    start_script = (repo_root / "scripts" / "start.sh").read_text(encoding="utf-8")

    assert start_script.index("PORT_CHECKER") < start_script.index("migrate_schema.py")


def test_restart_runs_migrations_without_port_check():
    """restart.sh is a reload, not a start: no port check, but still migrates."""
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    restart_script = (repo_root / "scripts" / "restart.sh").read_text(encoding="utf-8")

    assert "check-service-ports.py" not in restart_script
    assert "auto-assign-ports.py" not in restart_script
    assert "migrate_schema.py" in restart_script


# ── Fake install harness for start.sh ──────────────────────────────
#
# start.sh is a shell script, so the only honest test is to run it. The repo is
# copied into tmp_path, given a stub `.venv` whose `bin/python` dispatches known
# helper scripts to stubs (and to the real interpreter for anything else), plus
# an isolated HOME with fake agent CLIs on PATH. Nothing touches the real HOME.

_AGENT_CONFIG_PATHS = (
    ".codex/config.toml",
    ".claude/settings.json",
    ".config/opencode/opencode.json",
    ".config/kilo/config.json",
    ".gemini/settings.json",
)

# Ports the auto-assign stub below writes into config.yaml, replacing the
# defaults from config.example.yaml.
_ASSIGNED_PORTS = {"port": 4100, "api_port": 4101, "otlp_port": 4102}

_PYTHON_WRAPPER_PORTS_FREE = """\
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  */sync-config.py|*/check-service-ports.py|*/migrate_schema.py|*/auto-assign-ports.py)
    exit 0
    ;;
  -c)
    printf '4002\\n'
    exit 0
    ;;
esac
exec @PYTHON@ "$@"
"""

# Fails the first --strict port check, so start.sh takes the auto-assign path.
_PYTHON_WRAPPER_PORTS_BUSY = """\
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  */sync-config.py|*/migrate_schema.py)
    exit 0
    ;;
  */check-service-ports.py)
    if [[ ! -f "${HOME}/.llm-tracker/.port-check-failed" ]]; then
      mkdir -p "${HOME}/.llm-tracker"
      touch "${HOME}/.llm-tracker/.port-check-failed"
      echo "defaults busy" >&2
      exit 1
    fi
    exit 0
    ;;
  */auto-assign-ports.py)
    exec @PYTHON@ - "$@" <<'PY'
import pathlib
import sys
import yaml
config = pathlib.Path(sys.argv[sys.argv.index("--config") + 1])
data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
data.setdefault("server", {}).update(@PORTS@)
config.write_text(yaml.safe_dump(data), encoding="utf-8")
PY
    ;;
esac
exec @PYTHON@ "$@"
"""


def _fake_install(tmp_path, python_wrapper, stamp=None):
    import hashlib
    import os
    import shutil
    import sys

    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    fake_repo = tmp_path / "repo"
    shutil.copytree(
        repo_root,
        fake_repo,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "logs",
            "frontend/node_modules",
            ".pytest_cache",
            "__pycache__",
        ),
    )

    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    venv_bin = fake_repo / ".venv" / "bin"
    home.mkdir()
    fake_bin.mkdir()
    venv_bin.mkdir(parents=True)

    # Installed agents: start.sh must leave them alone.
    for agent in ("codex", "claude"):
        agent_path = fake_bin / agent
        agent_path.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        agent_path.chmod(0o755)

    wrapper = venv_bin / "python"
    wrapper.write_text(
        python_wrapper.replace("@PYTHON@", sys.executable).replace(
            "@PORTS@", repr(_ASSIGNED_PORTS)
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    for name in ("supervisord", "supervisorctl"):
        stub = venv_bin / name
        stub.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)

    if stamp is None:
        stamp = hashlib.sha256(
            (fake_repo / "requirements.txt").read_bytes()
        ).hexdigest()
    (fake_repo / ".venv" / ".requirements.sha256").write_text(
        stamp + "\n", encoding="utf-8"
    )

    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{fake_bin}{os.pathsep}/bin{os.pathsep}/usr/bin",
        "PYTHONPATH": str(fake_repo),
    }
    return fake_repo, home, env


def _run_start(fake_repo, env, timeout=20):
    import subprocess

    result = subprocess.run(
        ["/bin/bash", str(fake_repo / "scripts" / "start.sh")],
        cwd=fake_repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return result, result.stdout + result.stderr


def _agent_config_state(home):
    import pathlib

    return {rel: (pathlib.Path(home) / rel).exists() for rel in _AGENT_CONFIG_PATHS}


@pytest.mark.slow
def test_start_creates_config_from_example_and_leaves_home_agents_alone(tmp_path):
    """start.sh bootstraps its own config, and never edits agent settings."""
    import os

    import yaml

    real_home = __import__("pathlib").Path(os.environ["HOME"]).resolve()
    real_before = _agent_config_state(real_home)

    fake_repo, home, env = _fake_install(tmp_path, _PYTHON_WRAPPER_PORTS_FREE)
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text('model = "gpt-5"\n', encoding="utf-8")

    result, output = _run_start(fake_repo, env)
    assert result.returncode == 0, output
    assert "Config created" in output
    assert "Port check passed" in output

    config = yaml.safe_load(
        (home / ".llm-tracker" / "config.yaml").read_text(encoding="utf-8")
    )
    example = yaml.safe_load(
        (fake_repo / "config.example.yaml").read_text(encoding="utf-8")
    )
    assert config["server"]["port"] == example["server"]["port"]
    assert config["server"]["api_port"] == example["server"]["api_port"]

    # Installed agents stay unconfigured; absent agent dirs stay absent.
    assert (home / ".codex" / "config.toml").read_text(encoding="utf-8") == (
        'model = "gpt-5"\n'
    )
    for rel in _AGENT_CONFIG_PATHS[1:]:
        assert not (home / rel).exists(), rel
    assert _agent_config_state(real_home) == real_before


@pytest.mark.slow
def test_start_records_auto_assigned_ports_and_leaves_home_agents_alone(tmp_path):
    """Regression: auto-assign on a fresh config must land in config.yaml."""
    import os

    import yaml

    real_home = __import__("pathlib").Path(os.environ["HOME"]).resolve()
    real_before = _agent_config_state(real_home)

    fake_repo, home, env = _fake_install(tmp_path, _PYTHON_WRAPPER_PORTS_BUSY)
    (home / ".codex").mkdir()

    result, output = _run_start(fake_repo, env)
    assert result.returncode == 0, output
    assert "Ports auto-assigned" in output

    config = yaml.safe_load(
        (home / ".llm-tracker" / "config.yaml").read_text(encoding="utf-8")
    )
    for key, port in _ASSIGNED_PORTS.items():
        assert config["server"][key] == port

    for rel in _AGENT_CONFIG_PATHS[1:]:
        assert not (home / rel).exists(), rel
    assert not (home / ".codex" / "config.toml").exists()
    assert _agent_config_state(real_home) == real_before


@pytest.mark.slow
def test_start_refuses_to_run_when_requirements_stamp_is_stale(tmp_path):
    """start.sh no longer installs; a stale stamp must stop it, pointing at bootstrap."""
    fake_repo, home, env = _fake_install(
        tmp_path, _PYTHON_WRAPPER_PORTS_FREE, stamp="0" * 64
    )

    result, output = _run_start(fake_repo, env)

    assert result.returncode == 1, output
    assert "Dependencies are out of date" in output
    assert "run llm-tracker server bootstrap" in output
    assert not (home / ".llm-tracker" / "config.yaml").exists()


# ---------------------------------------------------------------------------
# _parse_otlp_endpoint
# ---------------------------------------------------------------------------


def test_parse_otlp_endpoint_valid(runtime_ports_module):
    result = runtime_ports_module._parse_otlp_endpoint("http://127.0.0.1:49153/v1/logs")
    assert result == ("127.0.0.1", 49153)


def test_parse_otlp_endpoint_missing_port(runtime_ports_module):
    result = runtime_ports_module._parse_otlp_endpoint("http://127.0.0.1/v1/logs")
    assert result is None


def test_parse_otlp_endpoint_invalid_url(runtime_ports_module):
    result = runtime_ports_module._parse_otlp_endpoint("not-a-url")
    assert result is None


def test_parse_otlp_endpoint_empty_string(runtime_ports_module):
    result = runtime_ports_module._parse_otlp_endpoint("")
    assert result is None


# ---------------------------------------------------------------------------
# parse_supervisor_status
# ---------------------------------------------------------------------------


def test_parse_supervisor_status_empty_string(runtime_ports_module):
    assert runtime_ports_module.parse_supervisor_status("") == {}


def test_parse_supervisor_status_single_program_with_pid(runtime_ports_module):
    result = runtime_ports_module.parse_supervisor_status(
        "llm-tracker-proxy RUNNING pid 1234"
    )
    assert result == {
        "llm-tracker-proxy": runtime_ports_module.SupervisorProgramState(
            status="RUNNING",
            pid=1234,
        )
    }


def test_parse_supervisor_status_program_without_pid(runtime_ports_module):
    result = runtime_ports_module.parse_supervisor_status("llm-tracker-proxy STOPPED")
    assert result == {
        "llm-tracker-proxy": runtime_ports_module.SupervisorProgramState(
            status="STOPPED",
            pid=None,
        )
    }


def test_parse_supervisor_status_multiple_programs(runtime_ports_module):
    text = (
        "llm-tracker-proxy RUNNING pid 100\n"
        "llm-tracker-api RUNNING pid 200\n"
        "llm-tracker-otlp STOPPED\n"
    )
    result = runtime_ports_module.parse_supervisor_status(text)
    assert result == {
        "llm-tracker-proxy": runtime_ports_module.SupervisorProgramState(
            status="RUNNING", pid=100
        ),
        "llm-tracker-api": runtime_ports_module.SupervisorProgramState(
            status="RUNNING", pid=200
        ),
        "llm-tracker-otlp": runtime_ports_module.SupervisorProgramState(
            status="STOPPED", pid=None
        ),
    }


# ---------------------------------------------------------------------------
# format_port_issue
# ---------------------------------------------------------------------------


def test_format_port_issue_not_listening(runtime_ports_module):
    issue = runtime_ports_module.PortIssue(
        service="API",
        program="llm-tracker-api",
        host="127.0.0.1",
        port=4001,
        kind="not_listening",
        listener_pid=None,
        listener_command=None,
        expected_pid=76037,
    )
    text = runtime_ports_module.format_port_issue(issue)
    assert "expected" in text
    assert "llm-tracker-api" in text
    assert "pid 76037" in text
    assert "nothing is listening" in text


def test_format_port_issue_occupied_by_unexpected_process(runtime_ports_module):
    issue = runtime_ports_module.PortIssue(
        service="API",
        program="llm-tracker-api",
        host="127.0.0.1",
        port=4001,
        kind="occupied_by_unexpected_process",
        listener_pid=18431,
        listener_command="QQ",
        expected_pid=76037,
    )
    text = runtime_ports_module.format_port_issue(issue)
    assert "owned by" in text
    assert "QQ (pid 18431)" in text
    assert "not llm-tracker-api pid 76037" in text


def test_format_port_issue_occupied_by_other_process(runtime_ports_module):
    issue = runtime_ports_module.PortIssue(
        service="API",
        program="llm-tracker-api",
        host="127.0.0.1",
        port=4001,
        kind="occupied_by_other_process",
        listener_pid=18431,
        listener_command="QQ",
        expected_pid=None,
    )
    text = runtime_ports_module.format_port_issue(issue)
    assert "already owned by" in text
    assert "QQ (pid 18431)" in text
    assert "llm-tracker-api cannot bind" in text


# ---------------------------------------------------------------------------
# detect_port_issues edge cases
# ---------------------------------------------------------------------------


def test_detect_port_issues_stopped_program_with_listeners(runtime_ports_module):
    service_ports = [
        runtime_ports_module.ServicePort(
            service="API",
            program="llm-tracker-api",
            host="127.0.0.1",
            port=4001,
        )
    ]
    supervisor_states = {
        "llm-tracker-api": runtime_ports_module.SupervisorProgramState(
            status="STOPPED",
            pid=None,
        )
    }
    listeners_by_port = {
        4001: [runtime_ports_module.PortListener(pid=5555, command="nginx")]
    }

    issues = runtime_ports_module.detect_port_issues(
        service_ports=service_ports,
        supervisor_states=supervisor_states,
        listeners_by_port=listeners_by_port,
    )

    assert len(issues) == 1
    assert issues[0] == runtime_ports_module.PortIssue(
        service="API",
        program="llm-tracker-api",
        host="127.0.0.1",
        port=4001,
        kind="occupied_by_other_process",
        listener_pid=5555,
        listener_command="nginx",
        expected_pid=None,
    )


def test_detect_port_issues_empty_service_ports(runtime_ports_module):
    issues = runtime_ports_module.detect_port_issues(
        service_ports=[],
        supervisor_states={
            "llm-tracker-api": runtime_ports_module.SupervisorProgramState(
                status="RUNNING", pid=100
            )
        },
        listeners_by_port={
            4001: [runtime_ports_module.PortListener(pid=999, command="X")]
        },
    )
    assert issues == []


def test_detect_port_issues_multiple_listeners_uses_first(runtime_ports_module):
    service_ports = [
        runtime_ports_module.ServicePort(
            service="API",
            program="llm-tracker-api",
            host="127.0.0.1",
            port=4001,
        )
    ]
    supervisor_states = {
        "llm-tracker-api": runtime_ports_module.SupervisorProgramState(
            status="RUNNING",
            pid=76037,
        )
    }
    listeners_by_port = {
        4001: [
            runtime_ports_module.PortListener(pid=1111, command="first"),
            runtime_ports_module.PortListener(pid=2222, command="second"),
        ]
    }

    issues = runtime_ports_module.detect_port_issues(
        service_ports=service_ports,
        supervisor_states=supervisor_states,
        listeners_by_port=listeners_by_port,
    )

    assert len(issues) == 1
    assert issues[0].listener_pid == 1111
    assert issues[0].listener_command == "first"
    assert issues[0].kind == "occupied_by_unexpected_process"
