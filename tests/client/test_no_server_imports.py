"""The client must never import the server.

This is the whole enforcement mechanism for the client/server split, and it is a
static check rather than a convention: a client that reached into ``src`` would
break on a machine that has only a client, and nothing else in the test suite
would notice.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CLIENT_DIR = Path(__file__).resolve().parents[2] / "client"
# `src` is the server package; the rest are the server's framework stack, which a
# client-only install does not install. pyyaml is deliberately allowed.
FORBIDDEN_ROOTS = {"src", "gunicorn", "fastapi", "sqlalchemy", "uvicorn"}


def _python_files() -> list[Path]:
    files = sorted(path for path in CLIENT_DIR.rglob("*.py"))
    assert files, "no client modules found"
    return files


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_client_never_imports_the_server(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in FORBIDDEN_ROOTS, f"{path.name} imports {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".")[0]
            assert root not in FORBIDDEN_ROOTS, f"{path.name} imports {node.module}"


def test_client_requirements_stay_small() -> None:
    """The client installs on machines that have no server, so it stays light."""
    requirements = (CLIENT_DIR / "requirements.txt").read_text(encoding="utf-8")
    names = {
        line.split(">=")[0].split("==")[0].split("<")[0].strip().lower()
        for line in requirements.splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert names == {"httpx", "pydantic", "pyyaml"}


def test_server_cli_does_not_import_the_client() -> None:
    """The dependency runs one way: client -> protocol <- server."""
    source = Path(__file__).resolve().parents[2] / "src" / "cli.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] != "client"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "client"
