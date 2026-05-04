"""Rule-based provider parser for coding agents.

Reads agent config files to find base URLs, then maps them to provider names.
"""

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# URL-based provider mapping rules (checked in order)
PROVIDER_RULES: list[tuple[str, str]] = [
    ("api.minimaxi", "MiniMax"),
    ("xiaomimimo", "Xiaomi"),
    ("api.anthropic", "Anthropic"),
    ("api.openai", "OpenAI"),
    ("api.github", "GitHub"),
    ("azure", "Azure"),
    ("google", "Google"),
    ("amazon", "AWS"),
    ("localhost", "local"),
    ("127.0.0.1", "local"),
]


def _load_json(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _load_toml(path: Path) -> Optional[dict]:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _extract_url(config: dict, *keys: str) -> Optional[str]:
    # First try explicit dotted key paths (e.g. "env.ANTHROPIC_BASE_URL")
    for key in keys:
        val = config
        for part in key.split("."):
            if isinstance(val, dict):
                val = val.get(part)
            else:
                val = None
                break
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    # Then search nested sections (e.g. model_providers.*.base_url)
    return _find_url_in_nested(config, set(keys))


def _find_url_in_nested(obj: dict, keys: set[str]) -> Optional[str]:
    for key in keys:
        if key in obj:
            val = obj[key]
            if isinstance(val, str) and val.startswith("http"):
                return val
    for val in obj.values():
        if isinstance(val, dict):
            found = _find_url_in_nested(val, keys)
            if found:
                return found
    return None


def _match_url_to_provider(url: str) -> str:
    for pattern, provider in PROVIDER_RULES:
        if pattern in url:
            return provider
    return "unknown"


def _derive_provider_from_base_url(url: str) -> str | None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip(".").lower()
    if not hostname:
        return None

    if hostname == "localhost" or "." not in hostname:
        return hostname

    parts = hostname.split(".")
    if len(parts) < 2:
        return None

    if (
        len(parts) >= 3
        and len(parts[-1]) == 2
        and parts[-2] in {"ac", "co", "com", "edu", "gov", "net", "org"}
    ):
        return parts[-3]

    return parts[-2]


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    base_url: str | None
    source: str | None


def parse_claude_base_url() -> Optional[str]:
    """Parse Claude Code base URL from ~/.claude/settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    config = _load_json(settings_path)
    if not config:
        return None
    return _extract_url(config, "env.ANTHROPIC_BASE_URL", "base_url", "url")


def _load_codex_config() -> Optional[dict]:
    """Load Codex config, merging $CODEX_HOME/config.toml over global."""
    config = _load_toml(Path.home() / ".codex" / "config.toml") or {}
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        override = _load_toml(Path(codex_home) / "config.toml")
        if override:
            config.update(override)
    return config or None


def parse_codex_base_url() -> Optional[str]:
    """Parse Codex base URL from config.toml.

    Reads ~/.codex/config.toml first, then merges $CODEX_HOME/config.toml
    on top so project-level overrides take precedence.
    """
    config = _load_codex_config()
    if not config:
        return None
    return _extract_url(config, "base_url", "url", "api_base_url")


def parse_gemini_base_url() -> Optional[str]:
    """Parse Gemini CLI base URL from ~/.gemini/settings.json."""
    settings_path = Path.home() / ".gemini" / "settings.json"
    config = _load_json(settings_path)
    if not config:
        return None
    return _extract_url(config, "base_url", "url", "api_base_url")


PROVIDER_DEFAULTS: dict[str, str] = {
    "claude": "anthropic",
    "codex": "openai",
    "gemini": "google",
}


def parse_provider_metadata(agent: str) -> ProviderMetadata:
    """Parse provider/base URL metadata for a coding agent config."""
    if agent == "claude":
        base_url = parse_claude_base_url()
        source = "claude_settings"
    elif agent == "codex":
        base_url = parse_codex_base_url()
        source = "codex_config"
    elif agent == "gemini":
        base_url = parse_gemini_base_url()
        source = "gemini_settings"
    else:
        return ProviderMetadata(
            provider=PROVIDER_DEFAULTS.get(agent, "unknown"),
            base_url=None,
            source=None,
        )

    provider = _match_url_to_provider(base_url) if base_url else "unknown"
    if provider == "unknown" and base_url:
        provider = _derive_provider_from_base_url(base_url) or "unknown"
    if provider == "unknown":
        provider = PROVIDER_DEFAULTS.get(agent, "unknown")

    return ProviderMetadata(provider=provider, base_url=base_url, source=source)


def parse_provider(agent: str) -> str:
    """Parse provider for a coding agent, with fallback to default."""
    return parse_provider_metadata(agent).provider
