import json
import os
import shutil
import subprocess
import sys

import httpx
import yaml


def load_config():
    config_path = os.path.expanduser(
        os.environ.get("TOKENAGE_CONFIG", "~/.tokenage/config.yaml")
    )
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def get_otlp_url(config):
    """Build OTLP server URL from config."""
    from urllib.parse import urlparse

    server = config.get("server", {})
    otlp_port = server.get("otlp_port", 4002)
    base_url = server.get("base_url")
    if base_url:
        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
    else:
        host = server.get("host", "127.0.0.1")
    return f"http://{host}:{otlp_port}"


def check_otlp_health(otlp_url):
    """Make an actual request to the OTLP server /health endpoint."""
    try:
        resp = httpx.get(f"{otlp_url}/health", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                return True
    except Exception:
        pass
    return False


def status_payload():
    """Ask the installed client for this machine's agent wiring."""
    launcher = shutil.which("tokenage")
    if launcher is None:
        return None
    try:
        result = subprocess.run(
            [launcher, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # Exit 1 means a miswired agent; the JSON still names it.
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def main():
    config = load_config()
    if config is None:
        return 0

    # A live collector means agents are reporting; nothing to warn about.
    if check_otlp_health(get_otlp_url(config)):
        return 0

    # Otherwise let the local client name the detected agents that are unwired.
    payload = status_payload()
    if payload is None:
        return 0
    detected = payload.get("detected")
    health = payload.get("agents")
    if not isinstance(detected, dict) or not isinstance(health, dict):
        return 0

    errors = []
    for name, info in detected.items():
        if not isinstance(info, dict) or not info.get("found"):
            continue
        agent_health = health.get(name)
        status = agent_health.get("status") if isinstance(agent_health, dict) else None
        if status != "ready":
            errors.append(f"❌ OTLP tracking not ready for {name} (Status: {status})")

    if errors:
        print("\n".join(errors))
        print("Run tokenage setup to repair agent tracking.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
