import os
import sys

import httpx
import yaml


def load_config():
    config_path = os.path.expanduser(
        os.environ.get("LLM_TRACKER_CONFIG", "~/.llm-tracker/config.yaml")
    )
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def get_api_url(config):
    server = config.get("server", {})
    host = server.get("host", "127.0.0.1")
    api_port = server.get("api_port")
    if api_port is None and isinstance(server.get("port"), int):
        api_port = server["port"] + 1
    if not isinstance(api_port, int):
        return None
    return f"http://{host}:{api_port}"


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


def main():
    config = load_config()
    if config is None:
        return 0

    # First, make an actual request to the OTLP server
    otlp_url = get_otlp_url(config)
    if check_otlp_health(otlp_url):
        return 0

    # OTLP server is not responding — fall back to API agent health check
    base_url = get_api_url(config)
    if base_url is None:
        return 0
    try:
        httpx.get(f"{base_url}/config", timeout=2.0)
    except Exception:
        # API server is down or unreachable, skip check
        return 0

    try:
        agents_resp = httpx.get(f"{base_url}/local/agents", timeout=2.0)
        health_resp = httpx.get(f"{base_url}/local/setup-health", timeout=2.0)

        if agents_resp.status_code != 200 or health_resp.status_code != 200:
            return 0

        detected = agents_resp.json()
        health = health_resp.json().get("agents", {})

        errors = []
        for name, info in detected.items():
            if info.get("found"):
                agent_health = health.get(name, {})
                if agent_health.get("status") != "ready":
                    errors.append(
                        f"❌ OTLP tracking not ready for {name} (Status: {agent_health.get('status')})"
                    )

        if errors:
            print("\n".join(errors))
            print("Check Settings -> OTLP Tracking Setup in the dashboard to fix.")
            return 1

    except Exception as e:
        print(f"Warning: OTLP readiness check failed: {e}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
