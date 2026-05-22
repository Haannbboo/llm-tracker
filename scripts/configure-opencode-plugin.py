#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def warn_skip(message: str) -> int:
    print(
        f"WARNING: {message}; skipping OpenCode plugin configuration", file=sys.stderr
    )
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


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: configure-opencode-plugin.py PROJECT_ROOT [OTLP_PORT]",
            file=sys.stderr,
        )
        return 1

    project_root = Path(sys.argv[1]).expanduser().resolve()
    otlp_port = sys.argv[2] if len(sys.argv) >= 3 else "4002"
    plugin_dir = project_root / "plugins" / "opencode"
    config_path = Path.home() / ".config" / "opencode" / "opencode.json"
    endpoint = f"http://localhost:{otlp_port}/v1/logs"

    node_modules = plugin_dir / "node_modules"
    if not node_modules.exists():
        print(f"==> Installing opencode plugin dependencies in {plugin_dir}")
        result = run_npm(["install", "--package-lock=false"], plugin_dir)
        if result is None:
            return warn_skip("npm not found")
        if result.returncode != 0:
            return warn_skip(f"npm install failed:\n{result.stderr}")

    if not (plugin_dir / "dist" / "index.js").exists():
        print(f"==> Building opencode plugin from {plugin_dir}")
        result = run_npm(["run", "build"], plugin_dir)
        if result is None:
            return warn_skip("npm not found")
        if result.returncode != 0:
            return warn_skip(f"plugin build failed:\n{result.stderr}")
        print("==> Plugin built successfully")
    else:
        print("==> Plugin already built")

    config = load_json(config_path)
    plugins = config.get("plugin")
    if not isinstance(plugins, list):
        plugins = []

    plugin_path = str(plugin_dir / "dist" / "index.js")
    plugin_entry = [plugin_path, {"endpoint": endpoint}]

    already_registered = False
    for i, entry in enumerate(plugins):
        if isinstance(entry, str) and entry == plugin_path:
            plugins[i] = plugin_entry
            already_registered = True
            break
        if isinstance(entry, list) and len(entry) >= 1 and entry[0] == plugin_path:
            if len(entry) < 2:
                entry.append({"endpoint": endpoint})
            elif isinstance(entry[1], dict):
                entry[1]["endpoint"] = endpoint
            already_registered = True
            break

    if not already_registered:
        plugins.append(plugin_entry)

    config["plugin"] = plugins
    save_json(config_path, config)
    print(f"==> llm-tracker plugin registered in {config_path} (endpoint: {endpoint})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
