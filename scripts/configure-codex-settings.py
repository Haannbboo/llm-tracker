#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

_GRAY = "\033[38;2;102;102;102m" if sys.stdout.isatty() else ""
_RESET = "\033[0m" if sys.stdout.isatty() else ""


def _info(msg: str) -> None:
    print(f"  {_GRAY}{msg}{_RESET}")


def _write_private(path: Path, content: str) -> None:
    if path.exists():
        path.chmod(0o600)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def load_ingest_token() -> str | None:
    try:
        credentials = json.loads(
            (Path.home() / ".llm-tracker" / "credentials.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    token = credentials.get("ingest_token") if isinstance(credentials, dict) else None
    return token if isinstance(token, str) and token else None


def resolve_otlp_logs_endpoint(
    otlp_port: str, host: str = "localhost", endpoint: str | None = None
) -> str:
    """Return explicit OTLP logs endpoint override or localhost port default."""
    env_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if env_endpoint:
        return env_endpoint
    if endpoint and "://" in endpoint:
        return endpoint
    return f"http://{host}:{otlp_port}/v1/logs"


def _headers_value(token: str) -> str:
    return f'{{ "x-llm-tracker-token" = {json.dumps(token)} }}'


def _set_section_headers(body: str, token: str | None) -> str:
    if not token:
        return re.sub(r"(?m)^headers\s*=.*\n?", "", body)
    line = f"headers = {_headers_value(token)}"
    if re.search(r"(?m)^headers\s*=", body):
        return re.sub(r"(?m)^headers\s*=.*$", line, body, count=1)
    return body.rstrip() + "\n" + line + "\n"


def _set_inline_headers(line: str, token: str | None) -> str:
    if not token:
        return re.sub(r",\s*headers\s*=\s*\{[^{}]*\}", "", line, count=1)
    headers = f"headers = {_headers_value(token)}"
    if re.search(r"headers\s*=\s*\{[^{}]*\}", line):
        return re.sub(r"headers\s*=\s*\{[^{}]*\}", headers, line, count=1)

    match = re.search(r"(?P<prefix>.*?)(?P<body>otlp-http\s*=\s*\{[^{}]*)\}", line)
    if not match:
        return line
    body = match.group("body").rstrip() + ", " + headers
    return match.group("prefix") + body + line[match.end("body") :]


def update_existing_otel_config(
    content: str, endpoint: str, token: str | None = None
) -> str:
    """Update Codex OTLP endpoint in inline or nested TOML config shapes."""
    # 1. Look for explicit [otel.exporter.otlp-http] block first
    # This is more specific and should be prioritized if it exists.
    section = re.search(
        r"(?ms)(^\[otel\.exporter\.otlp-http\]\s*)(.*?)(?=^\[|\Z)",
        content,
    )
    if section:
        body = section.group(2)
        if re.search(r"(?m)^endpoint\s*=", body):
            updated_body = re.sub(
                r"(?m)^endpoint\s*=.*$",
                f'endpoint = "{endpoint}"',
                body,
                count=1,
            )
        else:
            updated_body = f'endpoint = "{endpoint}"\n' + body
        updated_body = _set_section_headers(updated_body, token)
        return content[: section.start(2)] + updated_body + content[section.end(2) :]

    # 2. Look for a block starting with [otel]
    otel_match = re.search(r"(?ms)^\[otel\](.*?)(?=^\[|\Z)", content)
    if otel_match:
        otel_block = otel_match.group(1)
        # Check if exporter is defined within this [otel] block
        exporter_match = re.search(r"(?m)^\s*exporter\s*=\s*(.*)", otel_block)
        if exporter_match:
            exporter_line = exporter_match.group(0)
            # Update endpoint in the exporter line (handles both inline and complex values)
            if "endpoint" in exporter_line:
                new_exporter_line = re.sub(
                    r'(endpoint\s*=\s*")[^"]+(")',
                    rf"\g<1>{endpoint}\g<2>",
                    exporter_line,
                )
                new_exporter_line = _set_inline_headers(new_exporter_line, token)
                if new_exporter_line != exporter_line:
                    return content.replace(exporter_line, new_exporter_line)
                return content
            else:
                # Exporter exists but no endpoint key (e.g. inline table)
                if exporter_match.group(1).strip().startswith("{"):
                    new_exporter_val = exporter_match.group(1).strip()
                    # Add endpoint before the last closing brace
                    new_exporter_val = re.sub(
                        r"\}\s*\}$",
                        rf', endpoint = "{endpoint}", protocol = "json" }} }}',
                        new_exporter_val,
                    )
                    new_exporter_line = exporter_line.replace(
                        exporter_match.group(1), new_exporter_val
                    )
                    new_exporter_line = _set_inline_headers(new_exporter_line, token)
                    return content.replace(exporter_line, new_exporter_line)

        # If [otel] exists but no exporter found so far, check if we have any other [otel.exporter...] sections
        if not re.search(r"^\[otel\.exporter", content, re.M):
            # No existing exporter anywhere, add it safely inside the [otel] block
            headers = f", headers = {_headers_value(token)}" if token else ""
            new_otel_block = (
                otel_match.group(0).rstrip()
                + f'\nexporter = {{ otlp-http = {{ endpoint = "{endpoint}", protocol = "json"{headers} }} }}\n'
            )
            return content.replace(otel_match.group(0), new_otel_block)

    # 3. Nothing found, append new section
    headers = f", headers = {_headers_value(token)}" if token else ""
    return (
        content.rstrip()
        + f'\n\n[otel]\nenvironment = "dev"\nexporter = {{ otlp-http = {{ endpoint = "{endpoint}", protocol = "json"{headers} }} }}\n'
    )


def _strip_otel(body: str) -> str:
    """Drop the [otel] table and everything under it."""
    cleaned = re.sub(r"(?ms)^\[otel[^\]]*\]\s*.*?(?=^\[|\Z)", "", body)
    cleaned = re.sub(r"(?m)^otel\.exporter\s*=.*\n?", "", cleaned)
    cleaned = re.sub(r"(?m)^otel\.environment\s*=.*\n?", "", cleaned)
    return cleaned


def _disable(config_path: Path, expected_endpoint: str | None) -> int:
    """Remove llm-tracker's OTLP settings from a Codex config.

    A hand-written collector config is left alone: the block is only removed
    while its endpoint is the one llm-tracker wrote.
    """
    if not config_path.exists():
        _info(f"No Codex config at {config_path}")
        return 0
    content = config_path.read_text(encoding="utf-8")
    found = re.search(r"endpoint\s*=\s*[\"\']([^\"\']+)", content)
    if found and expected_endpoint and found.group(1) != expected_endpoint:
        print(
            f"{config_path} points at another collector ({found.group(1)}); left alone",
            file=sys.stderr,
        )
        return 0
    new_content = _strip_otel(content)
    if new_content == content:
        _info(f"No llm-tracker telemetry in {config_path}")
        return 0
    _write_private(config_path, new_content)
    _info(f"Codex OTLP telemetry removed from {config_path}")
    return 0


def main():
    argv = sys.argv[1:]
    disable = False
    if "--disable" in argv:
        disable = True
        argv = [arg for arg in argv if arg != "--disable"]
    if len(argv) not in (1, 2, 3, 4, 5):
        print(
            "usage: configure-codex-settings.py CONFIG_PATH "
            "[--disable [ENDPOINT]] | [OTLP_PORT] [HOST] [ENDPOINT] [TOKEN]",
            file=sys.stderr,
        )
        return 1

    config_path = Path(argv[0]).expanduser()
    if disable:
        # ENDPOINT is the one llm-tracker wrote; anything else is the user's.
        return _disable(config_path, argv[1] if len(argv) >= 2 else None)
    otlp_port = argv[1] if len(argv) >= 2 else "4002"
    host = argv[2] if len(argv) >= 3 else "localhost"
    endpoint = argv[3] if len(argv) >= 4 else None
    token = (
        argv[4]
        if len(argv) >= 5
        else os.environ.get("LLM_TRACKER_INGEST_TOKEN") or load_ingest_token()
    )

    if not config_path.parent.exists():
        # Same marker as the plugin scripts' warn_skip(): `llm-tracker login`
        # reads it to avoid reporting a skipped agent as wired.
        print(
            f"WARNING: {config_path.parent} does not exist; skipping Codex configuration",
            file=sys.stderr,
        )
        return 0

    content = ""
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")

    endpoint = resolve_otlp_logs_endpoint(otlp_port, host, endpoint)

    new_content = update_existing_otel_config(content, endpoint, token)
    if new_content != content:
        _write_private(config_path, new_content)
        _info(f"Codex OTLP telemetry updated to {endpoint} in {config_path}")
    else:
        _info(f"Codex OTLP telemetry already up-to-date in {config_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
