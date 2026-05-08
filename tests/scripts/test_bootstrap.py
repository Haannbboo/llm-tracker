from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):  # noqa: A002
        return


class _HttpProbeServer:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


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


def test_bootstrap_succeeds_when_install_start_and_post_checks_pass(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    with (
        _HttpProbeServer() as proxy,
        _HttpProbeServer() as api,
        _HttpProbeServer() as otlp,
    ):
        fake_repo = _make_fake_bootstrap_repo(
            tmp_path,
            home,
            ports=(proxy.port, api.port, otlp.port),
        )

        result = subprocess.run(
            ["bash", str(fake_repo / "scripts" / "bootstrap.sh")],
            cwd=fake_repo,
            env={**os.environ, "HOME": str(home)},
            text=True,
            capture_output=True,
            timeout=20,
        )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "✅ llm-tracker bootstrap complete" in output
    assert f"API running: http://127.0.0.1:{api.port}" in output
    assert f"Proxy listening: http://127.0.0.1:{proxy.port}" in output
    assert f"OTLP listening: http://127.0.0.1:{otlp.port}" in output


def test_bootstrap_exits_nonzero_when_post_start_checks_fail(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    fake_repo = _make_fake_bootstrap_repo(
        tmp_path,
        home,
        ports=(9, 9, 9),
    )

    result = subprocess.run(
        ["bash", str(fake_repo / "scripts" / "bootstrap.sh")],
        cwd=fake_repo,
        env={**os.environ, "HOME": str(home)},
        text=True,
        capture_output=True,
        timeout=20,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "llm-tracker bootstrap finished with" in output
    assert "not responding" in output
