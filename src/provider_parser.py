"""Rule-based provider parser for coding agents.

Reads agent config files to find base URLs, then maps them to provider names.
"""

import json
import re
from pathlib import Path
from typing import Optional

# URL-based provider mapping rules (checked in order)
PROVIDER_RULES: list[tuple[str, str]] = [
    ("api.minimaxi", "MiniMax"),
    ("vectorengine", "vectorengine"),
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


def parse_claude_provider() -> str:
    """Parse Claude Code provider from ~/.claude/settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    config = _load_json(settings_path)
    if not config:
        return "unknown"

    base_url = _extract_url(config, "env.ANTHROPIC_BASE_URL", "base_url", "url")
    if not base_url:
        return "unknown"

    return _match_url_to_provider(base_url)


def parse_codex_provider() -> str:
    """Parse Codex provider from ~/.codex/config.toml."""
    settings_path = Path.home() / ".codex" / "config.toml"
    config = _load_toml(settings_path)
    if not config:
        return "unknown"

    base_url = _extract_url(config, "base_url", "url", "api_base_url")
    if not base_url:
        return "unknown"

    return _match_url_to_provider(base_url)


def parse_gemini_provider() -> str:
    """Parse Gemini CLI provider from ~/.gemini/settings.json."""
    settings_path = Path.home() / ".gemini" / "settings.json"
    config = _load_json(settings_path)
    if not config:
        return "unknown"

    base_url = _extract_url(config, "base_url", "url", "api_base_url")
    if not base_url:
        return "unknown"

    return _match_url_to_provider(base_url)


PROVIDER_DEFAULTS: dict[str, str] = {
    "claude": "anthropic",
    "codex": "openai",
    "gemini": "google",
}


def parse_provider(agent: str) -> str:
    """Parse provider for a coding agent, with fallback to default."""
    if agent == "claude":
        result = parse_claude_provider()
    elif agent == "codex":
        result = parse_codex_provider()
    elif agent == "gemini":
        result = parse_gemini_provider()
    else:
        return PROVIDER_DEFAULTS.get(agent, "unknown")
    if result == "unknown":
        return PROVIDER_DEFAULTS.get(agent, "unknown")
    return result
