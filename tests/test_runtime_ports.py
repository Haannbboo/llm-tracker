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


def test_strict_checker_output_is_empty_when_only_non_blocking_issues():
    checker_path = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "scripts"
        / "check-service-ports.py"
    )
    source = checker_path.read_text(encoding="utf-8")

    assert "output_issues = blocking_issues if args.strict else issues" in source
    assert "if not output_issues:" in source


def test_start_and_restart_check_port_conflicts_before_migrations():
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[1]
    start_script = (repo_root / "scripts" / "start.sh").read_text(encoding="utf-8")
    restart_script = (repo_root / "scripts" / "restart.sh").read_text(encoding="utf-8")

    assert start_script.index(
        'if ! "${PYTHON}" "${PORT_CHECKER}"'
    ) < start_script.index("migrate_schema.py")
    assert restart_script.index(
        'if ! "${PYTHON}" "${PORT_CHECKER}"'
    ) < restart_script.index("migrate_schema.py")
