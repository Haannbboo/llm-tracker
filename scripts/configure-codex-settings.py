#!/usr/bin/env python3
import sys
from pathlib import Path


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

    endpoint = f"http://localhost:{otlp_port}/v1/logs"

    # Simple check and update logic for the [otel] section
    if "[otel]" not in content:
        # Append new section
        new_section = f'\n[otel]\nenvironment = "dev"\nexporter = {{ otlp-http = {{ endpoint = "{endpoint}", protocol = "json" }} }}\n'
        with open(config_path, "a", encoding="utf-8") as f:
            f.write(new_section)
        print(f"==> Codex OTLP telemetry configured in {config_path}")
    else:
        # Update existing endpoint port
        import re

        # Match the endpoint line specifically within or after [otel]
        new_content = re.sub(
            r'(endpoint\s*=\s*"http://localhost:)([0-9]+)(/v1/logs")',
            rf"\g<1>{otlp_port}\g<3>",
            content,
        )
        if new_content != content:
            config_path.write_text(new_content, encoding="utf-8")
            print(
                f"==> Codex OTLP telemetry port updated to {otlp_port} in {config_path}"
            )
        else:
            print(f"==> Codex OTLP telemetry already up-to-date in {config_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
