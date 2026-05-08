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

    (scripts_dir / "install.sh").write_text(
        textwrap.dedent(
            f"""
            #!/usr/bin/env bash
            set -euo pipefail
            mkdir -p "{home}/.local/bin" "{home}/.llm-tracker"
            cat > "{scripts_dir}/llm-tracker" <<'EOF'
            #!/usr/bin/env bash
            echo llm-tracker fake cli
            EOF
            chmod +x "{scripts_dir}/llm-tracker"
            ln -sf "{scripts_dir}/llm-tracker" "{home}/.local/bin/llm-tracker"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (scripts_dir / "install.sh").chmod(0o755)

    proxy_port, api_port, otlp_port = ports
    (scripts_dir / "start.sh").write_text(
        textwrap.dedent(
            f"""
            #!/usr/bin/env bash
            set -euo pipefail
            mkdir -p "{home}/.llm-tracker"
            cat > "{home}/.llm-tracker/config.yaml" <<'EOF'
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


def _make_fake_curl(
    tmp_path: Path, *, open_ports: set[int], setup_health: dict | None = None
) -> Path:
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
            SETUP_HEALTH = {json.dumps(setup_health)!r}

            args = sys.argv[1:]
            url = next((arg for arg in reversed(args) if arg.startswith("http://")), "")
            parsed = urlparse(url)
            port = parsed.port

            if port not in OPEN_PORTS:
                sys.exit(7)

            if parsed.path == "/local/setup-health":
                if SETUP_HEALTH == "null":
                    sys.exit(22)
                sys.stdout.write(SETUP_HEALTH)
                sys.exit(0)

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


def _add_fake_agent(bin_dir: Path, name: str) -> None:
    agent_path = bin_dir / name
    agent_path.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    agent_path.chmod(0o755)


def _run_bootstrap(
    fake_repo: Path,
    home: Path,
    bin_dir: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bin_dir}{os.pathsep}/bin{os.pathsep}/usr/bin",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["/bin/bash", str(fake_repo / "scripts" / "bootstrap.sh")],
        cwd=fake_repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
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
    gemini: dict,
) -> dict:
    expected_logs_endpoint = f"http://localhost:{otlp_port}/v1/logs"
    expected_endpoint = f"http://localhost:{otlp_port}"
    return {
        "expected": {
            "otlp_endpoint": expected_endpoint,
            "otlp_logs_endpoint": expected_logs_endpoint,
        },
        "summary": {
            "total_agents": 3,
            "configured_agents": sum(
                1 for agent in (claude, codex, gemini) if agent["configured"]
            ),
            "matching_agents": sum(
                1 for agent in (claude, codex, gemini) if agent["endpoint_matches"]
            ),
        },
        "agents": {
            "claude": claude,
            "codex": codex,
            "gemini": gemini,
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
        gemini=_agent_health(
            status="missing_config",
            expected_endpoint=f"http://localhost:{ports[2]}",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(
        tmp_path, open_ports=set(ports), setup_health=setup_health
    )
    result = _run_bootstrap(fake_repo, home, bin_dir)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "✅ llm-tracker bootstrap complete" in output
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
        gemini=_agent_health(
            status="ready",
            expected_endpoint=f"http://localhost:{ports[2]}",
            configured_endpoint=f"http://localhost:{ports[2]}",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(
        tmp_path, open_ports=set(ports), setup_health=setup_health
    )

    _add_fake_agent(bin_dir, "gemini")

    result = _run_bootstrap(fake_repo, home, bin_dir)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Agent tracking verification" in output
    assert "Claude: skipped" in output
    assert "Codex: skipped" in output
    assert "Gemini: ready" in output
    assert "Agent tracking: 1 ready, 2 skipped, 0 failed" in output


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
        gemini=_agent_health(
            status="ready",
            expected_endpoint=f"http://localhost:{ports[2]}",
            configured_endpoint=f"http://localhost:{ports[2]}",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(
        tmp_path, open_ports=set(ports), setup_health=setup_health
    )
    _add_fake_agent(bin_dir, "claude")
    _add_fake_agent(bin_dir, "codex")
    _add_fake_agent(bin_dir, "gemini")

    result = _run_bootstrap(fake_repo, home, bin_dir)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "Agent tracking verification" in output
    assert "Claude: OTLP not configured" in output
    assert "Codex: configured endpoint mismatch" in output
    assert "Gemini: ready" in output
    assert "Agent tracking: 1 ready, 0 skipped, 2 failed" in output
    assert secret_endpoint not in output


def test_bootstrap_skips_gemini_when_settings_file_exists_but_cli_is_missing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    gemini_settings = home / ".gemini" / "settings.json"
    gemini_settings.parent.mkdir(parents=True)
    gemini_settings.write_text('{"mcpServers": {}}\n', encoding="utf-8")

    ports = (4500, 4501, 4502)
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
        gemini=_agent_health(
            status="ready",
            expected_endpoint=f"http://localhost:{ports[2]}",
            configured_endpoint=f"http://localhost:{ports[2]}",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(
        tmp_path, open_ports=set(ports), setup_health=setup_health
    )

    result = _run_bootstrap(fake_repo, home, bin_dir)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Claude: skipped" in output
    assert "Codex: skipped" in output
    assert "Gemini: skipped" in output
    assert "Agent tracking: 0 ready, 3 skipped, 0 failed" in output


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

    result = _run_bootstrap(fake_repo, home, bin_dir)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "llm-tracker bootstrap finished with" in output
    assert "not responding" in output


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
        gemini=_agent_health(
            status="ready",
            expected_endpoint=f"http://localhost:{ports[2]}",
            configured_endpoint=f"http://localhost:{ports[2]}",
        ),
    )
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(
        tmp_path, open_ports=set(ports), setup_health=setup_health
    )

    result = _run_bootstrap(fake_repo, home, bin_dir)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Gemini: skipped" in output
    assert "Gemini: ready" not in output
    assert "Agent tracking: 0 ready, 3 skipped, 0 failed" in output
