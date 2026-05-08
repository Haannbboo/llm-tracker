"""Tests for the _read_port YAML parser defined in bootstrap.sh."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_read_port(
    config_path: Path, key: str, default: int | str
) -> subprocess.CompletedProcess:
    """Run the _read_port function against *config_path* via a bash subprocess."""
    return subprocess.run(
        [
            "bash",
            "-c",
            f"""
            _read_port() {{
                local key="$1" default="$2"
                local val
                val="$(grep -E "^\\s+${{key}}:" "{config_path}" 2>/dev/null | head -1 | awk '{{print $2}}')"
                if [[ -n "${{val}}" && "${{val}}" =~ ^[0-9]+$ ]]; then
                    echo "${{val}}"
                else
                    echo "${{default}}"
                fi
            }}
            _read_port {key} {default}
            """,
        ],
        capture_output=True,
        text=True,
    )


def test_reads_simple_port_value(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 5010\n", encoding="utf-8")

    result = _run_read_port(config, "port", 4000)
    assert result.stdout.strip() == "5010"


def test_returns_default_for_missing_key(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 5010\n", encoding="utf-8")

    result = _run_read_port(config, "otlp_port", 4002)
    assert result.stdout.strip() == "4002"


def test_ignores_trailing_comment(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 5010  # custom port\n", encoding="utf-8")

    result = _run_read_port(config, "port", 4000)
    assert result.stdout.strip() == "5010"


def test_returns_default_for_quoted_value(tmp_path):
    """Quoted values like `port: "5010"` are non-numeric after awk, so default is returned."""
    config = tmp_path / "config.yaml"
    config.write_text('server:\n  port: "5010"\n', encoding="utf-8")

    result = _run_read_port(config, "port", 4000)
    # awk prints `"5010"` which fails the numeric regex
    assert result.stdout.strip() == "4000"


def test_returns_default_for_empty_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")

    result = _run_read_port(config, "port", 4000)
    assert result.stdout.strip() == "4000"


def test_returns_default_for_non_numeric_value(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: abc\n", encoding="utf-8")

    result = _run_read_port(config, "port", 4000)
    assert result.stdout.strip() == "4000"
