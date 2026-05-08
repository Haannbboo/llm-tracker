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


def test_start_and_restart_check_port_conflicts_before_migrations():
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    start_script = (repo_root / "scripts" / "start.sh").read_text(encoding="utf-8")
    restart_script = (repo_root / "scripts" / "restart.sh").read_text(encoding="utf-8")

    assert start_script.index("PORT_CHECKER") < start_script.index("migrate_schema.py")
    assert restart_script.index(
        'if ! "${PYTHON}" "${PORT_CHECKER}"'
    ) < restart_script.index("migrate_schema.py")


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
