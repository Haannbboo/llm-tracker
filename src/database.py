"""Database models and query helpers for llm-tracker.

The steady-state pattern in this module is:
- ORM models for entity lifecycle operations such as inserts and base URL resolution
- `select(...)`-style projection queries for usage reporting and aggregation
"""

from __future__ import annotations


from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    and_,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from config.app import CONFIG


class Base(DeclarativeBase):
    pass


metadata = Base.metadata


class BaseUrl(Base):
    __tablename__ = "base_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    provider_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    usages: Mapped[list["Usage"]] = relationship(back_populates="base_url")


class Usage(Base):
    __tablename__ = "usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_length: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_creation_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_url_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("base_urls.id"), nullable=True
    )
    base_url: Mapped[BaseUrl | None] = relationship(back_populates="usages")


_engine_cache: dict[str, Engine] = {}


def get_db_url(db_path: str | None = None) -> str:
    """Resolve an explicit DB override or fall back to the configured default."""
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
    """Return a cached engine for the requested database URL/path."""
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
    """Create ORM-managed tables if they do not already exist."""
    engine = get_engine(db_path)
    metadata.create_all(engine)


# === Entity / Persistence Helpers ===
# Operate on ORM objects and small entity workflows.


def _apply_base_url_updates(
    row: BaseUrl,
    *,
    provider_name: str | None,
    source: str | None,
) -> bool:
    updated = False
    if provider_name and (not row.provider_name or row.provider_name == "unknown"):
        row.provider_name = provider_name
        updated = True
    if source and not row.source:
        row.source = source
        updated = True
    return updated


def get_or_create_base_url(
    base_url: str,
    *,
    db_path: str | None = None,
    provider_name: str | None = None,
    source: str | None = None,
) -> int:
    """Resolve a stable `base_urls.id`, updating missing metadata when possible."""
    engine = get_engine(db_path)

    for attempt in range(2):
        with Session(engine) as session:
            row = session.scalar(select(BaseUrl).where(BaseUrl.base_url == base_url))
            if row is not None:
                if _apply_base_url_updates(
                    row,
                    provider_name=provider_name,
                    source=source,
                ):
                    session.commit()
                return int(row.id)

            row = BaseUrl(
                base_url=base_url,
                provider_name=provider_name,
                source=source,
            )
            session.add(row)
            try:
                session.commit()
                return int(row.id)
            except IntegrityError:
                # On PostgreSQL, the transaction is aborted after an IntegrityError.
                # Retry in a fresh transaction so we can observe the winning row.
                session.rollback()
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


def log_usage(usage: Usage, db_path: str | None = None) -> None:
    """Persist a single usage row to the configured or explicitly provided DB."""
    with Session(get_engine(db_path)) as session:
        session.add(usage)
        session.commit()


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


# === Reporting / Query Helpers ===
# Return projected rows and aggregates for API consumers.


def _usage_filters(
    *,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[Any]:
    filters: list[Any] = []
    if provider:
        filters.append(Usage.provider == provider)
    if model:
        filters.append(Usage.model == model)
    if since:
        filters.append(Usage.ts >= since)
    if until:
        filters.append(Usage.ts <= until)
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
    """Return recent usage rows plus the resolved base URL when available."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        since=since,
        until=until,
    )
    query = (
        select(
            Usage.id,
            Usage.ts,
            Usage.provider,
            Usage.model,
            Usage.endpoint,
            Usage.prompt_tokens,
            Usage.prompt_length,
            Usage.completion_tokens,
            Usage.reasoning_tokens,
            Usage.cached_tokens,
            Usage.total_tokens,
            Usage.latency_ms,
            Usage.ttft_ms,
            Usage.tool_tokens,
            Usage.cache_creation_tokens,
            Usage.status,
            Usage.base_url_id,
            BaseUrl.base_url.label("base_url"),
        )
        .select_from(Usage)
        .outerjoin(BaseUrl, Usage.base_url_id == BaseUrl.id)
        .order_by(Usage.ts.desc())
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
    """Count usage rows matching the optional provider/model/time filters."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        since=since,
        until=until,
    )
    query = select(func.count()).select_from(Usage)
    if filters:
        query = query.where(and_(*filters))
    with get_engine().connect() as connection:
        return int(connection.execute(query).scalar_one())


def summarize_usage(
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate usage totals by provider and model for dashboard summaries."""
    filters = _usage_filters(since=since, until=until)
    query = (
        select(
            Usage.provider,
            Usage.model,
            func.count().label("requests"),
            func.sum(Usage.prompt_tokens).label("prompt_tokens"),
            func.sum(Usage.completion_tokens).label("completion_tokens"),
            func.sum(Usage.reasoning_tokens).label("reasoning_tokens"),
            func.sum(Usage.cached_tokens).label("cached_tokens"),
            func.sum(Usage.total_tokens).label("total_tokens"),
            func.avg(Usage.latency_ms).label("avg_latency_ms"),
        )
        .group_by(Usage.provider, Usage.model)
        .order_by(func.sum(Usage.total_tokens).desc())
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
    """Bucket usage into local-time hourly or daily periods in Python."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        since=since,
        until=until,
    )
    query = select(
        Usage.ts,
        Usage.prompt_tokens,
        Usage.completion_tokens,
        Usage.cached_tokens,
        Usage.total_tokens,
    ).order_by(Usage.ts.asc())
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
