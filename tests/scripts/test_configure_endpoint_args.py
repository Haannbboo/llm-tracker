"""Endpoint-argument tests for the configure-* wiring scripts (PR 3).

Each script accepts an optional trailing full-endpoint argument (contains
"://") that overrides PORT/HOST composition — used by `llm-tracker login`
to wire agents at a hosted HTTPS OTLP endpoint. Legacy argv must behave
identically to before.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"

ENDPOINT = "https://api.example.com:4005/v1/logs"


def _run(script: str, args: list[str], home: Path, extra_env=None):
    env = {**os.environ, "HOME": str(home)}
    env.pop("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), *args],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


def _make_built_plugin_root(tmp_path: Path, name: str) -> Path:
    project_root = tmp_path / "repo"
    plugin_dir = project_root / "plugins" / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "node_modules").mkdir()
    (plugin_dir / "dist").mkdir()
    (plugin_dir / "dist" / "index.js").write_text("export default async () => ({})\n")
    return project_root


# ------------------------------------------------------------------- claude


def test_claude_endpoint_arg(tmp_path):
    settings = tmp_path / "settings.json"
    result = _run(
        "configure-claude-settings.py",
        [str(settings), "4002", "localhost", ENDPOINT],
        home=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    env = json.loads(settings.read_text())["env"]
    assert env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == ENDPOINT


def test_claude_legacy_host_port(tmp_path):
    settings = tmp_path / "settings.json"
    result = _run(
        "configure-claude-settings.py",
        [str(settings), "4102", "otlp.example.com"],
        home=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    env = json.loads(settings.read_text())["env"]
    assert (
        env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"]
        == "http://otlp.example.com:4102/v1/logs"
    )


def test_claude_env_var_wins_over_endpoint_arg(tmp_path):
    settings = tmp_path / "settings.json"
    result = _run(
        "configure-claude-settings.py",
        [str(settings), "4002", "localhost", ENDPOINT],
        home=tmp_path,
        extra_env={"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://env.example:9/v1/logs"},
    )
    assert result.returncode == 0, result.stderr
    env = json.loads(settings.read_text())["env"]
    assert env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == "http://env.example:9/v1/logs"


def test_claude_wire_argv_shape_with_placeholder_port(tmp_path):
    # `llm-tracker login` wiring passes [SETTINGS, "0", "localhost", ENDPOINT]
    # — the endpoint must override the placeholder port/host, not compose
    # with them.
    settings = tmp_path / "settings.json"
    result = _run(
        "configure-claude-settings.py",
        [str(settings), "0", "localhost", ENDPOINT],
        home=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    env = json.loads(settings.read_text())["env"]
    assert env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == ENDPOINT


# -------------------------------------------------------------------- codex


def test_codex_endpoint_arg(tmp_path):
    config = tmp_path / "config.toml"
    result = _run(
        "configure-codex-settings.py",
        [str(config), "4002", "localhost", ENDPOINT],
        home=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    content = config.read_text()
    assert f'endpoint = "{ENDPOINT}"' in content


# --------------------------------------------------------- opencode / kilo


def test_opencode_endpoint_arg(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    project_root = _make_built_plugin_root(tmp_path, "opencode")
    result = _run(
        "configure-opencode-plugin.py",
        [str(project_root), "4005", "localhost", ENDPOINT],
        home=home,
    )
    assert result.returncode == 0, result.stderr
    config = json.loads((home / ".config" / "opencode" / "opencode.json").read_text())
    endpoints = [entry[1]["endpoint"] for entry in config["plugin"]]
    assert endpoints == [ENDPOINT]


def test_kilo_endpoint_arg(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    project_root = _make_built_plugin_root(tmp_path, "kilo")
    result = _run(
        "configure-kilo-plugin.py",
        [str(project_root), "4005", "localhost", ENDPOINT],
        home=home,
    )
    assert result.returncode == 0, result.stderr
    config = json.loads((home / ".config" / "kilo" / "opencode.json").read_text())
    endpoints = [entry[1]["endpoint"] for entry in config["plugin"]]
    assert endpoints == [ENDPOINT]
