#!/usr/bin/env python3
"""Read OTLP port and host from config.yaml. Prints '<port> <host>'."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not config_path:
        print("4002 localhost")
        return

    try:
        config = yaml.safe_load(Path(config_path).read_text()) or {}
    except OSError:
        print("4002 localhost")
        return

    server = config.get("server", {})
    port = server.get("otlp_port", 4002)

    base_url = server.get("base_url")
    if base_url:
        host = urlparse(base_url).hostname or "localhost"
    elif server.get("host", "127.0.0.1") in ("0.0.0.0", "127.0.0.1"):
        host = "localhost"
    else:
        host = server.get("host", "localhost")

    print(f"{port} {host}")


if __name__ == "__main__":
    main()
