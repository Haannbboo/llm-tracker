from __future__ import annotations

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

    # Any call into the launcher is recorded: bootstrap must never make one.
    (scripts_dir / "tokenage").write_text(
        f'#!/usr/bin/env bash\necho "$@" >> "{home}/launcher-calls"\n',
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


def test_bootstrap_verifies_the_server_only_and_never_touches_a_client(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    ports = (4100, 4101, 4102)
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(tmp_path, open_ports=set(ports))
    result = _run_bootstrap(fake_repo, home, bin_dir)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "tokenage is LIVE" in output
    assert f"API running: http://127.0.0.1:{ports[1]}" in output
    assert f"Proxy listening: http://127.0.0.1:{ports[0]}" in output
    assert f"OTLP listening: http://127.0.0.1:{ports[2]}" in output
    assert f"Dashboard: http://127.0.0.1:{ports[1]}" in output
    assert "agent" not in output.lower()
    assert not (home / "launcher-calls").exists()
    assert (home / ".local" / "bin" / "tokenage").is_symlink()


def test_bootstrap_leaves_an_existing_launcher_alone(tmp_path):
    home = tmp_path / "home"
    ports = (4110, 4111, 4112)
    launcher = home / ".local" / "bin" / "tokenage"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# tokenage launcher\n")
    fake_repo = _make_fake_bootstrap_repo(tmp_path, home, ports=ports)
    bin_dir = _make_fake_curl(tmp_path, open_ports=set(ports))

    result = _run_bootstrap(fake_repo, home, bin_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not launcher.is_symlink()
    assert launcher.read_text() == "# tokenage launcher\n"


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
