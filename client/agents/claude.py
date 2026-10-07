"""Claude Code: telemetry env keys in ``~/.claude/settings.json``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from client.agents import DONE, FAILED, SKIPPED, write_private
from client.agents import info as _info


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
        return SKIPPED
    if not settings_path.exists():
        _info(f"No Claude Code settings at {settings_path}")
        return SKIPPED
    settings = load_settings(settings_path)
    env = settings.get("env")
    env = env if isinstance(env, dict) else {}
    current = env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if current != expected_endpoint:
        print(
            f"{settings_path} has no matching collector; left alone",
            file=sys.stderr,
        )
        return SKIPPED

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
        return SKIPPED
    write_private(settings_path, json.dumps(settings, indent=2) + "\n")
    _info(f"Claude Code telemetry removed from {settings_path}")
    return DONE


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


def configure(target: str | Path, logs_endpoint: str, token: str | None = None) -> int:
    settings_path = Path(target).expanduser()
    try:
        settings = load_settings(settings_path)
        env = settings.setdefault("env", {})

        desired_env = {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": logs_endpoint,
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
            write_private(settings_path, json.dumps(settings, indent=2) + "\n")
            _info(f"Claude Code telemetry configured in {settings_path}")
        else:
            _info(f"Claude Code telemetry already up-to-date in {settings_path}")
    except (OSError, UnicodeError, ValueError):
        print("cannot update Claude configuration; left unchanged", file=sys.stderr)
        return FAILED
    return DONE


def disable(target: str | Path, expected_endpoint: str | None) -> int:
    try:
        return _disable(Path(target).expanduser(), expected_endpoint)
    except (OSError, UnicodeError, ValueError):
        print("cannot update Claude configuration; left unchanged", file=sys.stderr)
        return FAILED
