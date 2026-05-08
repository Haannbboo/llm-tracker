#!/usr/bin/env python3
"""Report configured llm-tracker port conflicts before or after service startup."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
# Standalone script entrypoint: ensure project imports work without PYTHONPATH=.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.runtime_ports import (  # noqa: E402
    PortListener,
    detect_port_issues,
    format_port_issue,
    get_blocking_port_issues,
    get_configured_service_ports,
    parse_supervisor_status,
)


def _load_config(config_path: str) -> dict:
    """Load the user config used to derive the effective service ports."""
    with open(Path(config_path).expanduser(), encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def _collect_port_listeners(port: int) -> list[PortListener]:
    """Read current listeners for a port using ``lsof`` when available."""
    import socket

    if shutil.which("lsof") is not None:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode in {0, 1}:
            listeners: list[PortListener] = []
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 2:
                    continue
                listeners.append(PortListener(pid=int(parts[1]), command=parts[0]))
            return listeners

    # Fallback: probe the port directly via socket bind.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
        return []
    except OSError:
        return [PortListener(pid=-1, command="(unknown)")]


def _read_supervisor_states(supervisorctl: str, supervisord_conf: str | None) -> dict:
    """Return supervisor program states when supervisord is configured."""
    if not supervisord_conf or not Path(supervisord_conf).exists():
        return {}

    result = subprocess.run(
        [supervisorctl, "-c", supervisord_conf, "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}

    return parse_supervisor_status(result.stdout)


def main() -> int:
    """Check configured ports and optionally fail fast on conflicts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--supervisorctl", required=True)
    parser.add_argument("--supervisord-conf")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config = _load_config(args.config)
    service_ports = get_configured_service_ports(config)
    listeners_by_port = {
        service_port.port: _collect_port_listeners(service_port.port)
        for service_port in service_ports
    }
    supervisor_states = _read_supervisor_states(
        args.supervisorctl, args.supervisord_conf
    )
    issues = detect_port_issues(
        service_ports=service_ports,
        supervisor_states=supervisor_states,
        listeners_by_port=listeners_by_port,
    )

    if not issues:
        return 0

    blocking_issues = get_blocking_port_issues(issues)
    output_issues = blocking_issues if args.strict else issues
    if not output_issues:
        return 0

    # Keep the warning format concise so shell wrappers can surface it directly.
    print("==> Port Issues")
    for issue in output_issues:
        print(format_port_issue(issue))

    if args.strict and blocking_issues:
        print(
            "Resolve the conflicting port or change the configured service port "
            "before starting or restarting llm-tracker.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
