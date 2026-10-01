"""Agent configuration: the client's job, in both installation modes.

The server never edits agent settings. This module points detected agents at a
collector and takes them back off again, by shelling out to the four
``scripts/configure-*.py`` helpers that own the file formats.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib

from client.paths import (
    PACKAGE_ROOT,
    SCRIPTS_DIR,
    display_endpoint,
    local_server_info,
    server_root,
)

AGENT_SCRIPTS: dict[str, str] = {
    "codex": "configure-codex-settings.py",
    "claude": "configure-claude-settings.py",
    "opencode": "configure-opencode-plugin.py",
    "kilo": "configure-kilo-plugin.py",
}

PLUGIN_SUFFIX = {
    "opencode": "plugins/opencode/dist/index.js",
    "kilo": "plugins/kilo/dist/index.js",
}


def agent_targets() -> dict[str, str]:
    """Agent name -> the first positional argument for its configure script.

    Resolved on every call so a test (or a changed HOME) is honoured.
    """
    home = Path.home()
    return {
        "codex": str(home / ".codex" / "config.toml"),
        "claude": str(home / ".claude" / "settings.json"),
        "opencode": str(PACKAGE_ROOT),
        "kilo": str(PACKAGE_ROOT),
    }


def plugin_configs() -> dict[str, Path]:
    home = Path.home()
    return {
        "opencode": home / ".config" / "opencode" / "opencode.json",
        "kilo": home / ".config" / "kilo" / "opencode.json",
    }


# A cold `npm install` inside the plugin scripts can take minutes. This bounds a
# hang, not slow work.
BUILD_TIMEOUT = 300
SIMPLE_TIMEOUT = 30


def installed_agents() -> list[str]:
    return [name for name in AGENT_SCRIPTS if shutil.which(name)]


def intended_endpoint() -> str | None:
    """The collector this install wants agents to report at, or None.

    Offline and cheap, because `status` asks on every run: it reads what login
    recorded. A machine signed in to a remote server never falls back to the
    local collector — that would quietly point agents at a collector which is
    not their server's. `setup` uses `discover_collector`, which can go and ask.
    """
    from client.auth import load_credentials, stored_collector

    stored = stored_collector()
    if stored:
        return stored
    if load_credentials():
        return None
    if server_root() is not None:
        return local_server_info()["otlp_logs_endpoint"]
    return None


def discover_collector() -> str | None:
    from client.auth import discover_collector as _discover

    return _discover()


def ingest_token() -> str | None:
    from client.auth import load_credentials

    token = (load_credentials() or {}).get("ingest_token")
    return token if isinstance(token, str) and token else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return {}


def _plugin_endpoint(config: dict[str, Any], suffix: str, default: str) -> str | None:
    """First tracker plugin entry wins, matching the server's setup-health check."""
    entries = config.get("plugin")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, str):
            entry_path = entry
        elif isinstance(entry, list) and entry and isinstance(entry[0], str):
            entry_path = entry[0]
        else:
            continue
        if not entry_path.replace("\\", "/").endswith(suffix):
            continue
        if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], dict):
            return str(entry[1].get("endpoint") or default)
        return default
    return None


def _health(configured: bool, endpoint: str | None, expected: str | None) -> dict:
    # An unknown target is not a wrong one. A machine that signed in before the
    # server published its collector cannot tell whether an agent is right, and
    # must not be told the agent is broken for that.
    matches: bool | None = None
    if not configured:
        status = "missing_config"
        matches = False if expected else None
    elif not expected:
        status = "configured"
    else:
        matches = endpoint == expected
        status = "ready" if matches else "wrong_endpoint"
    return {
        "configured": configured,
        "endpoint_matches": matches,
        "configured_endpoint": endpoint,
        "expected_endpoint": expected,
        "status": status,
    }


def read_agent_states(expected_endpoint: str | None) -> dict[str, dict[str, Any]]:
    """Per-agent wiring state, with the same semantics as ``/local/setup-health``.

    ``llm-tracker status`` reports this, so the CLI and the dashboard cannot
    disagree about whether an agent is wired.
    """
    claude_env = _read_json(Path(agent_targets()["claude"])).get("env")
    claude_env = claude_env if isinstance(claude_env, dict) else {}
    claude_endpoint = claude_env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    claude_configured = (
        claude_env.get("CLAUDE_CODE_ENABLE_TELEMETRY") in ("1", "true", "True", True)
        and claude_env.get("OTEL_LOGS_EXPORTER") == "otlp"
        and isinstance(claude_endpoint, str)
    )

    codex_otel = _read_toml(Path(agent_targets()["codex"])).get("otel")
    codex_otel = codex_otel if isinstance(codex_otel, dict) else {}
    codex_exporter = codex_otel.get("exporter")
    codex_exporter = codex_exporter if isinstance(codex_exporter, dict) else {}
    codex_http = codex_exporter.get("otlp-http")
    codex_http = codex_http if isinstance(codex_http, dict) else {}
    codex_endpoint = codex_http.get("endpoint")
    codex_configured = not (
        codex_otel.get("enabled") is False or codex_http.get("enabled") is False
    ) and isinstance(codex_endpoint, str)

    # Match the plugin runtime default for legacy entries with no options.
    fallback = "http://localhost:4005/v1/logs"
    states = {
        "claude": _health(
            claude_configured,
            claude_endpoint if isinstance(claude_endpoint, str) else None,
            expected_endpoint,
        ),
        "codex": _health(
            codex_configured,
            codex_endpoint if isinstance(codex_endpoint, str) else None,
            expected_endpoint,
        ),
    }
    for name, path in plugin_configs().items():
        endpoint = _plugin_endpoint(_read_json(path), PLUGIN_SUFFIX[name], fallback)
        states[name] = _health(endpoint is not None, endpoint, expected_endpoint)
    return states


def _run(script: str, args: list[str], env: dict[str, str], timeout: int):
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _child_env(*, token: str | None, disable: bool) -> dict[str, str]:
    env = os.environ.copy()
    # A pre-existing local OTLP override would silently beat the endpoint we are
    # wiring, so it is always stripped.
    env.pop("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", None)
    if not disable and token:
        env["LLM_TRACKER_INGEST_TOKEN"] = token
    else:
        env.pop("LLM_TRACKER_INGEST_TOKEN", None)
    return env


def wire_agents(
    *, logs_endpoint: str, token: str | None, agents: list[str] | None = None
) -> list[str]:
    """Point detected agents at a collector. Returns the agents that were wired."""
    if not logs_endpoint:
        return []
    env = _child_env(token=token, disable=False)
    wired: list[str] = []
    for name in agents if agents is not None else installed_agents():
        script, target = AGENT_SCRIPTS[name], agent_targets()[name]
        try:
            result = _run(
                script,
                [target, logs_endpoint],
                env,
                BUILD_TIMEOUT if name in PLUGIN_SUFFIX else SIMPLE_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            reason = (
                "helper timed out"
                if isinstance(exc, subprocess.TimeoutExpired)
                else "helper could not start"
            )
            print(f"warning: wiring {name} failed: {reason}", file=sys.stderr)
            continue
        # Script exit statuses: 0 configured, 2 skipped, 1 failed.
        if result.returncode == 0:
            wired.append(name)
        else:
            detail = result.stderr.strip() or result.stdout.strip()
            status = "skipped" if result.returncode == 2 else "failed"
            print(f"warning: wiring {name} {status}: {detail}", file=sys.stderr)
    return wired


@dataclass
class DisableResult:
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def disable_agents(*, expected_endpoint: str | None = None) -> DisableResult:
    """Remove llm-tracker's telemetry settings from the agents it manages.

    Remove settings only when their collector matches this installation's known
    endpoint. Unknown ownership leaves the configuration untouched.
    """
    env = _child_env(token=None, disable=True)
    outcome = DisableResult()
    agents = installed_agents()
    if not expected_endpoint:
        outcome.skipped.extend(agents)
        if agents:
            print(
                "warning: collector unknown; agent settings left unchanged",
                file=sys.stderr,
            )
        return outcome
    for name in agents:
        script, target = AGENT_SCRIPTS[name], agent_targets()[name]
        args = [target, "--disable"]
        if expected_endpoint:
            args.append(expected_endpoint)
        try:
            result = _run(script, args, env, SIMPLE_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            reason = (
                "helper timed out"
                if isinstance(exc, subprocess.TimeoutExpired)
                else "helper could not start"
            )
            print(f"warning: un-wiring {name} failed: {reason}", file=sys.stderr)
            outcome.failed.append(name)
            continue
        if result.returncode == 0:
            outcome.removed.append(name)
        else:
            (outcome.skipped if result.returncode == 2 else outcome.failed).append(name)
            print(
                f"warning: un-wiring {name} "
                f"{'skipped' if result.returncode == 2 else 'failed'}: "
                f"{result.stderr.strip() or result.stdout.strip()}",
                file=sys.stderr,
            )
    return outcome


def run_setup(*, disable: bool) -> int:
    """``llm-tracker setup`` — wire, or un-wire, the agents found on this machine."""
    agents = installed_agents()
    if not agents:
        print("No tracked agents detected; nothing to wire.")
        return 0
    expected = intended_endpoint()
    if disable:
        outcome = disable_agents(expected_endpoint=expected)
        if outcome.removed:
            print("  un-wired  " + ", ".join(outcome.removed))
        elif not outcome.failed:
            print("No matching telemetry removed; agent settings left unchanged.")
        if outcome.failed:
            print("  un-wiring failed: " + ", ".join(outcome.failed), file=sys.stderr)
        return 1 if outcome.failed or not expected else 0

    # A login made before the client recorded the collector needs one lookup
    # against the server; the answer is then remembered for later commands.
    endpoint = discover_collector() or expected
    if not endpoint:
        print(
            "No collector to wire agents to. Sign in with llm-tracker login, "
            "or install the server component.",
            file=sys.stderr,
        )
        return 1
    print(f"  collector   {display_endpoint(endpoint)}")
    wired = wire_agents(logs_endpoint=endpoint, token=ingest_token())
    if not wired:
        print("  no agents could be wired")
        return 1
    print("  wired       " + ", ".join(wired))
    return 0
