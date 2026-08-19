from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "read-otlp-config.py"


def _run(tmp_path: Path, config: str, *args: str) -> str:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(config_path), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_endpoint_mode_preserves_https_base_url(tmp_path: Path):
    config = """
server:
  base_url: https://tracker.example/
  otlp_port: 4105
"""

    assert _run(tmp_path, config, "--endpoint") == (
        "https://tracker.example:4105/v1/logs"
    )


def test_endpoint_mode_uses_configured_port_for_origin_with_port_or_path(
    tmp_path: Path,
):
    for base_url in (
        "https://tracker.example:8443",
        "https://tracker.example/proxy",
    ):
        config = f"""
server:
  base_url: {base_url}
  otlp_port: 4105
"""

        assert _run(tmp_path, config, "--endpoint") == (
            "https://tracker.example:4105/v1/logs"
        )


def test_endpoint_mode_defaults_schemeless_base_url_to_http(tmp_path: Path):
    config = """
server:
  base_url: tracker.example
  otlp_port: 4105
"""

    assert _run(tmp_path, config, "--endpoint") == (
        "http://tracker.example:4105/v1/logs"
    )


def test_endpoint_mode_and_legacy_mode_preserve_ipv6_host(tmp_path: Path):
    config = """
server:
  base_url: https://[::1]
  otlp_port: 4105
"""

    assert _run(tmp_path, config, "--endpoint") == "https://[::1]:4105/v1/logs"
    assert _run(tmp_path, config) == "4105 [::1]"


def test_endpoint_mode_defaults_to_http_for_local_config(tmp_path: Path):
    config = """
server:
  host: 127.0.0.1
  otlp_port: 4105
"""

    assert _run(tmp_path, config, "--endpoint") == "http://localhost:4105/v1/logs"


def test_legacy_mode_still_returns_port_and_host(tmp_path: Path):
    config = """
server:
  base_url: https://tracker.example
  otlp_port: 4105
"""

    assert _run(tmp_path, config) == "4105 tracker.example"


def test_start_and_restart_pass_full_endpoint_to_agent_configurators():
    repo_root = Path(__file__).resolve().parents[2]
    configurators = (
        "configure-codex-settings.py",
        "configure-claude-settings.py",
        "configure-opencode-plugin.py",
        "configure-kilo-plugin.py",
    )

    for script_name in ("start.sh", "restart.sh"):
        script = (repo_root / "scripts" / script_name).read_text(encoding="utf-8")
        assert 'read-otlp-config.py" "${CONFIG_PATH}" --endpoint' in script
        for configurator in configurators:
            assert f"{configurator}" in script
        assert script.count('"${OTLP_ENDPOINT}"') == 4
