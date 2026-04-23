from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    ForeignKey,
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
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from config.app import CONFIG

metadata = MetaData()

base_urls_table = Table(
    "base_urls",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("base_url", String, nullable=False, unique=True),
    Column("provider_name", String),
    Column("source", String),
)

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
    Column("base_url_id", Integer, ForeignKey("base_urls.id"), nullable=True),
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
    _ensure_base_urls_columns_removed(engine)
    _ensure_usage_columns(engine)


def _ensure_usage_columns(engine: Engine) -> None:
    if not _usage_table_exists(engine):
        return

    _ensure_usage_column(
        engine,
        "prompt_length",
        sqlite_definition="INTEGER NOT NULL DEFAULT 0",
        postgresql_definition="INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_usage_column(
        engine,
        "base_url_id",
        sqlite_definition="INTEGER REFERENCES base_urls(id)",
        postgresql_definition="INTEGER REFERENCES base_urls(id)",
    )


def _ensure_usage_column(
    engine: Engine,
    column_name: str,
    *,
    sqlite_definition: str,
    postgresql_definition: str,
) -> None:
    if column_name in _usage_column_names(engine):
        return

    definition = (
        postgresql_definition
        if engine.dialect.name == "postgresql"
        else sqlite_definition
    )

    with engine.begin() as connection:
        try:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        f"ALTER TABLE usage ADD COLUMN IF NOT EXISTS {column_name} {definition}"
                    )
                )
            else:
                connection.execute(
                    text(f"ALTER TABLE usage ADD COLUMN {column_name} {definition}")
                )
        except SQLAlchemyError:
            # Another process may have added the column after our initial schema check.
            if column_name not in _usage_column_names(engine):
                raise


def _usage_table_exists(engine: Engine) -> bool:
    return "usage" in inspect(engine).get_table_names()


def _base_urls_table_exists(engine: Engine) -> bool:
    return "base_urls" in inspect(engine).get_table_names()


def _usage_column_names(engine: Engine) -> set[str]:
    return _table_column_names(engine, "usage")


def _base_url_column_names(engine: Engine) -> set[str]:
    return _table_column_names(engine, "base_urls")


def _table_column_names(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _ensure_base_urls_columns_removed(engine: Engine) -> None:
    if not _base_urls_table_exists(engine):
        return

    _drop_table_column(engine, "base_urls", "validation_status")
    _drop_table_column(engine, "base_urls", "last_error")


def _drop_table_column(engine: Engine, table_name: str, column_name: str) -> None:
    if column_name not in _table_column_names(engine, table_name):
        return

    with engine.begin() as connection:
        try:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column_name}"
                    )
                )
            else:
                connection.execute(
                    text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
                )
        except SQLAlchemyError:
            if column_name in _table_column_names(engine, table_name):
                raise


def _base_url_row(base_url: str, connection: Any) -> Any:
    return connection.execute(
        select(base_urls_table).where(base_urls_table.c.base_url == base_url)
    ).first()


def _base_url_updates(
    row: Any,
    *,
    provider_name: str | None,
    source: str | None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if provider_name and (not row.provider_name or row.provider_name == "unknown"):
        updates["provider_name"] = provider_name
    if source and not row.source:
        updates["source"] = source
    return updates


def get_or_create_base_url(
    base_url: str,
    *,
    db_path: str | None = None,
    provider_name: str | None = None,
    source: str | None = None,
) -> int:
    engine = get_engine(db_path)

    for attempt in range(2):
        with engine.begin() as connection:
            row = _base_url_row(base_url, connection)
            if row is not None:
                updates = _base_url_updates(
                    row,
                    provider_name=provider_name,
                    source=source,
                )
                if updates:
                    connection.execute(
                        update(base_urls_table)
                        .where(base_urls_table.c.id == row.id)
                        .values(**updates)
                    )
                return int(row.id)

            values = {
                "base_url": base_url,
                "provider_name": provider_name,
                "source": source,
            }

            try:
                result = connection.execute(insert(base_urls_table), [values])
                inserted_id = result.inserted_primary_key[0]
                return int(inserted_id)
            except IntegrityError:
                # On PostgreSQL, the transaction is aborted after an IntegrityError.
                # Retry in a fresh transaction so we can observe the winning row.
                if attempt == 0:
                    continue
                raise

    raise RuntimeError(f"Failed to resolve base_url id for {base_url}")


def resolve_base_url_id(
    *,
    base_url: str | None,
    db_path: str | None = None,
    provider_name: str | None = None,
    source: str | None = None,
) -> int | None:
    if not base_url:
        return None

    return get_or_create_base_url(
        base_url,
        db_path=db_path,
        provider_name=provider_name,
        source=source,
    )


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
        select(*usage_table.c, base_urls_table.c.base_url.label("base_url"))
        .select_from(
            usage_table.outerjoin(
                base_urls_table, usage_table.c.base_url_id == base_urls_table.c.id
            )
        )
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
