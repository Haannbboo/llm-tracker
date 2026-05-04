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
        ("https://token-plan-sgp.xiaomimimo.com/anthropic", "Xiaomi"),
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


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://free.codesonline.dev", "codesonline"),
        ("https://vectorengine.com", "vectorengine"),
        ("https://api.example.com/v1", "example"),
        ("http://localhost:8080", "localhost"),
        ("not-a-url", None),
    ],
)
def test_derive_provider_from_base_url(provider_parser_module, url, expected):
    assert provider_parser_module._derive_provider_from_base_url(url) == expected


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
        _write_codex_config(isolated_home, "https://unknown.example.com")
        assert provider_parser_module.parse_provider("codex") == "example"

    def test_codex_codesonline_provider(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_codex_config(isolated_home, "https://free.codesonline.dev")
        assert provider_parser_module.parse_provider("codex") == "codesonline"

    def test_claude_unknown_url_uses_domain_stem(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_claude_settings(
            isolated_home, "https://token-plan-sgp.xiaomimimo.com/anthropic"
        )
        assert provider_parser_module.parse_provider("claude") == "Xiaomi"


class TestCodexHomeOverride:
    def test_codex_home_overrides_global(
        self,
        provider_parser_module,
        isolated_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _write_codex_config(isolated_home, "https://api.openai.com/v1")
        codex_home = isolated_home / "project-codex"
        codex_home.mkdir()
        (codex_home / "config.toml").write_text(
            'base_url = "https://proxy.company.com/v1"', encoding="utf-8"
        )
        monkeypatch.setenv("CODEX_HOME", str(codex_home))
        assert provider_parser_module.parse_provider("codex") == "company"

    def test_codex_home_without_global(
        self,
        provider_parser_module,
        isolated_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _write_codex_config(isolated_home, None)
        codex_home = isolated_home / "project-codex"
        codex_home.mkdir()
        (codex_home / "config.toml").write_text(
            'base_url = "https://proxy.company.com/v1"', encoding="utf-8"
        )
        monkeypatch.setenv("CODEX_HOME", str(codex_home))
        assert provider_parser_module.parse_provider("codex") == "company"

    def test_codex_home_not_set_uses_global(
        self, provider_parser_module, isolated_home: Path
    ):
        _write_codex_config(isolated_home, "https://api.anthropic.com")
        assert provider_parser_module.parse_provider("codex") == "Anthropic"

    def test_codex_home_metadata_source(
        self,
        provider_parser_module,
        isolated_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _write_codex_config(isolated_home, "https://api.openai.com/v1")
        codex_home = isolated_home / "project-codex"
        codex_home.mkdir()
        (codex_home / "config.toml").write_text(
            'base_url = "https://proxy.company.com/v1"', encoding="utf-8"
        )
        monkeypatch.setenv("CODEX_HOME", str(codex_home))
        metadata = provider_parser_module.parse_provider_metadata("codex")
        assert metadata.base_url == "https://proxy.company.com/v1"
        assert metadata.source == "codex_config"

    def test_codex_home_nested_model_providers(
        self,
        provider_parser_module,
        isolated_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _write_codex_config(isolated_home, None)
        codex_home = isolated_home / "project-codex"
        codex_home.mkdir()
        (codex_home / "config.toml").write_text(
            'model = "gpt-4.1"\n\n[model_providers.bench_target]\n'
            'name = "Benchmark Target"\nwire_api = "responses"\n'
            'base_url = "https://router.example.com/v1"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("CODEX_HOME", str(codex_home))
        assert provider_parser_module.parse_provider("codex") == "example"


def test_parse_provider_metadata_returns_base_url_and_source(
    provider_parser_module, isolated_home: Path
):
    _write_codex_config(isolated_home, "https://unknown.example.com")

    metadata = provider_parser_module.parse_provider_metadata("codex")

    assert metadata.provider == "example"
    assert metadata.base_url == "https://unknown.example.com"
    assert metadata.source == "codex_config"
