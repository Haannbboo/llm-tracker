"""Client URL resolution must agree with the independently installed server."""

from __future__ import annotations

import pytest
import yaml

from client import paths
from src.config.server_config import resolve_server_urls


@pytest.mark.parametrize(
    "section",
    [
        {},
        {"port": 5000},
        {"port": 5000, "api_port": 6000},
        {"port": 5000, "api_port": 6000, "otlp_port": 7000},
        {"host": "0.0.0.0"},
        {"host": "::"},
        {"host": "::1"},
        {"base_url": "https://tracker.example:8443/", "port": 5000},
        {"base_url": "tracker.example:8443", "api_port": 6000},
        {"base_url": "http://127.0.0.1", "otlp_port": 7000},
        {"base_url": "http://[::1]:8443/", "port": 5000},
        {"base_url": "[::1]:8443", "otlp_port": 7000},
    ],
)
def test_local_urls_match_server(section, tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"server": section}))
    monkeypatch.setenv("TOKENAGE_CONFIG", str(config))

    client = paths.local_server_info()
    server = resolve_server_urls({"server": section})

    assert client["api_url"] == server["api_url"]
    assert client["proxy_url"] == server["proxy_url"]
    assert client["otlp_logs_endpoint"] == f"{server['otlp_url']}/v1/logs"
