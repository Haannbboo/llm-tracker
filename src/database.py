"""Database models and query helpers for llm-tracker.

The steady-state pattern in this module is:
- ORM models for entity lifecycle operations such as inserts and base URL resolution
- `select(...)`-style projection queries for usage reporting and aggregation
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import (
    ForeignKey,
    Integer,
    Numeric,
    String,
    and_,
    case,
    create_engine,
    func,
    or_,
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
    client_source: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
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
    input_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0, server_default=text("0")
    )
    output_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0, server_default=text("0")
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_url_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("base_urls.id"), nullable=True
    )
    base_url: Mapped[BaseUrl | None] = relationship(back_populates="usages")


DB_URL_ENV_VAR = "LLM_TRACKER_DB_URL"

_engine_cache: dict[str, Engine] = {}


def get_db_url(db_path: str | None = None) -> str:
    """Resolve an explicit DB target, env override, or configured default."""
    if db_path and "://" in db_path:
        return db_path
    if db_path:
        return f"sqlite:///{db_path}"

    env_url = os.environ.get(DB_URL_ENV_VAR)
    if env_url:
        return env_url

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


USAGE_COPY_FIELDS = (
    "ts",
    "provider",
    "model",
    "client_source",
    "session_id",
    "endpoint",
    "prompt_tokens",
    "prompt_length",
    "completion_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "total_tokens",
    "latency_ms",
    "ttft_ms",
    "tool_tokens",
    "cache_creation_tokens",
    "input_cost_usd",
    "output_cost_usd",
    "total_cost_usd",
    "status",
)


def _usage_copy_kwargs(row: Usage) -> dict[str, Any]:
    return {field: getattr(row, field) for field in USAGE_COPY_FIELDS}


def merge_usage_database(
    *,
    source_db_path: str,
    target_db_path: str | None = None,
) -> int:
    """Copy usage rows from an isolated run DB into the configured/main DB."""
    source_engine = get_engine(source_db_path)
    target_engine = get_engine(target_db_path)
    inserted = 0

    with Session(source_engine) as source:
        rows = source.execute(
            select(Usage, BaseUrl)
            .outerjoin(BaseUrl, Usage.base_url_id == BaseUrl.id)
            .order_by(Usage.id.asc())
        ).all()

    with Session(target_engine) as target:
        for row, base_url in rows:
            base_url_id = None
            if base_url is not None:
                base_url_id = get_or_create_base_url(
                    base_url.base_url,
                    db_path=target_db_path,
                    provider_name=base_url.provider_name,
                    source=base_url.source,
                )
            target.add(
                Usage(
                    **_usage_copy_kwargs(row),
                    base_url_id=base_url_id,
                )
            )
            inserted += 1
        target.commit()

    return inserted


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {key: _normalize_value(value) for key, value in row._mapping.items()}


# === Reporting / Query Helpers ===
# Return projected rows and aggregates for API consumers.


SUMMARY_SUM_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "tool_tokens",
    "cache_creation_tokens",
    "total_tokens",
    "input_cost_usd",
    "output_cost_usd",
    "total_cost_usd",
)


def _empty_usage_summary() -> dict[str, Any]:
    return {
        "requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "tool_tokens": 0,
        "cache_creation_tokens": 0,
        "total_tokens": 0,
        "input_cost_usd": 0.0,
        "output_cost_usd": 0.0,
        "total_cost_usd": 0.0,
        "avg_latency_ms": None,
        "avg_ttft_ms": None,
        "cache_hit_rate": 0.0,
    }


def _add_row_to_summary(summary: dict[str, Any], row: dict[str, Any]) -> None:
    summary["requests"] += 1
    status = row.get("status")
    if status is not None and status >= 400:
        summary["failed_requests"] += 1
    else:
        summary["successful_requests"] += 1

    for field in SUMMARY_SUM_FIELDS:
        summary[field] += row.get(field) or 0


def _finalize_usage_summary(
    summary: dict[str, Any],
    *,
    latency_values: list[int],
    ttft_values: list[int],
) -> dict[str, Any]:
    if latency_values:
        summary["avg_latency_ms"] = sum(latency_values) / len(latency_values)
    if ttft_values:
        summary["avg_ttft_ms"] = sum(ttft_values) / len(ttft_values)

    prompt_tokens = summary["prompt_tokens"]
    summary["cache_hit_rate"] = (
        summary["cached_tokens"] / prompt_tokens if prompt_tokens else 0.0
    )

    return summary


def _usage_filters(
    *,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[Any]:
    filters: list[Any] = []
    if provider:
        filters.append(Usage.provider == provider)
    if model:
        filters.append(Usage.model == model)
    if client_source:
        filters.append(Usage.client_source == client_source)
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
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent usage rows plus the resolved base URL when available."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        client_source=client_source,
        since=since,
        until=until,
    )
    query = (
        select(
            Usage.id,
            Usage.ts,
            Usage.provider,
            Usage.model,
            Usage.client_source,
            Usage.session_id,
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
            Usage.input_cost_usd,
            Usage.output_cost_usd,
            Usage.total_cost_usd,
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
    with get_engine(db_path).connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def distinct_client_sources(
    *,
    since: str | None = None,
    until: str | None = None,
    db_path: str | None = None,
) -> list[str]:
    """Return distinct client_source values in the given time window."""
    filters = _usage_filters(since=since, until=until)
    filters.append(Usage.client_source.isnot(None))
    query = (
        select(Usage.client_source)
        .distinct()
        .where(and_(*filters))
        .order_by(Usage.client_source)
    )
    with get_engine(db_path).connect() as connection:
        return [row[0] for row in connection.execute(query)]


def count_usage(
    *,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> int:
    """Count usage rows matching the optional provider/model/time filters."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        client_source=client_source,
        since=since,
        until=until,
    )
    query = select(func.count()).select_from(Usage)
    if filters:
        query = query.where(and_(*filters))
    with get_engine().connect() as connection:
        return int(connection.execute(query).scalar_one())


def get_usage_high_watermark(*, db_path: str | None = None) -> int:
    query = select(func.max(Usage.id))
    with get_engine(db_path).connect() as connection:
        value = connection.execute(query).scalar_one()
    return int(value or 0)


def summarize_usage_window(
    *,
    after_id: int = 0,
    until_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    client_source: str | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    include_rows: bool = False,
    db_path: str | None = None,
) -> dict[str, Any]:
    filters = [Usage.id > after_id]
    if until_id is not None:
        filters.append(Usage.id <= until_id)
    if since:
        filters.append(Usage.ts >= since)
    if until:
        filters.append(Usage.ts <= until)
    if client_source:
        filters.append(Usage.client_source == client_source)
    if session_id:
        filters.append(Usage.session_id == session_id)
    if provider:
        filters.append(Usage.provider == provider)
    if model:
        filters.append(Usage.model == model)

    query = (
        select(
            Usage.id,
            Usage.ts,
            Usage.provider,
            Usage.model,
            Usage.client_source,
            Usage.session_id,
            Usage.endpoint,
            Usage.prompt_tokens,
            Usage.completion_tokens,
            Usage.reasoning_tokens,
            Usage.cached_tokens,
            Usage.tool_tokens,
            Usage.cache_creation_tokens,
            Usage.total_tokens,
            Usage.latency_ms,
            Usage.ttft_ms,
            Usage.input_cost_usd,
            Usage.output_cost_usd,
            Usage.total_cost_usd,
            Usage.status,
        )
        .where(and_(*filters))
        .order_by(Usage.id.asc())
    )

    with get_engine(db_path).connect() as connection:
        rows = [_row_to_dict(row) for row in connection.execute(query)]

    return _build_usage_window_summary(
        rows,
        after_id=after_id,
        until_id=until_id,
        include_rows=include_rows,
    )


def _build_usage_window_summary(
    rows: list[dict[str, Any]],
    *,
    after_id: int,
    until_id: int | None,
    include_rows: bool,
) -> dict[str, Any]:
    overall = _empty_usage_summary()
    overall_latencies: list[int] = []
    overall_ttfts: list[int] = []
    grouped: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {
        "sessions": {},
        "client_sources": {},
        "models": {},
    }
    group_latencies: dict[tuple[str, tuple[Any, ...]], list[int]] = {}
    group_ttfts: dict[tuple[str, tuple[Any, ...]], list[int]] = {}

    def ensure_group(
        group_name: str,
        key: tuple[Any, ...],
        labels: dict[str, Any],
    ) -> dict[str, Any]:
        groups = grouped[group_name]
        if key not in groups:
            groups[key] = labels | _empty_usage_summary()
            group_latencies[(group_name, key)] = []
            group_ttfts[(group_name, key)] = []
        return groups[key]

    for row in rows:
        _add_row_to_summary(overall, row)
        if row.get("latency_ms") is not None:
            overall_latencies.append(int(row["latency_ms"]))
        if row.get("ttft_ms") is not None:
            overall_ttfts.append(int(row["ttft_ms"]))

        group_specs = [
            (
                "sessions",
                (row.get("session_id"),),
                {"session_id": row.get("session_id")},
            ),
            (
                "client_sources",
                (row.get("client_source"),),
                {"client_source": row.get("client_source")},
            ),
            (
                "models",
                (row.get("provider"), row.get("model")),
                {"provider": row.get("provider"), "model": row.get("model")},
            ),
        ]
        for group_name, key, labels in group_specs:
            group = ensure_group(group_name, key, labels)
            _add_row_to_summary(group, row)
            if row.get("latency_ms") is not None:
                group_latencies[(group_name, key)].append(int(row["latency_ms"]))
            if row.get("ttft_ms") is not None:
                group_ttfts[(group_name, key)].append(int(row["ttft_ms"]))

    _finalize_usage_summary(
        overall,
        latency_values=overall_latencies,
        ttft_values=overall_ttfts,
    )
    window_until_id = until_id
    if window_until_id is None:
        window_until_id = rows[-1]["id"] if rows else after_id

    result: dict[str, Any] = {
        "window": {
            "after_id": after_id,
            "until_id": window_until_id,
            "row_count": len(rows),
        },
        "summary": overall,
        "sessions": [],
        "client_sources": [],
        "models": [],
    }

    for group_name in ("sessions", "client_sources", "models"):
        values = []
        for key, summary in grouped[group_name].items():
            values.append(
                _finalize_usage_summary(
                    summary,
                    latency_values=group_latencies[(group_name, key)],
                    ttft_values=group_ttfts[(group_name, key)],
                )
            )
        result[group_name] = sorted(
            values,
            key=lambda item: (
                str(
                    item.get("session_id")
                    or item.get("client_source")
                    or item.get("provider")
                    or ""
                ),
                str(item.get("model") or ""),
            ),
        )

    if include_rows:
        result["rows"] = rows

    return result


def summarize_usage(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate usage totals by provider and model for dashboard summaries."""
    filters = _usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )
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
            func.sum(Usage.input_cost_usd).label("input_cost_usd"),
            func.sum(Usage.output_cost_usd).label("output_cost_usd"),
            func.sum(Usage.total_cost_usd).label("total_cost_usd"),
            func.sum(
                case(
                    (or_(Usage.status.is_(None), Usage.status < 400), 1),
                    else_=0,
                )
            ).label("successful_requests"),
            func.sum(
                case(
                    (Usage.status >= 400, 1),
                    else_=0,
                )
            ).label("failed_requests"),
        )
        .group_by(Usage.provider, Usage.model)
        .order_by(func.sum(Usage.total_tokens).desc())
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine().connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def summarize_usage_by_source(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate usage totals by client_source for dashboard source chart."""
    filters = _usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )
    query = (
        select(
            Usage.client_source,
            func.count().label("requests"),
            func.sum(Usage.prompt_tokens).label("prompt_tokens"),
            func.sum(Usage.completion_tokens).label("completion_tokens"),
            func.sum(Usage.reasoning_tokens).label("reasoning_tokens"),
            func.sum(Usage.cached_tokens).label("cached_tokens"),
            func.sum(Usage.total_tokens).label("total_tokens"),
            func.avg(Usage.latency_ms).label("avg_latency_ms"),
            func.sum(Usage.input_cost_usd).label("input_cost_usd"),
            func.sum(Usage.output_cost_usd).label("output_cost_usd"),
            func.sum(Usage.total_cost_usd).label("total_cost_usd"),
            func.sum(
                case(
                    (or_(Usage.status.is_(None), Usage.status < 400), 1),
                    else_=0,
                )
            ).label("successful_requests"),
            func.sum(
                case(
                    (Usage.status >= 400, 1),
                    else_=0,
                )
            ).label("failed_requests"),
        )
        .group_by(Usage.client_source)
        .order_by(func.sum(Usage.total_tokens).desc())
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine().connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def summarize_usage_by_provider(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate usage totals by provider for dashboard provider chart."""
    filters = _usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )
    query = (
        select(
            Usage.provider,
            func.count().label("requests"),
            func.sum(Usage.prompt_tokens).label("prompt_tokens"),
            func.sum(Usage.completion_tokens).label("completion_tokens"),
            func.sum(Usage.reasoning_tokens).label("reasoning_tokens"),
            func.sum(Usage.cached_tokens).label("cached_tokens"),
            func.sum(Usage.total_tokens).label("total_tokens"),
            func.avg(Usage.latency_ms).label("avg_latency_ms"),
            func.sum(Usage.input_cost_usd).label("input_cost_usd"),
            func.sum(Usage.output_cost_usd).label("output_cost_usd"),
            func.sum(Usage.total_cost_usd).label("total_cost_usd"),
            func.sum(
                case(
                    (or_(Usage.status.is_(None), Usage.status < 400), 1),
                    else_=0,
                )
            ).label("successful_requests"),
            func.sum(
                case(
                    (Usage.status >= 400, 1),
                    else_=0,
                )
            ).label("failed_requests"),
        )
        .group_by(Usage.provider)
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
    client_source: str | None = None,
    granularity: str = "day",
    tz_offset: str = "+00:00",
) -> list[dict[str, Any]]:
    """Bucket usage into local-time hourly or daily periods in Python."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        client_source=client_source,
        since=since,
        until=until,
    )
    query = select(
        Usage.ts,
        Usage.prompt_tokens,
        Usage.completion_tokens,
        Usage.cached_tokens,
        Usage.total_tokens,
        Usage.input_cost_usd,
        Usage.output_cost_usd,
        Usage.total_cost_usd,
        Usage.latency_ms,
        Usage.status,
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
                    "input_cost_usd": Decimal("0"),
                    "output_cost_usd": Decimal("0"),
                    "total_cost_usd": Decimal("0"),
                    "_latency_sum": 0,
                    "_latency_count": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                },
            )
            bucket["requests"] += 1
            bucket["prompt_tokens"] += row.prompt_tokens or 0
            bucket["completion_tokens"] += row.completion_tokens or 0
            bucket["cached_tokens"] += row.cached_tokens or 0
            bucket["total_tokens"] += row.total_tokens or 0
            bucket["input_cost_usd"] += row.input_cost_usd or Decimal("0")
            bucket["output_cost_usd"] += row.output_cost_usd or Decimal("0")
            bucket["total_cost_usd"] += row.total_cost_usd or Decimal("0")
            if row.latency_ms is not None:
                bucket["_latency_sum"] += row.latency_ms
                bucket["_latency_count"] += 1
            if row.status is not None and row.status >= 400:
                bucket["failed_requests"] += 1
            else:
                bucket["successful_requests"] += 1

    result = []
    for key in sorted(buckets):
        bucket = buckets[key]
        count = bucket.pop("_latency_count")
        latency_sum = bucket.pop("_latency_sum")
        bucket["avg_latency_ms"] = latency_sum / count if count > 0 else 0
        result.append(
            {_normalize_value(k): _normalize_value(v) for k, v in bucket.items()}
        )
    return result
