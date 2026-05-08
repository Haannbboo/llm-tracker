"""Tests for the _collect_port_listeners socket fallback in both scripts."""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script(filename: str):
    """Load a script as a module via importlib."""
    script_path = REPO_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(
        filename.removesuffix(".py").replace("-", "_"), script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check_service_ports_module():
    return _load_script("check-service-ports.py")


@pytest.fixture
def auto_assign_ports_module():
    return _load_script("auto-assign-ports.py")


def _occupy_port() -> tuple[socket.socket, int]:
    """Bind a socket to a random free port and return (socket, port)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    return sock, port


# --- check-service-ports.py ---


def test_check_service_ports_socket_fallback_detects_occupied_port(
    check_service_ports_module,
):
    sock, port = _occupy_port()
    try:
        with patch("shutil.which", return_value=None):
            listeners = check_service_ports_module._collect_port_listeners(port)
    finally:
        sock.close()

    assert len(listeners) == 1
    assert listeners[0].pid == -1
    assert listeners[0].command == "(unknown)"


def test_check_service_ports_socket_fallback_returns_empty_for_free_port(
    check_service_ports_module,
):
    # Bind and immediately close to get a port guaranteed free at this instant.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    with patch("shutil.which", return_value=None):
        listeners = check_service_ports_module._collect_port_listeners(free_port)

    assert listeners == []


# --- auto-assign-ports.py ---


def test_auto_assign_ports_socket_fallback_detects_occupied_port(
    auto_assign_ports_module,
):
    sock, port = _occupy_port()
    try:
        with patch("shutil.which", return_value=None):
            listeners = auto_assign_ports_module._collect_port_listeners(port)
    finally:
        sock.close()

    assert len(listeners) == 1
    assert listeners[0].pid == -1
    assert listeners[0].command == "(unknown)"


def test_auto_assign_ports_socket_fallback_returns_empty_for_free_port(
    auto_assign_ports_module,
):
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    with patch("shutil.which", return_value=None):
        listeners = auto_assign_ports_module._collect_port_listeners(free_port)

    assert listeners == []
