#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path


def resolve_otlp_logs_endpoint(otlp_port: str) -> str:
    """Return explicit OTLP logs endpoint override or localhost port default."""
    env_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    if env_endpoint:
        return env_endpoint
    return f"http://localhost:{otlp_port}/v1/logs"


def update_existing_otel_config(content: str, endpoint: str) -> str:
    """Update Codex OTLP endpoint in inline or nested TOML config shapes."""
    inline_content = re.sub(
        r"(exporter\s*=\s*\{\s*otlp-http\s*=\s*\{\s*)[^\}]+(\}\s*\})",
        rf'\g<1>endpoint = "{endpoint}", protocol = "json" \g<2>',
        content,
    )
    if inline_content != content:
        return inline_content

    section = re.search(
        r"(?ms)(^\[otel\.exporter\.otlp-http\]\s*)(.*?)(?=^\[|\Z)",
        content,
    )
    if section is None:
        return (
            content.rstrip()
            + f'\n\n[otel.exporter.otlp-http]\nendpoint = "{endpoint}"\nprotocol = "json"\n'
        )

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
    return content[: section.start(2)] + updated_body + content[section.end(2) :]


def main():
    if len(sys.argv) not in (2, 3):
        print(
            "usage: configure-codex-settings.py CONFIG_PATH [OTLP_PORT]",
            file=sys.stderr,
        )
        return 1

    config_path = Path(sys.argv[1]).expanduser()
    otlp_port = sys.argv[2] if len(sys.argv) == 3 else "4002"

    if not config_path.parent.exists():
        return 0

    content = ""
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")

    endpoint = resolve_otlp_logs_endpoint(otlp_port)

    if "[otel]" not in content:
        new_section = f'\n[otel]\nenvironment = "dev"\nexporter = {{ otlp-http = {{ endpoint = "{endpoint}", protocol = "json" }} }}\n'
        with open(config_path, "a", encoding="utf-8") as f:
            f.write(new_section)
        print(f"==> Codex OTLP telemetry configured in {config_path}")
    else:
        new_content = update_existing_otel_config(content, endpoint)
        if new_content != content:
            config_path.write_text(new_content, encoding="utf-8")
            print(
                f"==> Codex OTLP telemetry endpoint updated to {endpoint} in {config_path}"
            )
        else:
            print(f"==> Codex OTLP telemetry already up-to-date in {config_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
