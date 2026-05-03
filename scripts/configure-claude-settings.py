#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def resolve_otlp_logs_endpoint(otlp_port: str) -> str:
    env_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if env_endpoint:
        return env_endpoint
    return f"http://localhost:{otlp_port}/v1/logs"


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(
            "usage: configure-claude-settings.py SETTINGS_PATH [OTLP_PORT]",
            file=sys.stderr,
        )
        return 1

    settings_path = Path(sys.argv[1]).expanduser()
    otlp_port = sys.argv[2] if len(sys.argv) == 3 else "4002"

    settings = load_settings(settings_path)
    env = settings.setdefault("env", {})

    desired_env = {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": resolve_otlp_logs_endpoint(otlp_port),
    }

    changed = False
    for k, v in desired_env.items():
        if env.get(k) != v:
            env[k] = v
            changed = True

    if changed:
        save_settings(settings_path, settings)
        print(f"==> Claude Code telemetry configured in {settings_path}")
    else:
        print(f"==> Claude Code telemetry already up-to-date in {settings_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
