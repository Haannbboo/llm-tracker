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
                    return content.replace(exporter_match.group(1), new_exporter_val)

        # If [otel] exists but no exporter found so far, check if we have any other [otel.exporter...] sections
        if not re.search(r"^\[otel\.exporter", content, re.M):
            # No existing exporter anywhere, add it safely inside the [otel] block
            new_otel_block = (
                otel_match.group(0).rstrip()
                + f'\nexporter = {{ otlp-http = {{ endpoint = "{endpoint}", protocol = "json" }} }}\n'
            )
            return content.replace(otel_match.group(0), new_otel_block)

    # 3. Nothing found, append new section
    return (
        content.rstrip()
        + f'\n\n[otel]\nenvironment = "dev"\nexporter = {{ otlp-http = {{ endpoint = "{endpoint}", protocol = "json" }} }}\n'
    )


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

    new_content = update_existing_otel_config(content, endpoint)
    if new_content != content:
        config_path.write_text(new_content, encoding="utf-8")
        print(f"==> Codex OTLP telemetry updated to {endpoint} in {config_path}")
    else:
        print(f"==> Codex OTLP telemetry already up-to-date in {config_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
