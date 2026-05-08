#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.app import CONFIG  # noqa: E402
from src.schema_migrations import migrate_database  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply explicit llm-tracker schema migrations."
    )
    parser.add_argument(
        "--db-url",
        default=CONFIG["db"]["url"],
        help="Target SQLAlchemy URL. Defaults to db.url from ~/.llm-tracker/config.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changes = migrate_database(args.db_url)

    if changes:
        print(f"Applied schema migrations: {', '.join(changes)}")
    else:
        print("Schema is up to date (configured database).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
