import os
import sys

import httpx
import yaml


def get_api_url():
    config_path = os.path.expanduser(
        os.environ.get("LLM_TRACKER_CONFIG", "~/.llm-tracker/config.yaml")
    )
    port = 4001
    host = "127.0.0.1"
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
                server = config.get("server", {})
                host = server.get("host", "127.0.0.1")
                port = server.get("api_port", server.get("port", 4000) + 1)
        except Exception:
            pass
    return f"http://{host}:{port}"


def main():
    base_url = get_api_url()
    try:
        httpx.get(f"{base_url}/config", timeout=2.0)
    except Exception:
        # Server is down or unreachable, skip check
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
