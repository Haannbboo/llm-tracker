#!/usr/bin/env python3
"""Configure the tokenage plugin for OpenCode.

Usage: configure-opencode-plugin.py PROJECT_ROOT [OTLP_PORT]

The plugin registers itself in the OpenCode config as a tracked plugin
so that tokenage's health endpoint can detect it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_GRAY = "\033[38;2;102;102;102m" if sys.stdout.isatty() else ""
_RESET = "\033[0m" if sys.stdout.isatty() else ""


def _info(msg: str) -> None:
    print(f"  {_GRAY}{msg}{_RESET}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read OpenCode configuration; left unchanged") from exc
    if not isinstance(data, dict) or (
        "plugin" in data and not isinstance(data["plugin"], list)
    ):
        raise ValueError("invalid OpenCode configuration; left unchanged")
    return data


def load_ingest_token() -> str | None:
    try:
        credentials = json.loads(
            (Path.home() / ".tokenage" / "credentials.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    token = credentials.get("ingest_token") if isinstance(credentials, dict) else None
    return token if isinstance(token, str) and token else None


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2) + "\n"
    if path.exists():
        path.chmod(0o600)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def warn_skip(message: str, *, failed: bool = False) -> int:
    print(
        f"WARNING: {message}; skipping OpenCode plugin configuration", file=sys.stderr
    )
    return 1 if failed else 2


def run_npm(
    args: list[str], plugin_dir: Path
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["npm", *args],
            cwd=plugin_dir,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None


OPENCODE_CONFIG_PATHS = [
    Path.home() / ".config" / "opencode" / "opencode.json",
]


def select_config_path() -> Path:
    """Return the OpenCode config path, creating it if needed."""
    return OPENCODE_CONFIG_PATHS[0]


def _disable(config_path: Path, expected_endpoint: str | None) -> int:
    """Remove tracker entries for the expected collector, preserving others.

    Plugin entries are identified by build path and collector endpoint. The
    built dist/ is left in place: rebuilding is cheaper than being wrong.
    """
    if not expected_endpoint:
        print(
            "collector unknown; OpenCode configuration left unchanged", file=sys.stderr
        )
        return 2
    if not config_path.exists():
        _info(f"No OpenCode config at {config_path}")
        return 2
    config = load_json(config_path)
    plugins = config.get("plugin")
    if not isinstance(plugins, list):
        _info(f"No tokenage plugin in {config_path}")
        return 2
    kept = []
    removed = 0
    for entry in plugins:
        entry_path = (
            entry
            if isinstance(entry, str)
            else entry[0]
            if isinstance(entry, list) and entry
            else ""
        )
        if (
            str(entry_path)
            .replace("\\", "/")
            .endswith("plugins/opencode/dist/index.js")
        ):
            options = (
                entry[1]
                if isinstance(entry, list)
                and len(entry) >= 2
                and isinstance(entry[1], dict)
                else {}
            )
            endpoint = options.get("endpoint") or "http://localhost:4005/v1/logs"
            if expected_endpoint and endpoint != expected_endpoint:
                kept.append(entry)
                _info(
                    f"Plugin in {config_path} points at another collector; left alone"
                )
                continue
            removed += 1
            continue
        kept.append(entry)
    if not removed:
        _info(f"No matching tokenage plugin in {config_path}")
        return 2
    if kept:
        config["plugin"] = kept
    else:
        config.pop("plugin", None)
    save_json(config_path, config)
    _info(f"tokenage plugin removed from {config_path}")
    return 0


# Exit status contract: 0 configured/removed, 2 skipped, 1 failed.
def _main() -> int:
    argv = sys.argv[1:]
    # Compact client API; retain PORT/HOST positional inputs for direct callers.
    if len(argv) == 2 and "://" in argv[1]:
        argv = [argv[0], "", "", argv[1]]
    disable = False
    if "--disable" in argv:
        disable = True
        argv = [arg for arg in argv if arg != "--disable"]
    if len(argv) not in (1, 2, 3, 4, 5):
        print(
            "usage: configure-opencode-plugin.py PROJECT_ROOT "
            "[--disable [ENDPOINT]] | ENDPOINT | [OTLP_PORT] [HOST] [ENDPOINT] [TOKEN]",
            file=sys.stderr,
        )
        return 1

    project_root = Path(argv[0]).expanduser().resolve()
    config_path = select_config_path()
    if disable:
        return _disable(config_path, argv[1] if len(argv) >= 2 else None)
    config = load_json(config_path)
    otlp_port = argv[1] if len(argv) >= 2 else "4005"
    host = argv[2] if len(argv) >= 3 else "localhost"
    endpoint_arg = argv[3] if len(argv) >= 4 else None
    token = (
        argv[4]
        if len(argv) >= 5
        else os.environ.get("TOKENAGE_INGEST_TOKEN") or load_ingest_token()
    )
    plugin_dir = project_root / "plugins" / "opencode"
    dist_dir = plugin_dir / "dist"
    if endpoint_arg and "://" in endpoint_arg:
        endpoint = endpoint_arg
    else:
        endpoint = f"http://{host}:{otlp_port}/v1/logs"

    if not (dist_dir / "index.js").exists():
        node_modules = plugin_dir / "node_modules"
        if not node_modules.exists():
            _info(f"Installing OpenCode plugin dependencies in {plugin_dir}")
            # `npm ci` needs a committed lock file. A checkout without one still
            # has to build, so fall back rather than skipping the agent.
            locked = (plugin_dir / "package-lock.json").exists()
            command = ["ci"] if locked else ["install"]
            result = run_npm(command, plugin_dir)
            if result is None:
                return warn_skip("npm not found")
            if result.returncode != 0:
                return warn_skip(
                    f"npm {command[0]} failed:\n{result.stderr}", failed=True
                )
        _info(f"Building OpenCode plugin from {plugin_dir}")
        result = run_npm(["run", "build"], plugin_dir)
        if result is None:
            return warn_skip("npm not found")
        if result.returncode != 0:
            return warn_skip(f"plugin build failed:\n{result.stderr}", failed=True)
        _info("Plugin built successfully")
    else:
        _info("Plugin already built")

    # Register in config
    # Builds can take minutes; merge into the latest user settings, not the
    # snapshot used to validate the file before npm ran.
    config = load_json(config_path)
    plugins = config.get("plugin")
    if not isinstance(plugins, list):
        plugins = []

    plugin_path = str(plugin_dir / "dist" / "index.js")
    plugin_options: dict[str, Any] = {"endpoint": endpoint}
    if token:
        plugin_options["token"] = token
    plugin_entry = [plugin_path, plugin_options]

    # OpenCode loads every configured plugin. Keep one tracker build so stale
    # worktree entries cannot emit duplicate or unauthenticated telemetry.
    filtered_plugins = []
    for entry in plugins:
        entry_path = (
            entry
            if isinstance(entry, str)
            else entry[0]
            if isinstance(entry, list) and entry
            else ""
        )
        if (
            str(entry_path)
            .replace("\\", "/")
            .endswith("plugins/opencode/dist/index.js")
        ):
            continue
        filtered_plugins.append(entry)
    plugins = filtered_plugins

    plugins.append(plugin_entry)

    config["plugin"] = plugins
    save_json(config_path, config)
    _info(f"tokenage plugin registered in {config_path}")

    return 0


def main() -> int:
    try:
        return _main()
    except (OSError, UnicodeError, ValueError):
        print("cannot update OpenCode configuration; left unchanged", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
