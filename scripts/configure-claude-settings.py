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
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
    """Remove llm-tracker's telemetry keys and its tool-call hooks.

    A hand-written collector config is left alone: the OTLP keys are only removed
    while the endpoint is the one llm-tracker wrote. The hooks are identified by
    script path, so they can only be ours.
    """
    if not settings_path.exists():
        _info(f"No Claude Code settings at {settings_path}")
        return 0
    settings = load_settings(settings_path)
    env = settings.get("env")
    env = env if isinstance(env, dict) else {}
    current = env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if current and expected_endpoint and current != expected_endpoint:
        print(
            f"{settings_path} points at another collector ({current}); left alone",
            file=sys.stderr,
        )
        return 0

    changed = False
    for key in _OWNED_ENV_KEYS:
        if key in env:
            del env[key]
            changed = True
    headers = env.get("OTEL_EXPORTER_OTLP_HEADERS")
    if isinstance(headers, str) and headers.startswith("x-llm-tracker-token="):
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
            kept = [entry for entry in entries if not _is_tracker_hook(entry)]
            if len(kept) != len(entries):
                changed = True
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event)
        if hooks:
            settings["hooks"] = hooks
        else:
            settings.pop("hooks", None)

    if not changed:
        _info(f"No llm-tracker telemetry in {settings_path}")
        return 0
    save_settings(settings_path, settings)
    _info(f"Claude Code telemetry removed from {settings_path}")
    return 0


def _is_tracker_hook(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    inner = entry.get("hooks")
    if not isinstance(inner, list):
        return False
    return any(
        isinstance(hook, dict)
        and str(hook.get("command", "")).endswith("claude-hook.sh")
        for hook in inner
    )


def main() -> int:
    argv = sys.argv[1:]
    disable = False
    if "--disable" in argv:
        disable = True
        argv = [arg for arg in argv if arg != "--disable"]
    if len(argv) not in (1, 2, 3, 4, 5):
        print(
            "usage: configure-claude-settings.py SETTINGS_PATH "
            "[--disable [ENDPOINT]] | [OTLP_PORT] [HOST] [ENDPOINT] [TOKEN]",
            file=sys.stderr,
        )
        return 1

    settings_path = Path(argv[0]).expanduser()
    if disable:
        # ENDPOINT is the one llm-tracker wrote; anything else is the user's.
        return _disable(settings_path, argv[1] if len(argv) >= 2 else None)
    otlp_port = argv[1] if len(argv) >= 2 else "4002"
    host = argv[2] if len(argv) >= 3 else "localhost"
    endpoint = argv[3] if len(argv) >= 4 else None
    token = (
        argv[4]
        if len(argv) >= 5
        else os.environ.get("LLM_TRACKER_INGEST_TOKEN") or load_ingest_token()
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
        desired_env["OTEL_EXPORTER_OTLP_HEADERS"] = f"x-llm-tracker-token={token}"

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

    # Hosted tracking uses OTLP directly; the legacy tool-call hook is a no-op
    # and a versioned source path would add duplicate hooks on every update.
    if os.environ.get("LLM_TRACKER_HOSTED_CLIENT") == "1":
        return 0

    # Register tool-call hook (PreToolUse + PostToolUse).
    hook_path = Path(__file__).resolve().parent / "claude-hook.sh"
    parts = hook_path.parts
    if ".claude" in parts:
        wt_idx = parts.index(".claude") + 1
        if wt_idx < len(parts) and parts[wt_idx] == "worktrees":
            main_hook = Path(*parts[: wt_idx - 1]) / "scripts" / "claude-hook.sh"
            if main_hook.exists():
                hook_path = main_hook
    hook_script = str(hook_path)
    hooks = settings.setdefault("hooks", {})
    hook_changed = False
    for event in ("PreToolUse", "PostToolUse"):
        event_hooks = hooks.setdefault(event, [])
        # Only add if not already registered.
        if not any(
            h.get("matcher") == ".*"
            and any(
                hh.get("type") == "command" and hh.get("command") == hook_script
                for hh in h.get("hooks", [])
            )
            for h in event_hooks
        ):
            event_hooks.append(
                {
                    "matcher": ".*",
                    "hooks": [{"type": "command", "command": hook_script}],
                }
            )
            hook_changed = True
    if hook_changed:
        save_settings(settings_path, settings)
        _info(f"Tool-call hook registered in {settings_path}")
    else:
        _info(f"Tool-call hook already registered in {settings_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
