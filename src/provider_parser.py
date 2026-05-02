"""Rule-based provider parser for coding agents.

Reads agent config files to find base URLs, then maps them to provider names.
"""

import json
import re
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


def _parse_toml_basic(content: str) -> Optional[dict]:
    """Minimal TOML parser for base_url only."""
    m = re.search(r'base_url\s*=\s*"([^"]+)"', content)
    if m:
        return {"base_url": m.group(1)}
    return None


def _load_json(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _load_toml(path: Path) -> Optional[dict]:
    try:
        with open(path, "rb") as f:
            content = f.read().decode("utf-8")
    except OSError:
        return None
    return _parse_toml_basic(content)


def _extract_url(config: dict, *keys: str) -> Optional[str]:
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


def parse_codex_base_url() -> Optional[str]:
    """Parse Codex base URL from ~/.codex/config.toml."""
    settings_path = Path.home() / ".codex" / "config.toml"
    config = _load_toml(settings_path)
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
