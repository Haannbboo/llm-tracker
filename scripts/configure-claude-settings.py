#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_GRAY = "\033[38;2;102;102;102m" if sys.stdout.isatty() else ""
_RESET = "\033[0m" if sys.stdout.isatty() else ""


def _info(msg: str) -> None:
    print(f"  {_GRAY}{msg}{_RESET}")


def load_settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read Claude configuration; left unchanged") from exc
    if not isinstance(data, dict) or (
        "env" in data and not isinstance(data["env"], dict)
    ):
        raise ValueError("invalid Claude configuration; left unchanged")
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


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(settings, indent=2) + "\n"
    if path.exists():
        path.chmod(0o600)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def resolve_otlp_logs_endpoint(
    otlp_port: str, host: str = "localhost", endpoint: str | None = None
) -> str:
    env_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if env_endpoint:
        return env_endpoint
    if endpoint and "://" in endpoint:
        return endpoint
    return f"http://{host}:{otlp_port}/v1/logs"


# Only these keys are ever written by this script, so only these are removed.
_OWNED_ENV_KEYS = (
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "OTEL_LOGS_EXPORTER",
    "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
)


def _disable(settings_path: Path, expected_endpoint: str | None) -> int:
    """Remove tokenage's telemetry keys and its tool-call hooks.

    A hand-written collector config is left alone: the OTLP keys are only removed
    while the endpoint is the one tokenage wrote. The hooks are identified by
    script path, so they can only be ours.
    """
    if not expected_endpoint:
        print("collector unknown; Claude configuration left unchanged", file=sys.stderr)
        return 2
    if not settings_path.exists():
        _info(f"No Claude Code settings at {settings_path}")
        return 2
    settings = load_settings(settings_path)
    env = settings.get("env")
    env = env if isinstance(env, dict) else {}
    current = env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if current != expected_endpoint:
        print(
            f"{settings_path} has no matching collector; left alone",
            file=sys.stderr,
        )
        return 2

    changed = False
    for key in _OWNED_ENV_KEYS:
        if key in env:
            del env[key]
            changed = True
    headers = env.get("OTEL_EXPORTER_OTLP_HEADERS")
    if isinstance(headers, str):
        remaining = [
            part
            for part in headers.split(",")
            if part.strip().partition("=")[0] != "x-tokenage-token"
        ]
        if len(remaining) != len(headers.split(",")):
            if remaining:
                env["OTEL_EXPORTER_OTLP_HEADERS"] = ",".join(remaining)
            else:
                del env["OTEL_EXPORTER_OTLP_HEADERS"]
            changed = True
    if env:
        settings["env"] = env
    else:
        settings.pop("env", None)

    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event in ("PreToolUse", "PostToolUse"):
            entries = hooks.get(event)
            if not isinstance(entries, list):
                continue
            kept = []
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(
                    entry.get("hooks"), list
                ):
                    kept.append(entry)
                    continue
                remaining = [
                    hook for hook in entry["hooks"] if not _is_tracker_hook(hook)
                ]
                if len(remaining) != len(entry["hooks"]):
                    changed = True
                    if remaining:
                        kept.append({**entry, "hooks": remaining})
                else:
                    kept.append(entry)
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event)
        if hooks:
            settings["hooks"] = hooks
        else:
            settings.pop("hooks", None)

    if not changed:
        _info(f"No tokenage telemetry in {settings_path}")
        return 2
    save_settings(settings_path, settings)
    _info(f"Claude Code telemetry removed from {settings_path}")
    return 0


def _is_tracker_hook(hook: object) -> bool:
    if not isinstance(hook, dict) or hook.get("type") != "command":
        return False
    # Historical registration used an absolute scripts/claude-hook.sh path.
    # A user's similarly named command is not ours.
    command = hook.get("command")
    if not isinstance(command, str):
        return False
    path = Path(command)
    if not path.is_absolute() or path.parts[-2:] != ("scripts", "claude-hook.sh"):
        return False
    root = path.parent.parent
    try:
        launcher = (root / "scripts" / "tokenage").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return "# tokenage launcher" in launcher.splitlines() and (
        (root / "client").is_dir() or (root / "src").is_dir()
    )


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
            "usage: configure-claude-settings.py SETTINGS_PATH "
            "[--disable [ENDPOINT]] | ENDPOINT | [OTLP_PORT] [HOST] [ENDPOINT] [TOKEN]",
            file=sys.stderr,
        )
        return 1

    settings_path = Path(argv[0]).expanduser()
    if disable:
        # ENDPOINT is the one tokenage wrote; anything else is the user's.
        return _disable(settings_path, argv[1] if len(argv) >= 2 else None)
    otlp_port = argv[1] if len(argv) >= 2 else "4002"
    host = argv[2] if len(argv) >= 3 else "localhost"
    endpoint = argv[3] if len(argv) >= 4 else None
    token = (
        argv[4]
        if len(argv) >= 5
        else os.environ.get("TOKENAGE_INGEST_TOKEN") or load_ingest_token()
    )

    settings = load_settings(settings_path)
    env = settings.setdefault("env", {})

    desired_env = {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": resolve_otlp_logs_endpoint(
            otlp_port, host, endpoint
        ),
    }
    if token:
        desired_env["OTEL_EXPORTER_OTLP_HEADERS"] = f"x-tokenage-token={token}"

    changed = False
    for k, v in desired_env.items():
        if env.get(k) != v:
            env[k] = v
            changed = True
    if not token and "OTEL_EXPORTER_OTLP_HEADERS" in env:
        del env["OTEL_EXPORTER_OTLP_HEADERS"]
        changed = True

    if changed:
        save_settings(settings_path, settings)
        _info(f"Claude Code telemetry configured in {settings_path}")
    else:
        _info(f"Claude Code telemetry already up-to-date in {settings_path}")

    return 0


def main() -> int:
    try:
        return _main()
    except (OSError, UnicodeError, ValueError):
        print("cannot update Claude configuration; left unchanged", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
