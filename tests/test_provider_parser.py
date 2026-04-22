from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def provider_parser_module(load_module) -> pytest.ModuleType:
    return load_module("src.provider_parser")


def _write_claude_settings(home: Path, base_url: str | None) -> None:
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    if base_url is None:
        settings.write_text("{}", encoding="utf-8")
        return
    settings.write_text(
        json.dumps({"env": {"ANTHROPIC_BASE_URL": base_url}}), encoding="utf-8"
    )


def _write_codex_config(home: Path, base_url: str | None) -> None:
    config = home / ".codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    if base_url is None:
        config.write_text("", encoding="utf-8")
        return
    config.write_text(f'base_url = "{base_url}"', encoding="utf-8")


def _write_gemini_settings(home: Path, base_url: str | None) -> None:
    settings = home / ".gemini" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    if base_url is None:
        settings.write_text("{}", encoding="utf-8")
        return
    settings.write_text(json.dumps({"base_url": base_url}), encoding="utf-8")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://api.minimaxi.com/v1", "MiniMax"),
        ("https://free.codesonline.dev", "codesonline"),
        ("https://vectorengine.com", "vectorengine"),
        ("https://api.anthropic.com", "Anthropic"),
        ("https://api.openai.com/v1", "OpenAI"),
        ("https://api.github.com", "GitHub"),
        ("https://my-resource.openai.azure.com", "Azure"),
        ("https://generativelanguage.googleapis.com", "Google"),
        ("https://bedrock-runtime.us-east-1.amazonaws.com", "AWS"),
        ("http://localhost:8080", "local"),
        ("http://127.0.0.1:11434", "local"),
        ("https://unknown.com", "unknown"),
    ],
)
def test_match_url_to_provider(provider_parser_module, url, expected):
    assert provider_parser_module._match_url_to_provider(url) == expected


class TestParseProvider:
    def test_claude_provider(self, provider_parser_module, isolated_home: Path):
        _write_claude_settings(isolated_home, "https://api.anthropic.com")
        assert provider_parser_module.parse_provider("claude") == "Anthropic"

    def test_codex_provider(self, provider_parser_module, isolated_home: Path):
        _write_codex_config(isolated_home, "https://api.openai.com/v1")
        assert provider_parser_module.parse_provider("codex") == "OpenAI"

    def test_gemini_provider(self, provider_parser_module, isolated_home: Path):
        _write_gemini_settings(
            isolated_home, "https://generativelanguage.googleapis.com"
        )
        assert provider_parser_module.parse_provider("gemini") == "Google"

    def test_claude_fallback(self, provider_parser_module, isolated_home: Path):
        _write_claude_settings(isolated_home, None)
        assert provider_parser_module.parse_provider("claude") == "anthropic"

    def test_codex_fallback(self, provider_parser_module, isolated_home: Path):
        _write_codex_config(isolated_home, None)
        assert provider_parser_module.parse_provider("codex") == "openai"

    def test_gemini_fallback(self, provider_parser_module, isolated_home: Path):
        _write_gemini_settings(isolated_home, None)
        assert provider_parser_module.parse_provider("gemini") == "google"

    def test_unknown_agent_fallback(self, provider_parser_module, isolated_home: Path):
        assert provider_parser_module.parse_provider("unknown-agent") == "unknown"

    def test_codex_unknown_url_fallback(
        self, provider_parser_module, isolated_home: Path
    ):
        # This currently falls back to 'openai'
        _write_codex_config(isolated_home, "https://unknown.example.com")
        assert provider_parser_module.parse_provider("codex") == "openai"

    def test_codex_codesonline_provider(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_codex_config(isolated_home, "https://free.codesonline.dev")
        assert provider_parser_module.parse_provider("codex") == "codesonline"
