"""``tokenage status`` — what is installed, is it running, where do agents point.

Reads state only. Creates no files, starts no services, and works on a machine
that has no config, no supervisord and no credentials.
"""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import httpx

from client.paths import (
    client_commit,
    client_version,
    display_endpoint,
    local_config,
    local_server_info,
    server_root,
    tracker_home,
)
from client.setup import (
    AGENT_MODULES,
    installed_agents,
    intended_endpoint,
    read_agent_states,
)

SERVICES = (
    ("proxy", "tokenage-proxy", "proxy_port"),
    ("api", "tokenage-api", "api_port"),
    ("otlp", "tokenage-otlp", "otlp_port"),
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


def _collector_address(info: dict[str, Any], bind_host: str) -> tuple[str, int] | None:
    """Ask the running API about its collector, not the caller's environment."""
    api_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(bind_host, bind_host)
    authority = f"[{api_host}]" if ":" in api_host else api_host
    try:
        response = httpx.get(
            f"http://{authority}:{info['api_port']}/version", timeout=1
        )
        response.raise_for_status()
        payload = response.json()
        bind = payload.get("collector_bind") if isinstance(payload, dict) else None
        if isinstance(bind, dict):
            host, port = bind.get("host"), bind.get("port")
            if (
                isinstance(host, str)
                and host
                and isinstance(port, int)
                and 1 <= port <= 65535
            ):
                return host, port
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    # Old/unreachable APIs cannot prove the running collector's bind address.
    # A public client URL or caller-side YAML port is not operational evidence.
    return None


def collect() -> dict[str, Any]:
    from client.auth import load_credentials

    credentials = load_credentials() or {}
    root = server_root()
    info = local_server_info() if root is not None else None

    services: list[dict[str, Any]] = []
    if info is not None:
        bind_host = str(local_config().get("host") or "127.0.0.1")
        collector_address = _collector_address(info, bind_host)
        otlp_host, otlp_port = collector_address or (bind_host, None)
        for name, program, port_key in SERVICES:
            managed = _supervisor_running(program, root) if root else None
            host = otlp_host if name == "otlp" else bind_host
            host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
            port = otlp_port if name == "otlp" else int(info[port_key])
            listening = _port_listening(host, port) if port is not None else None
            state = (
                "unknown"
                if port is None and managed is not False
                else "up"
                if managed and listening
                else "down"
            )
            services.append(
                {
                    "name": name,
                    "port": port,
                    "state": state,
                    "supervised": managed,
                }
            )

    expected = intended_endpoint()
    states = read_agent_states(expected)
    detected = installed_agents()
    agents = [
        {
            "name": name,
            "detected": name in detected,
            "configured": states.get(name, {}).get("configured", False),
            "endpoint_matches": states.get(name, {}).get("endpoint_matches", False),
            "endpoint": display_endpoint(
                states.get(name, {}).get("configured_endpoint")
            ),
        }
        for name in AGENT_MODULES
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
        "server_url": display_endpoint(credentials.get("server_url")),
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
        service["state"] == "down" for service in server["services"]
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
        return "run tokenage setup"
    if data["server"]["installed"] and any(
        service["state"] == "down" for service in data["server"]["services"]
    ):
        return "run tokenage server start"
    if data["server"]["installed"] and any(
        service["state"] == "unknown" for service in data["server"]["services"]
    ):
        return "check the server collector configuration; its address is unknown"
    if not data["server"]["installed"] and not data["account"]["signed_in"]:
        return "run tokenage login --server <url>"
    return None


def render(data: dict[str, Any]) -> str:
    lines: list[str] = []
    head = f"tokenage {data['client']['version']}"
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
            f"{service['name']} :{service['port'] if service['port'] is not None else '?'} {service['state']}"
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
            service["state"] == "down" for service in data["server"]["services"]
        ):
            suffix = " (not reachable)"
        elif data["server"]["installed"] and any(
            service["state"] == "unknown" for service in data["server"]["services"]
        ):
            suffix = " (collector address unknown)"
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
        for agent in wrong:
            detail = (
                f"→ {agent['endpoint']} (wrong collector)"
                if agent["configured"]
                else "needs configuration; run setup to check the file"
            )
            row("agents", f"{agent['name']} {detail}")

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
