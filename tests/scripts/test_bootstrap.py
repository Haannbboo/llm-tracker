from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


def _make_fake_bootstrap_repo(
    tmp_path: Path, home: Path, ports: tuple[int, int, int]
) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    fake_repo = tmp_path / "fake-repo"
    scripts_dir = fake_repo / "scripts"
    scripts_dir.mkdir(parents=True)

    shutil.copy2(repo_root / "scripts" / "bootstrap.sh", scripts_dir / "bootstrap.sh")
    (scripts_dir / "bootstrap.sh").chmod(0o755)

    lib_dir = scripts_dir / "lib"
    lib_dir.mkdir(parents=True)
    shutil.copy2(repo_root / "scripts" / "lib" / "terminal.sh", lib_dir / "terminal.sh")
    shutil.copy2(
        repo_root / "scripts" / "lib" / "requirements.sh", lib_dir / "requirements.sh"
    )

    # Create CLI wrapper directly (install logic is now inline in bootstrap.sh)
    (scripts_dir / "tokenage").write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "client" ]; then\n'
        '  case "${2:-}" in\n'
        "    start) exit 0 ;;\n"
        '    health) exec cat "${HOME}/health.json" ;;\n'
        "  esac\n"
        "fi\n"
        "echo tokenage fake cli\n",
        encoding="utf-8",
    )
    (scripts_dir / "tokenage").chmod(0o755)

    proxy_port, api_port, otlp_port = ports
    (scripts_dir / "start.sh").write_text(
        textwrap.dedent(
            f"""
            #!/usr/bin/env bash
            set -euo pipefail
            mkdir -p "{home}/.tokenage"
            cat > "{home}/.tokenage/config.yaml" <<'EOF'
            server:
              host: 127.0.0.1
              port: {proxy_port}
              api_port: {api_port}
              otlp_port: {otlp_port}
            EOF
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (scripts_dir / "start.sh").chmod(0o755)

    return fake_repo


def _make_fake_curl(tmp_path: Path, *, open_ports: set[int]) -> Path:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    curl_path = bin_dir / "curl"
    curl_path.write_text(
        textwrap.dedent(
            f"""
            #!/usr/bin/env python3
            import sys
            from urllib.parse import urlparse

            OPEN_PORTS = {sorted(open_ports)!r}

            args = sys.argv[1:]
            url = next((arg for arg in reversed(args) if arg.startswith("http://")), "")
            parsed = urlparse(url)
            port = parsed.port

            if port not in OPEN_PORTS:
                sys.exit(7)

            if "%{{content_type}}" in args:
                sys.stdout.write("text/html")
            elif "%{{http_code}}" in args:
                sys.stdout.write("200")
            sys.exit(0)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    curl_path.chmod(0o755)
    python_path = bin_dir / "python3"
    python_path.symlink_to(Path(sys.executable))
    return bin_dir


def _health_file(home: Path, setup_health: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "health.json").write_text(json.dumps(setup_health), encoding="utf-8")


def _add_fake_agent(bin_dir: Path, name: str) -> None:
    agent_path = bin_dir / name
    agent_path.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    agent_path.chmod(0o755)


def _run_bootstrap(
    fake_repo: Path,
    home: Path,
    bin_dir: Path,
    extra_env: dict[str, str] | None = None,
    setup_health: dict | None = None,
) -> subprocess.CompletedProcess:
    if setup_health is not None:
        _health_file(home, setup_health)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bin_dir}{os.pathsep}/bin{os.pathsep}/usr/bin",
        "TOKENAGE_SKIP_INSTALL": "1",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["/bin/bash", str(fake_repo / "scripts" / "bootstrap.sh")],
        cwd=fake_repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
    )


def _agent_health(
    *,
    status: str,
    expected_endpoint: str,
    configured_endpoint: str | None = None,
) -> dict:
    configured = configured_endpoint is not None
    return {
        "configured": configured,
        "endpoint_matches": status == "ready",
        "configured_endpoint": configured_endpoint,
        "expected_endpoint": expected_endpoint,
        "status": status,
    }


def _setup_health(
    *,
    otlp_port: int,
    claude: dict,
    codex: dict,
    opencode: dict | None = None,
    kilo: dict | None = None,
) -> dict:
    expected_logs_endpoint = f"http://localhost:{otlp_port}/v1/logs"
    expected_endpoint = f"http://localhost:{otlp_port}"
    opencode = opencode or _agent_health(
        status="missing_config",
        expected_endpoint=expected_logs_endpoint,
    )
    kilo = kilo or _agent_health(
        status="missing_config",
        expected_endpoint=expected_logs_endpoint,
    )
    return {
        "expected": {
            "otlp_endpoint": expected_endpoint,
            "otlp_logs_endpoint": expected_logs_endpoint,
        },
        "summary": {
            "total_agents": 4,
            "configured_agents": sum(
                1 for agent in (claude, codex, opencode, kilo) if agent["configured"]
            ),
            "matching_agents": sum(
                1
                for agent in (claude, codex, opencode, kilo)
                if agent["endpoint_matches"]
            ),
        },
        "agents": {
            "claude": claude,
            "codex": codex,
            "opencode": opencode,
            "kilo": kilo,
        },
    }


def test_bootstrap_succeeds_when_install_start_and_post_checks_pass(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    ports = (4100, 4101, 4102)
    setup_health = _setup_health(
        otlp_port=ports[2],
        claude=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
        codex=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(tmp_path, open_ports=set(ports))
    result = _run_bootstrap(fake_repo, home, bin_dir, setup_health=setup_health)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "tokenage is LIVE" in output
    assert f"API running: http://127.0.0.1:{ports[1]}" in output
    assert f"Proxy listening: http://127.0.0.1:{ports[0]}" in output
    assert f"OTLP listening: http://127.0.0.1:{ports[2]}" in output
    assert f"Dashboard: http://127.0.0.1:{ports[1]}" in output


def test_bootstrap_reports_local_setup_health_ready_and_skipped_agents(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    ports = (4200, 4201, 4202)
    setup_health = _setup_health(
        otlp_port=ports[2],
        claude=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
        codex=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
        kilo=_agent_health(
            status="ready",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
            configured_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(tmp_path, open_ports=set(ports))

    _add_fake_agent(bin_dir, "kilo")

    result = _run_bootstrap(fake_repo, home, bin_dir, setup_health=setup_health)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Verifying agent tracking" in output
    assert "Claude: skipped" in output
    assert "Codex: skipped" in output
    assert "OpenCode: skipped" in output
    assert "Kilo: ready" in output
    assert "Agents: 1 ready, 3 skipped, 0 failed" in output


def test_bootstrap_fails_when_detected_agent_setup_health_is_not_ready(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    claude_settings = home / ".claude" / "settings.json"
    codex_config = home / ".codex" / "config.toml"
    claude_settings.parent.mkdir(parents=True)
    codex_config.parent.mkdir(parents=True)
    claude_settings.write_text('{"env": {}}\n', encoding="utf-8")
    codex_config.write_text(
        textwrap.dedent(
            """
            [otel]
            enabled = true
            [otel.exporter.otlp-http]
            endpoint = "https://secret-token@example.invalid/v1/logs"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    secret_endpoint = "https://secret-token@example.invalid/v1/logs"
    ports = (4300, 4301, 4302)
    setup_health = _setup_health(
        otlp_port=ports[2],
        claude=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
        codex=_agent_health(
            status="wrong_endpoint",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
            configured_endpoint=secret_endpoint,
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(tmp_path, open_ports=set(ports))
    _add_fake_agent(bin_dir, "claude")
    _add_fake_agent(bin_dir, "codex")

    result = _run_bootstrap(fake_repo, home, bin_dir, setup_health=setup_health)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "Verifying agent tracking" in output
    assert "Claude: OTLP not configured" in output
    assert "Codex: endpoint mismatch" in output
    assert "OpenCode: skipped" in output
    assert "Kilo: skipped" in output
    assert "Agents: 0 ready, 2 skipped, 2 failed" in output
    assert secret_endpoint not in output


def test_bootstrap_exits_nonzero_when_post_start_checks_fail(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    ports = (4400, 4401, 4402)

    fake_repo = _make_fake_bootstrap_repo(
        tmp_path,
        home,
        ports=ports,
    )
    bin_dir = _make_fake_curl(tmp_path, open_ports=set())
    sleep_log = tmp_path / "sleep-calls.txt"
    fake_sleep = bin_dir / "sleep"
    fake_sleep.write_text(
        "#!/usr/bin/env sh\n"
        'if [ "$#" -eq 1 ] && [ "$1" = "1" ]; then\n'
        '  printf "%s\\n" "$1" >> "$TOKENAGE_TEST_SLEEP_LOG"\n'
        "  exit 0\n"
        "fi\n"
        'exec /bin/sleep "$@"\n',
        encoding="utf-8",
    )
    fake_sleep.chmod(0o755)

    result = _run_bootstrap(
        fake_repo,
        home,
        bin_dir,
        extra_env={"TOKENAGE_TEST_SLEEP_LOG": str(sleep_log)},
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "tokenage started with" in output
    assert "API reachable: http://127.0.0.1:4401 (not responding)" in output
    assert "Proxy listening: http://127.0.0.1:4400 (not responding)" in output
    assert "OTLP listening: http://127.0.0.1:4402 (not responding)" in output
    assert sleep_log.read_text(encoding="utf-8").splitlines() == ["1"] * 30


def test_bootstrap_skips_undetected_agent_even_when_setup_health_is_ready(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    ports = (4600, 4601, 4602)
    setup_health = _setup_health(
        otlp_port=ports[2],
        claude=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
        codex=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
        kilo=_agent_health(
            status="ready",
            expected_endpoint=f"http://localhost:{ports[2]}/v1/logs",
            configured_endpoint=f"http://localhost:{ports[2]}/v1/logs",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(tmp_path, open_ports=set(ports))

    result = _run_bootstrap(fake_repo, home, bin_dir, setup_health=setup_health)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Kilo: skipped" in output
    assert "Kilo: ready" not in output
    assert "OpenCode: skipped" in output
    assert "Agents: 0 ready, 4 skipped, 0 failed" in output
