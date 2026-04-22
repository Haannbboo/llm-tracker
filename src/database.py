from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    and_,
    create_engine,
    func,
    inspect,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config.app import CONFIG

metadata = MetaData()

usage_table = Table(
    "usage",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String, nullable=False),
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False),
    Column("endpoint", String, nullable=False),
    Column("prompt_tokens", Integer),
    Column("prompt_length", Integer, nullable=False, server_default=text("0")),
    Column("completion_tokens", Integer),
    Column("reasoning_tokens", Integer),
    Column("cached_tokens", Integer),
    Column("total_tokens", Integer),
    Column("latency_ms", Integer),
    Column("ttft_ms", Integer),
    Column("tool_tokens", Integer),
    Column("cache_creation_tokens", Integer),
    Column("status", Integer),
)

_engine_cache: dict[str, Engine] = {}


def get_db_url(db_path: str | None = None) -> str:
    if db_path and "://" in db_path:
        return db_path
    if db_path:
        return f"sqlite:///{db_path}"
    return str(CONFIG["db"]["url"])


def _connect_args(db_url: str) -> dict[str, Any]:
    if db_url.startswith("sqlite:///"):
        return {"check_same_thread": False}
    return {}


def get_engine(db_path: str | None = None) -> Engine:
    db_url = get_db_url(db_path)
    if db_url not in _engine_cache:
        if db_url.startswith("sqlite:///"):
            sqlite_path = db_url[10:]
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        _engine_cache[db_url] = create_engine(
            db_url,
            future=True,
            pool_pre_ping=True,
            connect_args=_connect_args(db_url),
        )
    return _engine_cache[db_url]


def init_db(db_path: str | None = None) -> None:
    engine = get_engine(db_path)
    metadata.create_all(engine)
    _ensure_usage_columns(engine)


def _ensure_usage_columns(engine: Engine) -> None:
    if not _usage_table_exists(engine):
        return

    existing_columns = _usage_column_names(engine)
    if "prompt_length" in existing_columns:
        return

    with engine.begin() as connection:
        try:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "ALTER TABLE usage ADD COLUMN IF NOT EXISTS prompt_length INTEGER NOT NULL DEFAULT 0"
                    )
                )
            else:
                connection.execute(
                    text(
                        "ALTER TABLE usage ADD COLUMN prompt_length INTEGER NOT NULL DEFAULT 0"
                    )
                )
        except SQLAlchemyError:
            # Another process may have added the column after our initial schema check.
            if "prompt_length" not in _usage_column_names(engine):
                raise


def _usage_table_exists(engine: Engine) -> bool:
    return "usage" in inspect(engine).get_table_names()


def _usage_column_names(engine: Engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("usage")}


def log_usage(db_path: str | None = None, **fields: Any) -> None:
    with get_engine(db_path).begin() as connection:
        connection.execute(insert(usage_table), [fields])


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def _usage_filters(
    *,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[Any]:
    filters: list[Any] = []
    if provider:
        filters.append(usage_table.c.provider == provider)
    if model:
        filters.append(usage_table.c.model == model)
    if since:
        filters.append(usage_table.c.ts >= since)
    if until:
        filters.append(usage_table.c.ts <= until)
    return filters


def fetch_recent_usage(
    *,
    limit: int,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    filters = _usage_filters(
        provider=provider,
        model=model,
        since=since,
        until=until,
    )
    query = (
        select(usage_table)
        .order_by(usage_table.c.ts.desc())
        .limit(limit)
        .offset(offset)
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine().connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def count_usage(
    *,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> int:
    filters = _usage_filters(
        provider=provider,
        model=model,
        since=since,
        until=until,
    )
    query = select(func.count()).select_from(usage_table)
    if filters:
        query = query.where(and_(*filters))
    with get_engine().connect() as connection:
        return int(connection.execute(query).scalar_one())


def summarize_usage(
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    filters = _usage_filters(since=since, until=until)
    query = (
        select(
            usage_table.c.provider,
            usage_table.c.model,
            func.count().label("requests"),
            func.sum(usage_table.c.prompt_tokens).label("prompt_tokens"),
            func.sum(usage_table.c.completion_tokens).label("completion_tokens"),
            func.sum(usage_table.c.reasoning_tokens).label("reasoning_tokens"),
            func.sum(usage_table.c.cached_tokens).label("cached_tokens"),
            func.sum(usage_table.c.total_tokens).label("total_tokens"),
            func.avg(usage_table.c.latency_ms).label("avg_latency_ms"),
        )
        .group_by(usage_table.c.provider, usage_table.c.model)
        .order_by(func.sum(usage_table.c.total_tokens).desc())
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine().connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def _parse_iso8601(ts: str) -> datetime:
    normalized = ts.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def aggregate_usage_by_period(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    granularity: str = "day",
    tz_offset: str = "+00:00",
) -> list[dict[str, Any]]:
    filters = _usage_filters(
        provider=provider,
        model=model,
        since=since,
        until=until,
    )
    query = select(
        usage_table.c.ts,
        usage_table.c.prompt_tokens,
        usage_table.c.completion_tokens,
        usage_table.c.cached_tokens,
        usage_table.c.total_tokens,
    ).order_by(usage_table.c.ts.asc())
    if filters:
        query = query.where(and_(*filters))

    sign = 1 if tz_offset.startswith("+") else -1
    hours_str, minutes_str = tz_offset[1:].split(":", 1)
    offset_delta = timedelta(
        hours=sign * int(hours_str),
        minutes=sign * int(minutes_str),
    )

    buckets: dict[str, dict[str, Any]] = {}
    with get_engine().connect() as connection:
        for row in connection.execute(query):
            ts = _parse_iso8601(row.ts) + offset_delta
            period = ts.strftime(
                "%Y-%m-%d %H:00" if granularity == "hour" else "%Y-%m-%d"
            )
            bucket = buckets.setdefault(
                period,
                {
                    "period": period,
                    "requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "total_tokens": 0,
                },
            )
            bucket["requests"] += 1
            bucket["prompt_tokens"] += row.prompt_tokens or 0
            bucket["completion_tokens"] += row.completion_tokens or 0
            bucket["cached_tokens"] += row.cached_tokens or 0
            bucket["total_tokens"] += row.total_tokens or 0

    return [buckets[key] for key in sorted(buckets)]
