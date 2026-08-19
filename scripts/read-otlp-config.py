#!/usr/bin/env python3
"""Read OTLP connection details from config.yaml.

The default output is ``<port> <host>`` for existing callers. Pass
``--endpoint`` to print the full scheme-aware logs endpoint.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.server_config import resolve_server_urls


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    endpoint_mode = len(sys.argv) > 2 and sys.argv[2] == "--endpoint"
    if not config_path:
        print("http://localhost:4002/v1/logs" if endpoint_mode else "4002 localhost")
        return

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except OSError:
        print("http://localhost:4002/v1/logs" if endpoint_mode else "4002 localhost")
        return

    urls = resolve_server_urls(config)
    if endpoint_mode:
        print(f"{urls['otlp_url']}/v1/logs")
    else:
        parsed = urlparse(urls["otlp_url"])
        host = parsed.hostname or "localhost"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        print(f"{parsed.port or 4002} {host}")


if __name__ == "__main__":
    main()
