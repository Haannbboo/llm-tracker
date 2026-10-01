#!/usr/bin/env python3
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path

import tomllib

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


def update_existing_otel_config(
    content: str, endpoint: str, token: str | None = None
) -> str:
    """Configure only the logs HTTP exporter, preserving other OTEL settings."""
    parsed = tomllib.loads(content)
    otel = parsed.get("otel", {})
    if not isinstance(otel, dict):
        raise ValueError("unsupported Codex HTTP exporter layout; left unchanged")
    exporter = otel.get("exporter", {})
    if exporter == "none":
        exporter = {}
    if not isinstance(exporter, dict):
        raise ValueError("unsupported Codex HTTP exporter layout; left unchanged")
    http = exporter.get("otlp-http", {})
    http = deepcopy(http) if isinstance(http, dict) else {}
    http.update(endpoint=endpoint, protocol="json")
    headers = http.get("headers")
    headers = dict(headers) if isinstance(headers, dict) else {}
    if token:
        headers["x-llm-tracker-token"] = token
    else:
        headers.pop("x-llm-tracker-token", None)
    if headers:
        http["headers"] = headers
    else:
        http.pop("headers", None)

    desired = deepcopy(parsed)
    desired_otel = desired.setdefault("otel", {"environment": "dev"})
    desired_exporter = deepcopy(exporter)
    desired_exporter["otlp-http"] = http
    desired_otel["exporter"] = desired_exporter
    new_content = _edit_otel_config(content, parsed, exporter, http)
    # Validate both syntax and preservation before the caller writes anything.
    try:
        if tomllib.loads(new_content) != desired:
            raise ValueError("configuration values changed unexpectedly")
    except ValueError as exc:
        raise ValueError(
            "unsupported Codex HTTP exporter layout; left unchanged"
        ) from exc
    return new_content


def _edit_otel_config(content: str, parsed: dict, exporter: dict, http: dict) -> str:
    if "otel" not in parsed:
        return content.rstrip() + (
            '\n\n[otel]\nenvironment = "dev"\nexporter = '
            + _inline_toml({"otlp-http": http})
            + "\n"
        )
    if re.search(r"(?m)^\[otel\.exporter\.otlp-http\]", content):
        return _write_http_keys(content, http)
    section = re.search(
        r"(?ms)^\[otel\][^\S\n]*(?:#[^\n]*)?(?:\n|\Z)(.*?)(?=^\[|\Z)",
        content,
    )
    if section and re.search(r"(?m)^\s*exporter\s*=", section.group(1)):
        return _write_http_keys(content, http)
    if not exporter and section:
        body = (
            section.group(1).rstrip()
            + "\nexporter = "
            + _inline_toml({"otlp-http": http})
            + "\n"
        )
        return content[: section.start(1)] + body + content[section.end(1) :]
    return (
        content.rstrip()
        + "\n\n[otel.exporter.otlp-http]\n"
        + "".join(f"{key} = {_inline_toml(value)}\n" for key, value in http.items())
    )


def _inline_toml(value) -> str:
    """Render the inline exporter values while preserving unrelated options."""
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(
                f"{key if key in ('otlp-http', 'endpoint', 'protocol', 'headers') else json.dumps(key)} = {_inline_toml(item)}"
                for key, item in value.items()
            )
            + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(_inline_toml(item) for item in value) + "]"
    if isinstance(value, (str, bool, int, float)):
        return json.dumps(value)
    return value.isoformat()


def _write_http_keys(content: str, http: dict) -> str:
    """Edit only the HTTP exporter in the two shapes emitted by this script."""
    # The parsed headers are rendered inline below. Remove their old table so
    # TOML does not declare the same headers twice.
    content = re.sub(
        r"(?ms)^\[otel\.exporter\.otlp-http\.headers(?:\.[^\]]+)?\]"
        r"[^\S\n]*(?:#[^\n]*)?(?:\n|\Z).*?(?=^\[|\Z)",
        "",
        content,
    )
    section = re.search(
        r"(?ms)(^\[otel\.exporter\.otlp-http\][^\S\n]*(?:#[^\n]*)?(?:\n|\Z))"
        r"(.*?)(?=^\[|\Z)",
        content,
    )
    if section:
        body = section.group(2)
        body = re.sub(r"(?m)^\s*(endpoint|protocol|headers)\s*=.*\n?", "", body)
        body = (
            body.rstrip()
            + "\n"
            + "".join(
                f"{key} = {_inline_toml(http[key])}\n"
                for key in ("endpoint", "protocol", "headers")
                if key in http
            )
        )
        return content[: section.start(2)] + body + content[section.end(2) :]
    section = re.search(
        r"(?ms)^\[otel\][^\S\n]*(?:#[^\n]*)?(?:\n|\Z)(.*?)(?=^\[|\Z)",
        content,
    )
    if section:
        body = section.group(1)
        exporter = tomllib.loads(content)["otel"].get("exporter")
        exporter = exporter if isinstance(exporter, dict) else {}
        exporter["otlp-http"] = http
        body = re.sub(
            r"(?m)^\s*exporter\s*=.*$",
            lambda _: "exporter = " + _inline_toml(exporter),
            body,
            count=1,
        )
        return content[: section.start(1)] + body + content[section.end(1) :]
    raise ValueError("unsupported Codex HTTP exporter layout; left unchanged")


def _remove_http_exporter(content: str, exporter) -> str:
    section = re.search(
        r"(?ms)^\[otel\][^\S\n]*(?:#[^\n]*)?(?:\n|\Z)(.*?)(?=^\[|\Z)",
        content,
    )
    if section and re.search(r"(?m)^\s*exporter\s*=", section.group(1)):
        body = re.sub(
            r"(?m)^\s*exporter\s*=.*$",
            lambda _: "exporter = " + _inline_toml(exporter),
            section.group(1),
            count=1,
        )
        return content[: section.start(1)] + body + content[section.end(1) :]
    # Remove only the HTTP exporter and its own header subtables.
    cleaned = re.sub(
        r"(?ms)^\[otel\.exporter\.otlp-http(?:\.[^\]]+)?\]"
        r"[^\S\n]*(?:#[^\n]*)?(?:\n|\Z).*?(?=^\[|\Z)",
        "",
        content,
    )
    if exporter == "none":
        cleaned = re.sub(
            r"(?ms)^\[otel\.exporter\][^\S\n]*(?:#[^\n]*)?(?:\n|\Z).*?(?=^\[|\Z)",
            "",
            cleaned,
        )
        section = re.search(
            r"(?ms)^\[otel\][^\S\n]*(?:#[^\n]*)?(?:\n|\Z)(.*?)(?=^\[|\Z)",
            cleaned,
        )
        if not section:
            return cleaned.rstrip() + '\n\n[otel]\nexporter = "none"\n'
        body = section.group(1).rstrip() + '\nexporter = "none"\n'
        cleaned = cleaned[: section.start(1)] + body + cleaned[section.end(1) :]
    return cleaned


def _disable(config_path: Path, expected_endpoint: str | None) -> int:
    if not expected_endpoint:
        print("collector unknown; Codex configuration left unchanged", file=sys.stderr)
        return 2
    if not config_path.exists():
        _info(f"No Codex config at {config_path}")
        return 2
    content = config_path.read_text(encoding="utf-8")
    try:
        parsed = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        print("invalid Codex TOML configuration; left unchanged", file=sys.stderr)
        return 1
    otel = parsed.get("otel")
    exporter = otel.get("exporter") if isinstance(otel, dict) else None
    http = exporter.get("otlp-http") if isinstance(exporter, dict) else None
    if not isinstance(http, dict) or not http.get("endpoint"):
        _info(f"No llm-tracker telemetry in {config_path}")
        return 2
    if expected_endpoint and http["endpoint"] != expected_endpoint:
        print(f"{config_path} points at another collector; left alone", file=sys.stderr)
        return 2
    desired = deepcopy(parsed)
    remaining = desired["otel"]["exporter"]
    remaining.pop("otlp-http")
    if not remaining:
        desired["otel"]["exporter"] = "none"
    try:
        new_content = _remove_http_exporter(content, desired["otel"]["exporter"])
        # Refuse a text edit that changes any unrelated TOML value.
        if tomllib.loads(new_content) != desired:
            raise ValueError("unsupported Codex HTTP exporter layout; left unchanged")
    except (ValueError, TypeError, AttributeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _write_private(config_path, new_content)
    _info(f"Codex OTLP telemetry removed from {config_path}")
    return 0


# Exit status contract: 0 configured/removed, 2 skipped, 1 failed.
def _main():
    argv = sys.argv[1:]
    # Compact client API; retain PORT/HOST positional inputs for direct callers.
    if len(argv) == 2 and "://" in argv[1]:
        argv = [argv[0], "", "", argv[1]]
    disable = False
    if "--disable" in argv:
        disable = True
        argv = [arg for arg in argv if arg != "--disable"]
    if len(argv) not in (1, 2, 3, 4, 5):
        print(
            "usage: configure-codex-settings.py CONFIG_PATH "
            "[--disable [ENDPOINT]] | ENDPOINT | [OTLP_PORT] [HOST] [ENDPOINT] [TOKEN]",
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
        print(
            f"WARNING: {config_path.parent} does not exist; skipping Codex configuration",
            file=sys.stderr,
        )
        return 2

    content = ""
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")

    endpoint = resolve_otlp_logs_endpoint(otlp_port, host, endpoint)

    try:
        new_content = update_existing_otel_config(content, endpoint, token)
    except (ValueError, TypeError, AttributeError):
        print("unsupported Codex HTTP exporter layout; left unchanged", file=sys.stderr)
        return 1
    if new_content != content:
        _write_private(config_path, new_content)
        _info(f"Codex OTLP telemetry updated in {config_path}")
    else:
        _info(f"Codex OTLP telemetry already up-to-date in {config_path}")

    return 0


def main():
    try:
        return _main()
    except (OSError, UnicodeError):
        print("cannot update Codex configuration; left unchanged", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
