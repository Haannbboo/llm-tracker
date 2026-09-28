"""``llm-tracker status`` — what is installed, is it running, where do agents point.

Reads state only. Creates no files, starts no services, and works on a machine
that has no config, no supervisord and no credentials.
"""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

from client.paths import (
    client_commit,
    client_version,
    local_server_info,
    server_root,
    tracker_home,
)
from client.setup import (
    AGENT_SCRIPTS,
    installed_agents,
    intended_endpoint,
    read_agent_states,
)

SERVICES = (
    ("proxy", "llm-tracker-proxy", "proxy_port"),
    ("api", "llm-tracker-api", "api_port"),
    ("otlp", "llm-tracker-otlp", "otlp_port"),
)

_LABEL_WIDTH = 12


def _supervisord_conf() -> Path:
    return tracker_home() / "supervisord.conf"


def _supervisor_running(program: str, root: Path) -> bool | None:
    """True/False from supervisord, or None when it cannot be asked."""
    conf = _supervisord_conf()
    ctl = root / ".venv" / "bin" / "supervisorctl"
    if not conf.is_file() or not ctl.is_file():
        return None
    try:
        result = subprocess.run(
            [str(ctl), "-c", str(conf), "status", program],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    parts = result.stdout.split()
    return len(parts) >= 2 and parts[1] == "RUNNING"


def _port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _server_version(root: Path) -> str | None:
    version_file = root / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def collect() -> dict[str, Any]:
    from client.auth import load_credentials

    credentials = load_credentials() or {}
    root = server_root()
    info = local_server_info() if root is not None else None

    services: list[dict[str, Any]] = []
    if info is not None:
        for name, program, port_key in SERVICES:
            managed = _supervisor_running(program, root) if root else None
            listening = _port_listening("127.0.0.1", int(info[port_key]))
            state = "up" if managed and listening else "down"
            services.append(
                {
                    "name": name,
                    "port": int(info[port_key]),
                    "state": state,
                    "supervised": managed,
                }
            )

    expected = intended_endpoint()
    states = read_agent_states(expected)
    agents = [
        {
            "name": name,
            "installed": name in AGENT_SCRIPTS,
            "detected": name in installed_agents(),
            "configured": states.get(name, {}).get("configured", False),
            "endpoint_matches": states.get(name, {}).get("endpoint_matches", False),
            "endpoint": states.get(name, {}).get("configured_endpoint"),
        }
        for name in AGENT_SCRIPTS
    ]

    server: dict[str, Any] = {"installed": root is not None}
    if root is not None:
        server["version"] = _server_version(root)
        server["mode"] = "self-hosted"
        server["services"] = services

    signed_in = bool(credentials.get("cli_token") or credentials.get("server_url"))
    account: dict[str, Any] = {
        "signed_in": signed_in,
        "email": credentials.get("email"),
        "server_url": credentials.get("server_url"),
    }
    if credentials.get("device_name"):
        account["device_name"] = credentials["device_name"]

    return {
        "client": {"version": client_version(), "commit": client_commit()},
        "server": server,
        "account": account,
        "agents": agents,
        "dashboard": info["api_url"] if info is not None else None,
    }


def is_healthy(data: dict[str, Any]) -> bool:
    """Exit code is 1 when something installed is broken, never merely absent."""
    server = data["server"]
    if server["installed"] and any(
        service["state"] != "up" for service in server["services"]
    ):
        return False
    return not any(
        agent["detected"] and agent["endpoint_matches"] is False
        for agent in data["agents"]
    )


def _fix_hint(data: dict[str, Any]) -> str | None:
    if any(
        agent["detected"] and agent["endpoint_matches"] is not True
        for agent in data["agents"]
    ):
        return "run llm-tracker setup"
    if data["server"]["installed"] and any(
        service["state"] != "up" for service in data["server"]["services"]
    ):
        return "run llm-tracker server start"
    if not data["server"]["installed"] and not data["account"]["signed_in"]:
        return "run llm-tracker login --server <url>"
    return None


def render(data: dict[str, Any]) -> str:
    lines: list[str] = []
    head = f"llm-tracker {data['client']['version']}"
    commit = data["client"]["commit"]
    if commit:
        head += f" (client {commit[:7]})"
    if data["server"]["installed"]:
        head += f" · server {data['server'].get('version') or 'unknown'} (self-hosted)"
    lines.append(head)

    def row(label: str, value: str) -> None:
        lines.append(f"  {label:<{_LABEL_WIDTH}}{value}")

    if data["server"]["installed"]:
        services = " · ".join(
            f"{service['name']} :{service['port']} {service['state']}"
            for service in data["server"]["services"]
        )
        row("services", services)

    account = data["account"]
    if account["signed_in"]:
        row(
            "account",
            f"signed in as {account.get('email') or 'unknown'} → {account.get('server_url')}",
        )
        if account.get("device_name") and not data["server"]["installed"]:
            row("device", account["device_name"])
    else:
        row("account", "not signed in")

    detected = [agent for agent in data["agents"] if agent["detected"]]
    ready = [agent for agent in detected if agent["endpoint_matches"] is True]
    unknown = [agent for agent in detected if agent["endpoint_matches"] is None]
    wrong = [agent for agent in detected if agent["endpoint_matches"] is False]
    if not detected:
        row("agents", "none detected")
    elif not ready and not unknown:
        row("agents", "none wired")
    elif ready:
        endpoint = ready[0].get("endpoint") or ""
        suffix = ""
        if data["server"]["installed"] and any(
            service["state"] != "up" for service in data["server"]["services"]
        ):
            suffix = " (not reachable)"
        row(
            "agents",
            ", ".join(agent["name"] for agent in ready) + f" → {endpoint}{suffix}",
        )
    # Configured, but this machine does not know which collector to compare
    # against — it signed in before its server published one.
    if unknown:
        row(
            "agents",
            ", ".join(agent["name"] for agent in unknown)
            + f" → {unknown[0].get('endpoint') or '?'} (target unknown)",
        )
    if wrong:
        row(
            "agents",
            ", ".join(agent["name"] for agent in wrong)
            + f" → {wrong[0].get('endpoint') or '?'} (wrong collector)",
        )

    if data["dashboard"]:
        row("dashboard", data["dashboard"])

    hint = _fix_hint(data)
    if hint:
        row("fix", hint)
    return "\n".join(lines) + "\n"


def run_status(*, as_json: bool) -> int:
    data = collect()
    if as_json:
        print(json.dumps(data, separators=(",", ":"), sort_keys=False))
    else:
        print(render(data), end="")
    return 0 if is_healthy(data) else 1
