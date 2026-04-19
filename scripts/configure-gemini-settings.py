#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


DESIRED_TELEMETRY = {
    "enabled": True,
    "target": "local",
    "otlpEndpoint": "http://localhost:4002",
    "otlpProtocol": "http",
}
HOOK_NAME = "llm-tracker"


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


def desired_hook(hook_path: str) -> dict[str, Any]:
    return {
        "name": HOOK_NAME,
        "type": "command",
        "command": hook_path,
    }


def upsert_hooks(settings: dict[str, Any], hook_path: str) -> bool:
    """Set telemetry and BeforeModel/AfterModel hooks in settings. Returns True if changed."""
    changed = False

    if settings.get("telemetry") != DESIRED_TELEMETRY:
        settings["telemetry"] = DESIRED_TELEMETRY
        changed = True

    hooks = settings.setdefault("hooks", {})
    target_hook = desired_hook(hook_path)

    for event_name in ("BeforeModel", "AfterModel"):
        groups = hooks.get(event_name)
        if not isinstance(groups, list):
            groups = []

        # Remove any existing llm-tracker hooks (any format)
        kept_groups: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict):
                changed = True
                continue
            # Drop legacy top-level cmd groups
            if "cmd" in group or group.get("name") == HOOK_NAME:
                changed = True
                continue
            group_hooks = group.get("hooks")
            if not isinstance(group_hooks, list):
                kept_groups.append(group)
                continue
            filtered = [
                h
                for h in group_hooks
                if not (
                    isinstance(h, dict)
                    and (
                        h.get("name") == HOOK_NAME
                        or h.get("command", "").endswith("gemini-hook.sh")
                        or h.get("cmd", "").endswith("gemini-hook.sh")
                    )
                )
            ]
            if len(filtered) != len(group_hooks):
                changed = True
            if filtered:
                kept = dict(group)
                kept["hooks"] = filtered
                kept_groups.append(kept)
            else:
                changed = True

        # Append our hook group
        kept_groups.append({"matcher": "*", "hooks": [target_hook]})
        hooks[event_name] = kept_groups
        changed = True

    return changed


def strip_all_llm_tracker_hooks(settings: dict[str, Any]) -> bool:
    """Remove all llm-tracker hooks and telemetry from settings. Returns True if changed."""
    changed = False

    if "telemetry" in settings:
        del settings["telemetry"]
        changed = True

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return changed

    for event_name in ("BeforeModel", "AfterModel"):
        groups = hooks.get(event_name)
        if not isinstance(groups, list):
            continue

        new_groups: list[Any] = []
        for group in groups:
            if not isinstance(group, dict):
                new_groups.append(group)
                continue
            # Drop legacy top-level cmd groups pointing to our hook
            legacy_cmd = group.get("cmd", "")
            if group.get("name") == HOOK_NAME or (
                isinstance(legacy_cmd, str) and legacy_cmd.endswith("gemini-hook.sh")
            ):
                changed = True
                continue

            group_hooks = group.get("hooks")
            if isinstance(group_hooks, list):
                filtered = [
                    h
                    for h in group_hooks
                    if not (
                        isinstance(h, dict)
                        and (
                            h.get("name") == HOOK_NAME
                            or h.get("command", "").endswith("gemini-hook.sh")
                        )
                    )
                ]
                if len(filtered) != len(group_hooks):
                    changed = True
                if filtered:
                    kept = dict(group)
                    kept["hooks"] = filtered
                    new_groups.append(kept)
                else:
                    changed = True
                continue

            new_groups.append(group)

        if new_groups:
            hooks[event_name] = new_groups
        elif event_name in hooks:
            del hooks[event_name]
            changed = True

    if not hooks and "hooks" in settings:
        del settings["hooks"]
        changed = True

    return changed


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: configure-gemini-settings.py USER_SETTINGS PROJECT_SETTINGS HOOK_PATH",
            file=sys.stderr,
        )
        return 1

    user_settings_path = Path(sys.argv[1]).expanduser()
    project_settings_path = Path(sys.argv[2]).expanduser()
    hook_path = str(Path(sys.argv[3]).resolve())

    # Install telemetry + hooks into user settings (global, applies to all Gemini CLI usage)
    user_settings = load_settings(user_settings_path)
    upsert_hooks(user_settings, hook_path)
    save_settings(user_settings_path, user_settings)
    print(f"==> Gemini user telemetry and hooks configured in {user_settings_path}")

    # Strip any llm-tracker hooks/telemetry from project settings (avoid double-firing)
    project_settings = load_settings(project_settings_path)
    if strip_all_llm_tracker_hooks(project_settings):
        save_settings(project_settings_path, project_settings)
        print(
            f"==> Removed llm-tracker hooks/telemetry from project {project_settings_path}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
