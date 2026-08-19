from config.server_config import resolve_server_urls


def test_resolve_server_urls_uses_scheme_and_configured_ports():
    urls = resolve_server_urls(
        {
            "server": {
                "base_url": "https://tracker.example:8443/proxy",
                "port": 4007,
                "api_port": 4004,
                "otlp_port": 4005,
            }
        }
    )

    assert urls == {
        "proxy_url": "https://tracker.example:4007",
        "api_url": "https://tracker.example:4004",
        "otlp_url": "https://tracker.example:4005",
    }


def test_resolve_server_urls_falls_back_for_malformed_base_url():
    urls = resolve_server_urls(
        {
            "server": {
                "base_url": "https://",
                "host": "10.0.0.8",
                "port": 4107,
                "api_port": 4104,
                "otlp_port": 4105,
            }
        }
    )

    assert urls == {
        "proxy_url": "http://10.0.0.8:4107",
        "api_url": "http://10.0.0.8:4104",
        "otlp_url": "http://10.0.0.8:4105",
    }
