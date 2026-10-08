"""OpenCode / Kilo plugin registration (``client/agents/{opencode,kilo}.py``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from client.agents import kilo, opencode, plugin

AGENTS = {"opencode": opencode, "kilo": kilo}
ENDPOINT = "http://localhost:4102/v1/logs"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


def _project(tmp_path: Path, name: str, *, built: bool = True) -> Path:
    root = tmp_path / "repo"
    plugin_dir = root / "plugins" / name
    plugin_dir.mkdir(parents=True)
    if built:
        (plugin_dir / "node_modules").mkdir()
        (plugin_dir / "dist").mkdir()
        (plugin_dir / "dist" / "index.js").write_text(
            "export default async () => ({})\n"
        )
    return root


def _config(tmp_path: Path, name: str) -> Path:
    return tmp_path / ".config" / name / "opencode.json"


@pytest.mark.parametrize("name", AGENTS)
def test_registers_endpoint_and_token(tmp_path, name):
    root = _project(tmp_path, name)
    assert AGENTS[name].configure(root, ENDPOINT, "ingest-secret") == 0
    config = json.loads(_config(tmp_path, name).read_text())
    assert config["plugin"] == [
        [
            str(root / "plugins" / name / "dist" / "index.js"),
            {"endpoint": ENDPOINT, "token": "ingest-secret"},
        ]
    ]


@pytest.mark.parametrize("name", AGENTS)
def test_replaces_every_other_tracker_build_and_keeps_user_plugins(tmp_path, name):
    root = _project(tmp_path, name)
    path = str(root / "plugins" / name / "dist" / "index.js")
    _config(tmp_path, name).parent.mkdir(parents=True)
    _config(tmp_path, name).write_text(
        json.dumps(
            {
                "plugin": [
                    [
                        f"/old/worktree/plugins/{name}/dist/index.js",
                        {"endpoint": "http://localhost:4005/v1/logs"},
                    ],
                    "user-plugin",
                    [path, {"endpoint": "http://localhost:9999/v1/logs", "token": "t"}],
                ]
            }
        )
    )
    assert AGENTS[name].configure(root, ENDPOINT, None) == 0
    config = json.loads(_config(tmp_path, name).read_text())
    assert config["plugin"] == ["user-plugin", [path, {"endpoint": ENDPOINT}]]


@pytest.mark.parametrize("name", AGENTS)
def test_skips_without_npm(tmp_path, monkeypatch, name, capsys):
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    root = _project(tmp_path, name, built=False)
    assert AGENTS[name].configure(root, ENDPOINT, None) == 2
    assert "npm not found" in capsys.readouterr().err
    assert not _config(tmp_path, name).exists()


@pytest.mark.parametrize("name", AGENTS)
def test_build_timeout_is_a_failure_not_a_hang(tmp_path, monkeypatch, name, capsys):
    import subprocess

    def hang(*args, **kwargs):
        assert kwargs["timeout"] == plugin.BUILD_TIMEOUT
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(plugin.subprocess, "run", hang)
    root = _project(tmp_path, name, built=False)
    assert AGENTS[name].configure(root, ENDPOINT, None) == 1
    assert "timed out" in capsys.readouterr().err
