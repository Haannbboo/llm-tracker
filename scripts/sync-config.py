#!/usr/bin/env python3
"""Sync missing config defaults from config.example.yaml into a user config."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_GRAY = "\033[38;2;102;102;102m" if sys.stdout.isatty() else ""
_RESET = "\033[0m" if sys.stdout.isatty() else ""


def _info(msg: str) -> None:
    print(f"  {_GRAY}{msg}{_RESET}")


# Standalone script entrypoint: ensure project imports work without PYTHONPATH=.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    """Apply the missing-key config merge and print a short status message."""
    from config.merge import sync_config_file_with_defaults

    if len(sys.argv) != 3:
        print(
            "Usage: sync-config.py <config-path> <default-config-path>", file=sys.stderr
        )
        return 1

    config_path, default_config_path = sys.argv[1:3]
    changed = sync_config_file_with_defaults(config_path, default_config_path)
    if changed:
        _info(f"Updated config with missing defaults at {config_path}")
    else:
        _info(f"Config already includes current defaults at {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
