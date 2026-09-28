"""Where things live on disk, for both installation modes.

The client never imports the server. It discovers what is installed by looking
at ``$LLM_TRACKER_HOME``:

- ``$LLM_TRACKER_HOME/current``  -> a client source snapshot (client-only installs)
- ``$LLM_TRACKER_HOME/src``      -> the server clone (all-in-one installs)

A client-only install brings its own virtualenv. An all-in-one install reuses the
server's, because the client needs nothing the server does not already have.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

# Root of the source tree this client was loaded from. The agent-configuration
# scripts live in <root>/scripts, so the client needs the snapshot on disk, not
# just the client package.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PACKAGE_ROOT / "scripts"

VERSION_FILE = Path(__file__).resolve().parent / "VERSION"
COMMIT_FILE = Path(__file__).resolve().parent / "COMMIT"

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")

DEFAULT_PROXY_PORT = 4000
DEFAULT_API_PORT = 4001
DEFAULT_OTLP_PORT = 4002


def tracker_home() -> Path:
    return Path(os.environ.get("LLM_TRACKER_HOME", "~/.llm-tracker")).expanduser()


def credentials_path() -> Path:
    return tracker_home() / "credentials.json"


def installation_path() -> Path:
    return tracker_home() / "installation.json"


def config_path() -> Path:
    return Path(
        os.environ.get("LLM_TRACKER_CONFIG", "~/.llm-tracker/config.yaml")
    ).expanduser()


def read_object(path: Path) -> dict[str, Any] | None:
    """Read a JSON object, or None when the file is absent. Unreadable is an error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid JSON object in {path}")
    return data


def client_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def client_commit() -> str | None:
    raw = os.environ.get("LLM_TRACKER_CLIENT_COMMIT")
    if raw is None and COMMIT_FILE.exists():
        raw = COMMIT_FILE.read_text(encoding="utf-8").strip()
    value = (raw or "").lower()
    return value if _COMMIT_RE.fullmatch(value) else None


def client_root() -> Path | None:
    """The source snapshot the ``current`` symlink points at, if installed."""
    link = tracker_home() / "current"
    try:
        resolved = link.resolve(strict=True)
    except OSError:
        return None
    return resolved if (resolved / "client").is_dir() else None


def server_root() -> Path | None:
    """The server clone, if this machine has the server component installed.

    ``LLM_TRACKER_ROOT`` wins so worktrees and tests can point at any checkout.
    """
    candidates = []
    override = os.environ.get("LLM_TRACKER_ROOT")
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(tracker_home() / "src")
    for candidate in candidates:
        if (candidate / ".venv" / "bin" / "python").is_file():
            return candidate
    return None


def client_python() -> Path | None:
    """Interpreter to run this client with, or None when it is not installed."""
    root = client_root()
    if root is not None:
        candidate = root / ".venv" / "bin" / "python"
        if candidate.is_file():
            return candidate
    server = server_root()
    if server is not None:
        return server / ".venv" / "bin" / "python"
    return None


def local_config() -> dict[str, Any]:
    """The user config, or an empty dict when the server component is absent.

    Only the ``server`` section is read, so a config written by a different
    version cannot break the client.
    """
    try:
        raw = yaml.safe_load(config_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return {}
    if not isinstance(raw, dict):
        return {}
    section = raw.get("server")
    return section if isinstance(section, dict) else {}


def _port(section: dict[str, Any], key: str, default: int) -> int:
    value = section.get(key, default)
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


def local_server_info() -> dict[str, Any]:
    """Ports and URLs for the local server, from config plus the usual defaults.

    Mirrors ``src.config.server_config.resolve_server_urls`` closely enough for
    the CLI's needs. The one place they can disagree is the OpenCode/Kilo
    plugin default endpoint, which the server hardcodes to port 4005; the client
    uses the configured OTLP port instead.
    """
    section = local_config()
    proxy_port = _port(section, "port", DEFAULT_PROXY_PORT)
    api_port = _port(section, "api_port", DEFAULT_API_PORT)
    otlp_port = _port(section, "otlp_port", DEFAULT_OTLP_PORT)

    base = str(section.get("base_url") or "").strip().rstrip("/")
    host = str(section.get("host") or "127.0.0.1")
    if base:
        scheme, _, authority = base.partition("://")
        host = authority.split("/")[0].split(":")[0] or host
    else:
        scheme = "http"
    if host in {"0.0.0.0", "127.0.0.1", "::", ""}:
        host = "localhost"
    origin = f"{scheme}://{host}"

    return {
        "host": host,
        "proxy_port": proxy_port,
        "api_port": api_port,
        "otlp_port": otlp_port,
        "api_url": f"{origin}:{api_port}",
        "proxy_url": f"{origin}:{proxy_port}",
        "otlp_logs_endpoint": f"{origin}:{otlp_port}/v1/logs",
    }
