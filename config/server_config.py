"""Shared server configuration loader for gunicorn config files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import yaml

OTEL_EXPORTER_OTLP_LOGS_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    api_port: int
    otlp_host: str
    otlp_port: int
    base_url: str | None = None


def _resolve_otlp_host_port(config: dict) -> tuple[str, int]:
    endpoint = os.environ.get(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT_ENV)
    if endpoint:
        try:
            parsed = urlparse(endpoint)
            if parsed.hostname and parsed.port:
                return parsed.hostname, parsed.port
        except ValueError:
            pass

    server = config.get("server", {})
    host = str(server.get("host", "127.0.0.1"))
    proxy_port = int(server.get("port", 4000))
    api_port = int(server.get("api_port", proxy_port + 1))
    otlp_port = int(server.get("otlp_port", api_port + 1))
    return host, otlp_port


def resolve_server_urls(config: dict) -> dict[str, str]:
    """Return full URLs for proxy, api, and otlp services.

    Uses ``server.base_url`` when set (e.g. ``http://my-nas``), otherwise
    derives the host from ``server.host``.  Ports always come from the
    existing ``server.port``, ``server.api_port``, and ``server.otlp_port``
    fields.
    """
    server = config.get("server", {})
    base_url = server.get("base_url")
    if base_url:
        base = base_url.rstrip("/")
    else:
        host = str(server.get("host", "127.0.0.1"))
        if host in ("0.0.0.0", "127.0.0.1"):
            host = "localhost"
        base = f"http://{host}"
    port = int(server.get("port", 4000))
    api_port = int(server.get("api_port", port + 1))
    otlp_port = int(server.get("otlp_port", api_port + 1))
    return {
        "proxy_url": f"{base}:{port}",
        "api_url": f"{base}:{api_port}",
        "otlp_url": f"{base}:{otlp_port}",
    }


def load_server_config() -> ServerConfig:
    config_path = os.path.expanduser("~/.llm-tracker/config.yaml")
    try:
        with open(config_path, encoding="utf-8") as config_file:
            cfg = yaml.safe_load(config_file) or {}
    except OSError:
        cfg = {}

    server = cfg.get("server", {})
    host = str(server.get("host", "127.0.0.1"))
    base_url = server.get("base_url")
    port = int(server.get("port", 4000))
    otlp_host, otlp_port = _resolve_otlp_host_port(cfg)

    return ServerConfig(
        host=host,
        port=port,
        api_port=int(server.get("api_port", port + 1)),
        otlp_host=otlp_host,
        otlp_port=otlp_port,
        base_url=base_url,
    )
