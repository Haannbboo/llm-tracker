from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "configure-kilo-plugin.py"


def _make_project_root(tmp_path: Path, *, built: bool = True) -> Path:
    project_root = tmp_path / "repo"
    plugin_dir = project_root / "plugins" / "kilo"
    plugin_dir.mkdir(parents=True)
    if built:
        (plugin_dir / "node_modules").mkdir()
        (plugin_dir / "dist").mkdir()
        (plugin_dir / "dist" / "index.js").write_text(
            "export default async () => ({})\n",
            encoding="utf-8",
        )
    return project_root


def _run_configure(
    project_root: Path,
    home: Path,
    port: str = "4002",
    extra_env: dict[str, str] | None = None,
):
    env = {**os.environ, "HOME": str(home)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(project_root), port],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_configure_kilo_plugin_registers_endpoint(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    project_root = _make_project_root(tmp_path)

    result = _run_configure(project_root, home, "4102")

    assert result.returncode == 0, result.stderr
    # Script writes to the first existing config path, or opencode.json by default
    config_path = home / ".config" / "kilo" / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    plugin_entry = config["plugin"][0]
    assert plugin_entry == [
        str(project_root / "plugins" / "kilo" / "dist" / "index.js"),
        {"endpoint": "http://localhost:4102/v1/logs"},
    ]


def test_configure_kilo_plugin_updates_existing_entry(tmp_path):
    home = tmp_path / "home"
    config_path = home / ".config" / "kilo" / "opencode.json"
    config_path.parent.mkdir(parents=True)
    project_root = _make_project_root(tmp_path)
    plugin_path = str(project_root / "plugins" / "kilo" / "dist" / "index.js")
    config_path.write_text(
        json.dumps(
            {"plugin": [[plugin_path, {"endpoint": "http://localhost:9999/v1/logs"}]]}
        ),
        encoding="utf-8",
    )

    result = _run_configure(project_root, home, "4102")

    assert result.returncode == 0, result.stderr
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["plugin"] == [
        [plugin_path, {"endpoint": "http://localhost:4102/v1/logs"}]
    ]


def test_configure_kilo_plugin_skips_without_npm(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    project_root = _make_project_root(tmp_path, built=False)

    result = _run_configure(project_root, home, "4102", {"PATH": str(empty_bin)})

    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "WARNING: npm not found; skipping Kilo plugin configuration" in output
