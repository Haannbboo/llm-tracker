from unittest.mock import patch


def test_script_exits_zero_when_server_down():
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check-otlp-ready.py"
    spec = importlib.util.spec_from_file_location("check_otlp_ready", script_path)
    check_otlp_ready = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(check_otlp_ready)

    with patch("httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        assert check_otlp_ready.main() == 0


def test_script_exits_zero_when_config_missing(monkeypatch):
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check-otlp-ready.py"
    spec = importlib.util.spec_from_file_location("check_otlp_ready", script_path)
    check_otlp_ready = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_otlp_ready)

    # When config file doesn't exist, get_api_url returns None and main exits early
    monkeypatch.setenv("LLM_TRACKER_CONFIG", "/tmp/non-existent-config.yaml")
    assert check_otlp_ready.main() == 0


def test_script_uses_custom_port_from_config(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path
    from unittest.mock import patch

    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check-otlp-ready.py"
    spec = importlib.util.spec_from_file_location("check_otlp_ready", script_path)
    check_otlp_ready = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_otlp_ready)

    config_file = tmp_path / "config.yaml"
    config_data = {"server": {"api_port": 5001}}
    config_file.write_text(yaml.dump(config_data))

    monkeypatch.setenv("LLM_TRACKER_CONFIG", str(config_file))
    with patch("httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        assert check_otlp_ready.main() == 0
        # Should have tried to connect to custom port 5001
        mock_get.assert_called_with("http://127.0.0.1:5001/config", timeout=2.0)


def test_script_exits_zero_when_port_not_determinable(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path

    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check-otlp-ready.py"
    spec = importlib.util.spec_from_file_location("check_otlp_ready", script_path)
    check_otlp_ready = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_otlp_ready)

    # Config exists but neither api_port nor port is available
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"server": {}}))
    monkeypatch.setenv("LLM_TRACKER_CONFIG", str(config_file))
    assert check_otlp_ready.main() == 0


def test_script_fails_when_detected_agent_not_ready():
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check-otlp-ready.py"
    spec = importlib.util.spec_from_file_location("check_otlp_ready", script_path)
    check_otlp_ready = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(check_otlp_ready)

    with patch("httpx.get") as mock_get:

        def side_effect(url, **kwargs):
            mock = MagicMock()
            mock.status_code = 200
            if "/config" in url:
                mock.json.return_value = {"status": "ok"}
            elif "/local/agents" in url:
                mock.json.return_value = {
                    "claude": {"found": True},
                    "gemini": {"found": False},
                }
            elif "/local/setup-health" in url:
                mock.json.return_value = {
                    "agents": {
                        "claude": {"status": "missing_config"},
                        "gemini": {"status": "missing_config"},
                    }
                }
            return mock

        mock_get.side_effect = side_effect
        assert check_otlp_ready.main() == 1


def test_script_passes_when_detected_agents_ready():
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check-otlp-ready.py"
    spec = importlib.util.spec_from_file_location("check_otlp_ready", script_path)
    check_otlp_ready = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(check_otlp_ready)

    with patch("httpx.get") as mock_get:

        def side_effect(url, **kwargs):
            mock = MagicMock()
            mock.status_code = 200
            if "/config" in url:
                mock.json.return_value = {"status": "ok"}
            elif "/local/agents" in url:
                mock.json.return_value = {
                    "claude": {"found": True},
                    "gemini": {"found": False},
                }
            elif "/local/setup-health" in url:
                mock.json.return_value = {
                    "agents": {
                        "claude": {"status": "ready"},
                        "gemini": {"status": "missing_config"},
                    }
                }
            return mock

        mock_get.side_effect = side_effect
        assert check_otlp_ready.main() == 0
