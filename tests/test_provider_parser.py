from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def provider_parser_module(load_module) -> pytest.ModuleType:
    return load_module("src.provider_parser")


def _write_claude_settings(home: Path, base_url: str | None) -> None:
    settings = home / ".claude" / "settings.json"
    if base_url is None:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("{}", encoding="utf-8")
        return
    settings.parent.mkdir(parents=True, exist_ok=True)
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
    if base_url is None:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("{}", encoding="utf-8")
        return
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({"base_url": base_url}), encoding="utf-8")


class TestParseClaudeProvider:
    def test_minimaxi_url(self, provider_parser_module, isolated_home: Path):
        _write_claude_settings(isolated_home, "https://api.minimaxi.com/anthropic")
        result = provider_parser_module.parse_claude_provider()
        assert result == "MiniMax"

    def test_vectorengine_url(self, provider_parser_module, isolated_home: Path):
        _write_claude_settings(isolated_home, "https://vectorengine.example.com")
        result = provider_parser_module.parse_claude_provider()
        assert result == "vectorengine"

    def test_anthropic_url(self, provider_parser_module, isolated_home: Path):
        _write_claude_settings(isolated_home, "https://api.anthropic.com")
        result = provider_parser_module.parse_claude_provider()
        assert result == "Anthropic"

    def test_missing_file(self, provider_parser_module, isolated_home: Path):
        result = provider_parser_module.parse_claude_provider()
        assert result == "unknown"

    def test_empty_config(self, provider_parser_module, isolated_home: Path):
        _write_claude_settings(isolated_home, None)
        result = provider_parser_module.parse_claude_provider()
        assert result == "unknown"


class TestParseCodexProvider:
    def test_openai_url(self, provider_parser_module, isolated_home: Path):
        _write_codex_config(isolated_home, "https://api.openai.com/v1")
        result = provider_parser_module.parse_codex_provider()
        assert result == "OpenAI"

    def test_azure_url(self, provider_parser_module, isolated_home: Path):
        _write_codex_config(isolated_home, "https://myaccount.openai.azure.com")
        result = provider_parser_module.parse_codex_provider()
        assert result == "Azure"

    def test_missing_file(self, provider_parser_module, isolated_home: Path):
        result = provider_parser_module.parse_codex_provider()
        assert result == "unknown"

    def test_empty_config(self, provider_parser_module, isolated_home: Path):
        _write_codex_config(isolated_home, None)
        result = provider_parser_module.parse_codex_provider()
        assert result == "unknown"


class TestParseGeminiProvider:
    def test_google_url(self, provider_parser_module, isolated_home: Path):
        _write_gemini_settings(
            isolated_home, "https://generativelanguage.googleapis.com"
        )
        result = provider_parser_module.parse_gemini_provider()
        assert result == "Google"

    def test_missing_file(self, provider_parser_module, isolated_home: Path):
        result = provider_parser_module.parse_gemini_provider()
        assert result == "unknown"

    def test_empty_config(self, provider_parser_module, isolated_home: Path):
        _write_gemini_settings(isolated_home, None)
        result = provider_parser_module.parse_gemini_provider()
        assert result == "unknown"


class TestParseProvider:
    def test_claude_falls_back_to_anthropic(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_claude_settings(isolated_home, None)
        result = provider_parser_module.parse_provider("claude")
        assert result == "anthropic"

    def test_codex_falls_back_to_openai(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_codex_config(isolated_home, None)
        result = provider_parser_module.parse_provider("codex")
        assert result == "openai"

    def test_gemini_falls_back_to_google(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_gemini_settings(isolated_home, None)
        result = provider_parser_module.parse_provider("gemini")
        assert result == "google"

    def test_unknown_agent(self, provider_parser_module, isolated_home: Path):
        result = provider_parser_module.parse_provider("unknown-agent")
        assert result == "unknown"

    def test_claude_url_overrides_default(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_claude_settings(isolated_home, "https://api.minimaxi.com/anthropic")
        result = provider_parser_module.parse_provider("claude")
        assert result == "MiniMax"
