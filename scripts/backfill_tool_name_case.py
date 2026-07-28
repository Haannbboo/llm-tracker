#!/usr/bin/env python3
"""One-off backfill: lowercase tool_name so e.g. Bash/bash aggregate as one tool.

Fixes both `tool_calls.tool_name` and the denormalized `sessions.tool_calls_json`
counts, which mirror the same casing at write time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, select, update  # noqa: E402

from config.app import CONFIG  # noqa: E402
from src.database.engine import get_engine  # noqa: E402
from src.database.models import SessionRecord, ToolCall  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-url",
        default=CONFIG["db"]["url"],
        help="Target SQLAlchemy URL. Defaults to db.url from ~/.llm-tracker/config.yaml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    return parser.parse_args()


def backfill_tool_calls(connection, dry_run: bool) -> int:
    affected = connection.execute(
        select(func.count()).where(ToolCall.tool_name != func.lower(ToolCall.tool_name))
    ).scalar_one()
    if affected and not dry_run:
        connection.execute(
            update(ToolCall)
            .where(ToolCall.tool_name != func.lower(ToolCall.tool_name))
            .values(tool_name=func.lower(ToolCall.tool_name))
        )
    return affected


def backfill_session_tool_calls_json(connection, dry_run: bool) -> int:
    rows = connection.execute(
        select(SessionRecord.session_id, SessionRecord.tool_calls_json).where(
            SessionRecord.tool_calls_json.is_not(None)
        )
    ).all()

    changed = 0
    for session_id, raw in rows:
        tools = json.loads(raw or "{}")
        if not tools:
            continue
        merged: dict[str, int] = {}
        for name, count in tools.items():
            key = name.lower()
            merged[key] = merged.get(key, 0) + count
        if merged == tools:
            continue
        changed += 1
        if not dry_run:
            connection.execute(
                update(SessionRecord)
                .where(SessionRecord.session_id == session_id)
                .values(tool_calls_json=json.dumps(merged))
            )
    return changed


def main() -> int:
    args = parse_args()
    engine = get_engine(args.db_url)
    with engine.begin() as connection:
        tool_calls_changed = backfill_tool_calls(connection, args.dry_run)
        sessions_changed = backfill_session_tool_calls_json(connection, args.dry_run)

    verb = "Would update" if args.dry_run else "Updated"
    print(f"{verb} {tool_calls_changed} tool_calls row(s).")
    print(f"{verb} {sessions_changed} sessions.tool_calls_json row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
