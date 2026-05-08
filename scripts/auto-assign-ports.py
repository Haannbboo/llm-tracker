#!/usr/bin/env python3
"""Automatically move llm-tracker services to free ports when defaults are busy."""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
# Standalone script entrypoint: ensure project imports work without PYTHONPATH=.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.runtime_ports import (  # noqa: E402
    PortListener,
    detect_port_issues,
    get_blocking_port_issues,
    get_configured_service_ports,
)

SERVICE_KEYS = {
    "Proxy": "port",
    "API": "api_port",
    "OTLP": "otlp_port",
}
DEFAULT_START_PORT = 4000
DEFAULT_SEARCH_LIMIT = 200


def _load_config(config_path: Path) -> dict[str, Any]:
    with config_path.expanduser().open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def _write_config(config_path: Path, config: dict[str, Any]) -> None:
    config_path = config_path.expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file, sort_keys=False, allow_unicode=True)


def _collect_port_listeners(port: int) -> list[PortListener]:
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


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _find_free_ports(
    host: str, count: int, start_port: int, search_limit: int
) -> list[int]:
    ports: list[int] = []
    for port in range(start_port, start_port + search_limit):
        if port in ports:
            continue
        if _is_port_available(host, port):
            ports.append(port)
            if len(ports) == count:
                return ports
    raise RuntimeError(
        f"Could not find {count} free ports on {host} in range "
        f"{start_port}-{start_port + search_limit - 1}."
    )


def _service_port_summary(config: dict[str, Any]) -> list[str]:
    lines = []
    for service_port in get_configured_service_ports(config):
        lines.append(
            f"  {service_port.service}: http://{service_port.host}:{service_port.port}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--start-port", type=int, default=DEFAULT_START_PORT)
    parser.add_argument("--search-limit", type=int, default=DEFAULT_SEARCH_LIMIT)
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser()
    config = _load_config(config_path)
    service_ports = get_configured_service_ports(config)
    listeners_by_port = {
        service_port.port: _collect_port_listeners(service_port.port)
        for service_port in service_ports
    }
    issues = detect_port_issues(
        service_ports=service_ports,
        supervisor_states={},
        listeners_by_port=listeners_by_port,
    )
    blocking_issues = get_blocking_port_issues(issues)
    if not blocking_issues:
        return 0

    server = config.setdefault("server", {})
    host = str(server.get("host", "127.0.0.1"))
    try:
        free_ports = _find_free_ports(
            host=host,
            count=len(SERVICE_KEYS),
            start_port=args.start_port,
            search_limit=args.search_limit,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for key, port in zip(SERVICE_KEYS.values(), free_ports, strict=True):
        server[key] = port

    _write_config(config_path, config)

    print("==> Default service ports are busy; moved llm-tracker to free ports")
    for line in _service_port_summary(config):
        print(line)
    print(f"==> Updated config at {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
