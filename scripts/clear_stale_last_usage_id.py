#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402
from config.app import CONFIG  # noqa: E402
from src.database import get_engine  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear stale sessions.last_usage_id values left by a previous "
        "UUID migration that changed the type but kept old integer IDs as text."
    )
    parser.add_argument(
        "--db-url",
        default=CONFIG["db"]["url"],
        help="Target SQLAlchemy URL. Defaults to db.url from ~/.llm-tracker/config.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = get_engine(args.db_url)

    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == "postgresql":
            result = connection.execute(
                text(
                    "UPDATE sessions "
                    "SET last_usage_id = NULL "
                    "WHERE last_usage_id IS NOT NULL "
                    "AND last_usage_id ~ '^\\d+$'"
                )
            )
        elif dialect == "sqlite":
            result = connection.execute(
                text(
                    "UPDATE sessions "
                    "SET last_usage_id = NULL "
                    "WHERE last_usage_id IS NOT NULL "
                    "AND last_usage_id NOT LIKE '%-%'"
                )
            )
        else:
            print(f"Unsupported dialect: {dialect}")
            return 1

        print(f"Cleared {result.rowcount} stale last_usage_id values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
