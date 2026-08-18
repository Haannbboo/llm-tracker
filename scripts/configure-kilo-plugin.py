#!/usr/bin/env python3
"""Configure the llm-tracker plugin for Kilo Code.

Usage: configure-kilo-plugin.py PROJECT_ROOT [OTLP_PORT]

The plugin registers itself in the Kilo Code config as a tracked plugin
so that llm-tracker's health endpoint can detect it.

Kilo Code reads its plugin config from ~/.config/kilo/opencode.json.
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
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_ingest_token() -> str | None:
    try:
        credentials = json.loads(
            (Path.home() / ".llm-tracker" / "credentials.json").read_text(
                encoding="utf-8"
            )
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


def warn_skip(message: str) -> int:
    print(f"WARNING: {message}; skipping Kilo plugin configuration", file=sys.stderr)
    return 0


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


KILO_CONFIG_PATH = Path.home() / ".config" / "kilo" / "opencode.json"


def select_config_path() -> Path:
    """Return the Kilo Code config path, creating it if needed."""
    return KILO_CONFIG_PATH


def main() -> int:
    if len(sys.argv) not in (2, 3, 4, 5, 6):
        print(
            "usage: configure-kilo-plugin.py PROJECT_ROOT [OTLP_PORT] [HOST] [ENDPOINT] [TOKEN]",
            file=sys.stderr,
        )
        return 1

    project_root = Path(sys.argv[1]).expanduser().resolve()
    otlp_port = sys.argv[2] if len(sys.argv) >= 3 else "4005"
    host = sys.argv[3] if len(sys.argv) >= 4 else "localhost"
    endpoint_arg = sys.argv[4] if len(sys.argv) >= 5 else None
    token = (
        sys.argv[5]
        if len(sys.argv) >= 6
        else os.environ.get("LLM_TRACKER_INGEST_TOKEN") or load_ingest_token()
    )
    plugin_dir = project_root / "plugins" / "kilo"
    config_path = select_config_path()
    if endpoint_arg and "://" in endpoint_arg:
        endpoint = endpoint_arg
    else:
        endpoint = f"http://{host}:{otlp_port}/v1/logs"

    # Install dependencies
    node_modules = plugin_dir / "node_modules"
    if not node_modules.exists():
        _info(f"Installing Kilo plugin dependencies in {plugin_dir}")
        result = run_npm(["install", "--package-lock=false"], plugin_dir)
        if result is None:
            return warn_skip("npm not found")
        if result.returncode != 0:
            return warn_skip(f"npm install failed:\n{result.stderr}")

    # Build
    if not (plugin_dir / "dist" / "index.js").exists():
        _info(f"Building Kilo plugin from {plugin_dir}")
        result = run_npm(["run", "build"], plugin_dir)
        if result is None:
            return warn_skip("npm not found")
        if result.returncode != 0:
            return warn_skip(f"plugin build failed:\n{result.stderr}")
        _info("Plugin built successfully")
    else:
        _info("Plugin already built")

    # Register in config
    config = load_json(config_path)
    plugins = config.get("plugin")
    if not isinstance(plugins, list):
        plugins = []

    plugin_path = str(plugin_dir / "dist" / "index.js")
    plugin_options: dict[str, Any] = {"endpoint": endpoint}
    if token:
        plugin_options["token"] = token
    plugin_entry = [plugin_path, plugin_options]

    # Kilo loads every configured plugin. Keep one tracker build per config.
    filtered_plugins = []
    current_plugin_kept = False
    for entry in plugins:
        entry_path = (
            entry
            if isinstance(entry, str)
            else entry[0]
            if isinstance(entry, list) and entry
            else ""
        )
        if str(entry_path).replace("\\", "/").endswith("plugins/kilo/dist/index.js"):
            entry_endpoint = (
                entry[1].get("endpoint")
                if isinstance(entry, list)
                and len(entry) >= 2
                and isinstance(entry[1], dict)
                else None
            )
            if str(entry_path) == plugin_path:
                if current_plugin_kept:
                    continue
                current_plugin_kept = True
            elif entry_endpoint == endpoint:
                continue
        filtered_plugins.append(entry)
    plugins = filtered_plugins

    already_registered = False
    for i, entry in enumerate(plugins):
        if isinstance(entry, str) and entry == plugin_path:
            plugins[i] = plugin_entry
            already_registered = True
            break
        if isinstance(entry, list) and len(entry) >= 1 and entry[0] == plugin_path:
            if len(entry) < 2:
                entry.append(plugin_options)
            elif isinstance(entry[1], dict):
                entry[1]["endpoint"] = endpoint
                if token:
                    entry[1]["token"] = token
                else:
                    entry[1].pop("token", None)
            else:
                entry[1] = plugin_options
            already_registered = True
            break

    if not already_registered:
        plugins.append(plugin_entry)

    config["plugin"] = plugins
    save_json(config_path, config)
    _info(f"llm-tracker plugin registered in {config_path} (endpoint: {endpoint})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
