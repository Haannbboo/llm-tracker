import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml


def _load_script():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check-otlp-ready.py"
    spec = importlib.util.spec_from_file_location("check_otlp_ready", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_script_exits_zero_when_otlp_unreachable_and_client_absent():
    module = _load_script()

    with patch("httpx.get", side_effect=Exception("Connection refused")):
        with patch.object(module, "client_health_payload", return_value=None):
            assert module.main() == 0


def test_script_exits_zero_when_config_missing(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("TOKENAGE_CONFIG", "/tmp/non-existent-config.yaml")
    assert module.main() == 0


def test_script_checks_the_configured_otlp_port(monkeypatch, tmp_path):
    module = _load_script()
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"server": {"otlp_port": 5002}}))
    monkeypatch.setenv("TOKENAGE_CONFIG", str(config_file))

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"status": "ok"}
        )
        assert module.main() == 0

    mock_get.assert_called_with("http://127.0.0.1:5002/health", timeout=2.0)


def test_script_exits_zero_when_otlp_healthy_even_with_unwired_agents():
    module = _load_script()

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"status": "ok"}
        )
        with patch.object(module, "client_health_payload") as payload:
            assert module.main() == 0
    payload.assert_not_called()


def test_script_fails_when_detected_agent_not_ready():
    module = _load_script()

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=503)
        with patch.object(
            module,
            "client_health_payload",
            return_value={
                "detected": {"claude": {"found": True}, "codex": {"found": False}},
                "agents": {"claude": {"status": "missing_config"}},
            },
        ):
            assert module.main() == 1


def test_script_passes_when_detected_agents_ready():
    module = _load_script()

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=503)
        with patch.object(
            module,
            "client_health_payload",
            return_value={
                "detected": {"claude": {"found": True}, "codex": {"found": False}},
                "agents": {"claude": {"status": "ready"}},
            },
        ):
            assert module.main() == 0


def test_script_ignores_undetected_agents():
    module = _load_script()

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=503)
        with patch.object(
            module,
            "client_health_payload",
            return_value={
                "detected": {"claude": {"found": False}},
                "agents": {"claude": {"status": "missing_config"}},
            },
        ):
            assert module.main() == 0
