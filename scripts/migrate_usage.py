#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.app import CONFIG  # noqa: E402
from src.database import (  # noqa: E402
    _row_to_dict,
    base_urls_table,
    get_or_create_base_url,
    get_engine,
    init_db,
    usage_table,
)
from sqlalchemy import func, insert, select  # noqa: E402


def count_rows(db_url: str, table=usage_table) -> int:
    engine = get_engine(db_url)
    with engine.connect() as connection:
        return int(
            connection.execute(select(func.count()).select_from(table)).scalar_one()
        )


def fetch_source_rows(db_url: str, batch_size: int, table):
    engine = get_engine(db_url)
    last_id = 0

    while True:
        query = (
            select(table)
            .where(table.c.id > last_id)
            .order_by(table.c.id.asc())
            .limit(batch_size)
        )
        with engine.connect() as connection:
            rows = [_row_to_dict(row) for row in connection.execute(query)]

        if not rows:
            break

        yield rows
        last_id = rows[-1]["id"]


def existing_target_ids(target_url: str, table) -> set[int]:
    engine = get_engine(target_url)
    with engine.connect() as connection:
        rows = connection.execute(select(table.c.id))
        return {int(row.id) for row in rows}


def build_base_url_id_map(
    source_url: str,
    target_url: str,
    batch_size: int,
) -> dict[int, int]:
    base_url_id_map: dict[int, int] = {}

    for rows in fetch_source_rows(source_url, batch_size, base_urls_table):
        for row in rows:
            target_id = get_or_create_base_url(
                row["base_url"],
                db_path=target_url,
                provider_name=row.get("provider_name"),
                source=row.get("source"),
            )
            base_url_id_map[int(row["id"])] = target_id

    return base_url_id_map


def remap_usage_base_url_ids(
    rows: list[dict[str, object]], base_url_id_map: dict[int, int]
) -> list[dict[str, object]]:
    remapped_rows: list[dict[str, object]] = []

    for row in rows:
        remapped = dict(row)
        source_base_url_id = remapped.get("base_url_id")
        if source_base_url_id is not None:
            target_base_url_id = base_url_id_map.get(int(source_base_url_id))
            if target_base_url_id is None:
                raise KeyError(
                    f"Missing base_url mapping for source id {source_base_url_id}"
                )
            remapped["base_url_id"] = target_base_url_id
        remapped_rows.append(remapped)

    return remapped_rows


def copy_rows_for_table(
    table,
    source_url: str,
    target_url: str,
    batch_size: int,
    *,
    skip_existing: bool,
    base_url_id_map: dict[int, int] | None = None,
) -> tuple[int, int]:
    target_engine = get_engine(target_url)
    migrated = 0
    skipped = 0
    target_ids = existing_target_ids(target_url, table) if skip_existing else set()

    for rows in fetch_source_rows(source_url, batch_size, table):
        if skip_existing:
            filtered_rows = [row for row in rows if row["id"] not in target_ids]
            skipped += len(rows) - len(filtered_rows)
            rows = filtered_rows

        if not rows:
            continue

        if table is usage_table and base_url_id_map is not None:
            rows = remap_usage_base_url_ids(rows, base_url_id_map)

        with target_engine.begin() as connection:
            connection.execute(insert(table), rows)
        migrated += len(rows)

    return migrated, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy llm-tracker usage rows from a source database into an empty target database."
    )
    parser.add_argument(
        "--source-url",
        default=f"sqlite:///{Path(CONFIG['db'].get('path', '~/.llm-tracker/usage.db')).expanduser()}",
        help="Source SQLAlchemy URL. Defaults to the local SQLite usage DB path.",
    )
    parser.add_argument(
        "--target-url",
        default=CONFIG["db"]["url"],
        help="Target SQLAlchemy URL. Defaults to db.url from ~/.llm-tracker/config.yaml.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of rows to copy per batch.",
    )
    parser.add_argument(
        "--allow-nonempty-target",
        action="store_true",
        help="Allow migration into a target that already has rows.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="When the target is non-empty, skip source rows whose ids already exist in the target.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    init_db(args.source_url)
    init_db(args.target_url)

    source_count = count_rows(args.source_url)
    target_count = count_rows(args.target_url)

    if source_count == 0:
        print("Source usage table is empty; nothing to migrate.")
        return 0

    if target_count > 0 and not args.allow_nonempty_target:
        print(
            f"Refusing to migrate into non-empty target: target has {target_count} rows. "
            "Use --allow-nonempty-target to override.",
            file=sys.stderr,
        )
        return 1

    if target_count > 0 and not args.skip_existing:
        print(
            "Target is non-empty. Re-run with --skip-existing to ignore already-present ids.",
            file=sys.stderr,
        )
        return 1

    base_url_id_map = build_base_url_id_map(
        args.source_url,
        args.target_url,
        args.batch_size,
    )
    migrated, skipped = copy_rows_for_table(
        usage_table,
        args.source_url,
        args.target_url,
        args.batch_size,
        skip_existing=args.skip_existing,
        base_url_id_map=base_url_id_map,
    )
    print(f"Migrated {migrated} rows from {args.source_url} to {args.target_url}.")
    if skipped:
        print(f"Skipped {skipped} rows already present in the target.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
