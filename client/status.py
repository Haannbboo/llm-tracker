"""``tokenage status`` — client facts only: version, sign-in, where agents point.

Reads state only. Creates no files and works on a machine with no credentials.
The server's service view is ``tokenage server status``.
"""

from __future__ import annotations

import json
from typing import Any

from client.paths import client_commit, client_version, display_endpoint
from client.setup import (
    AGENT_MODULES,
    installed_agents,
    intended_endpoint,
    read_agent_states,
)

_LABEL_WIDTH = 12


def collect() -> dict[str, Any]:
    from client.auth import load_credentials

    credentials = load_credentials() or {}

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
        "account": account,
        "agents": agents,
    }


def is_healthy(data: dict[str, Any]) -> bool:
    """Exit code is 1 when a detected agent points at the wrong collector."""
    return not any(
        agent["detected"] and agent["endpoint_matches"] is False
        for agent in data["agents"]
    )


def _fix_hint(data: dict[str, Any]) -> str | None:
    if not data["account"]["signed_in"]:
        return "run tokenage login --server <url>"
    if any(
        agent["detected"] and agent["endpoint_matches"] is not True
        for agent in data["agents"]
    ):
        return "run tokenage setup"
    return None


def render(data: dict[str, Any]) -> str:
    lines: list[str] = []
    head = f"tokenage {data['client']['version']}"
    commit = data["client"]["commit"]
    if commit:
        head += f" (client {commit[:7]})"
    lines.append(head)

    def row(label: str, value: str) -> None:
        lines.append(f"  {label:<{_LABEL_WIDTH}}{value}")

    account = data["account"]
    if account["signed_in"]:
        row(
            "account",
            f"signed in as {account.get('email') or 'unknown'} → {account.get('server_url')}",
        )
        if account.get("device_name"):
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
        row(
            "agents",
            ", ".join(agent["name"] for agent in ready) + f" → {endpoint}",
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
