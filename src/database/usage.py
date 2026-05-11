"""Usage persistence, aggregation, and reporting helpers.

Extracted from database/__init__.py during Phase 5 refactoring.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    and_,
    case,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.orm import Session

from .models import BaseUrl, Usage, UsageDaily
from .engine import get_engine


# === Price helpers ===


def _avg_effective_price_expr(total_cost_col: Any, total_tokens_col: Any) -> Any:
    return case(
        (
            func.sum(total_tokens_col) > 0,
            func.sum(total_cost_col) / func.sum(total_tokens_col),
        ),
        else_=0,
    )


def _avg_effective_price_per_million_expr(
    total_cost_col: Any, total_tokens_col: Any
) -> Any:
    return _avg_effective_price_expr(total_cost_col, total_tokens_col) * 1_000_000


# === Entity / Persistence Helpers ===


def log_usage(usage: Usage, db_path: str | None = None) -> None:
    """Persist a single usage row and update the daily aggregation table."""
    with Session(get_engine(db_path), expire_on_commit=False) as session:
        session.add(usage)
        session.commit()
    try:
        upsert_daily_aggregate(usage, db_path=db_path)
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to update daily aggregate for usage ts=%s", usage.ts
        )
    try:
        from .sessions import upsert_session_from_usage

        upsert_session_from_usage(usage, db_path=db_path)
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to update session record for usage ts=%s", usage.ts
        )


def upsert_daily_aggregate(usage: Usage, db_path: str | None = None) -> None:
    """Incrementally update the daily aggregation table for a single usage row."""
    date = usage.ts[:10]
    client_source = usage.client_source or ""
    is_success = usage.status is None or usage.status < 400
    latency = usage.latency_ms or 0
    input_cost = Decimal(str(usage.input_cost_usd))
    output_cost = Decimal(str(usage.output_cost_usd))
    total_cost = Decimal(str(usage.total_cost_usd))

    engine = get_engine(db_path)
    with Session(engine) as session:
        existing = session.scalar(
            select(UsageDaily).where(
                and_(
                    UsageDaily.date == date,
                    UsageDaily.provider == usage.provider,
                    UsageDaily.model == usage.model,
                    UsageDaily.client_source == client_source,
                )
            )
        )
        if existing:
            existing.request_count += 1
            existing.prompt_tokens += usage.prompt_tokens or 0
            existing.completion_tokens += usage.completion_tokens or 0
            existing.reasoning_tokens += usage.reasoning_tokens or 0
            existing.cached_tokens += usage.cached_tokens or 0
            existing.total_tokens += usage.total_tokens or 0
            existing.tool_tokens += usage.tool_tokens or 0
            existing.cache_creation_tokens += usage.cache_creation_tokens or 0
            existing.prompt_length += usage.prompt_length
            existing.input_cost_usd += input_cost
            existing.output_cost_usd += output_cost
            existing.total_cost_usd += total_cost
            existing.successful_requests += 1 if is_success else 0
            existing.failed_requests += 0 if is_success else 1
            existing.latency_sum_ms += latency

            if not is_success:
                status = usage.status
                if status == 429:
                    existing.status_429 += 1
                elif status is not None and 400 <= status < 500:
                    existing.status_4xx += 1
                elif status is not None and status >= 500:
                    existing.status_5xx += 1
                else:
                    existing.status_unknown += 1
        else:
            status_429 = 0
            status_4xx = 0
            status_5xx = 0
            status_unknown = 0
            if not is_success:
                status = usage.status
                if status == 429:
                    status_429 = 1
                elif status is not None and 400 <= status < 500:
                    status_4xx = 1
                elif status is not None and status >= 500:
                    status_5xx = 1
                else:
                    status_unknown = 1

            session.add(
                UsageDaily(
                    date=date,
                    provider=usage.provider,
                    model=usage.model,
                    client_source=client_source,
                    request_count=1,
                    prompt_tokens=usage.prompt_tokens or 0,
                    completion_tokens=usage.completion_tokens or 0,
                    reasoning_tokens=usage.reasoning_tokens or 0,
                    cached_tokens=usage.cached_tokens or 0,
                    total_tokens=usage.total_tokens or 0,
                    tool_tokens=usage.tool_tokens or 0,
                    cache_creation_tokens=usage.cache_creation_tokens or 0,
                    prompt_length=usage.prompt_length,
                    input_cost_usd=input_cost,
                    output_cost_usd=output_cost,
                    total_cost_usd=total_cost,
                    successful_requests=1 if is_success else 0,
                    failed_requests=0 if is_success else 1,
                    latency_sum_ms=latency,
                    status_429=status_429,
                    status_4xx=status_4xx,
                    status_5xx=status_5xx,
                    status_unknown=status_unknown,
                )
            )
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
    from .base_url import get_or_create_base_url

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


# === Reporting / Query Helpers ===


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {key: _normalize_value(value) for key, value in row._mapping.items()}


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
        "status_429": 0,
        "status_4xx": 0,
        "status_5xx": 0,
        "status_unknown": 0,
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
        if status == 429:
            summary["status_429"] += 1
        elif 400 <= status < 500:
            summary["status_4xx"] += 1
        elif status >= 500:
            summary["status_5xx"] += 1
        else:
            summary["status_unknown"] += 1
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
    session_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    only_failed: bool = False,
    status_429: bool = False,
    status_4xx: bool = False,
    status_5xx: bool = False,
) -> list[Any]:
    filters: list[Any] = []
    if provider:
        filters.append(Usage.provider == provider)
    if model:
        filters.append(Usage.model == model)
    if client_source:
        filters.append(Usage.client_source == client_source)
    if session_id:
        filters.append(Usage.session_id == session_id)
    if since:
        filters.append(Usage.ts >= since)
    if until:
        filters.append(Usage.ts <= until)
    if only_failed:
        filters.append(Usage.status >= 400)
    if status_429:
        filters.append(Usage.status == 429)
    if status_4xx:
        filters.append(
            and_(Usage.status >= 400, Usage.status < 500, Usage.status != 429)
        )
    if status_5xx:
        filters.append(Usage.status >= 500)
    return filters


def _daily_usage_filters(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
) -> list[Any]:
    filters: list[Any] = []
    if since:
        filters.append(UsageDaily.date >= since[:10])
    if until:
        filters.append(UsageDaily.date <= until[:10])
    if provider:
        filters.append(UsageDaily.provider == provider)
    if model:
        filters.append(UsageDaily.model == model)
    if client_source:
        filters.append(UsageDaily.client_source == client_source)
    return filters


def _daily_usage_token_columns(*, include_reasoning: bool = True) -> tuple[Any, ...]:
    columns: list[Any] = [
        func.sum(UsageDaily.prompt_tokens).label("prompt_tokens"),
        func.sum(UsageDaily.completion_tokens).label("completion_tokens"),
    ]
    if include_reasoning:
        columns.append(func.sum(UsageDaily.reasoning_tokens).label("reasoning_tokens"))
    columns.extend(
        [
            func.sum(UsageDaily.cached_tokens).label("cached_tokens"),
            func.sum(UsageDaily.total_tokens).label("total_tokens"),
        ]
    )
    return tuple(columns)


def _daily_usage_latency_columns(
    *, include_avg_latency: bool = True, include_throughput: bool = True
) -> tuple[Any, ...]:
    columns: list[Any] = []
    if include_avg_latency:
        columns.append(
            (
                func.sum(UsageDaily.latency_sum_ms) / func.sum(UsageDaily.request_count)
            ).label("avg_latency_ms")
        )
    columns.append(func.sum(UsageDaily.latency_sum_ms).label("latency_sum_ms"))
    if include_throughput:
        columns.append(
            (
                func.sum(UsageDaily.completion_tokens)
                * 1000.0
                / func.nullif(func.sum(UsageDaily.latency_sum_ms), 0)
            ).label("avg_throughput")
        )
    return tuple(columns)


def _daily_usage_cost_columns(*, include_input_output: bool = True) -> tuple[Any, ...]:
    columns: list[Any] = []
    if include_input_output:
        columns.extend(
            [
                func.sum(UsageDaily.input_cost_usd).label("input_cost_usd"),
                func.sum(UsageDaily.output_cost_usd).label("output_cost_usd"),
            ]
        )
    columns.append(func.sum(UsageDaily.total_cost_usd).label("total_cost_usd"))
    return tuple(columns)


def _daily_usage_effective_price_columns() -> tuple[Any, ...]:
    return (
        _avg_effective_price_expr(
            UsageDaily.total_cost_usd, UsageDaily.total_tokens
        ).label("avg_effective_price_usd"),
        _avg_effective_price_per_million_expr(
            UsageDaily.total_cost_usd, UsageDaily.total_tokens
        ).label("avg_effective_price_per_million_usd"),
    )


def _daily_usage_status_columns() -> tuple[Any, ...]:
    return (
        func.sum(UsageDaily.successful_requests).label("successful_requests"),
        func.sum(UsageDaily.failed_requests).label("failed_requests"),
        func.sum(UsageDaily.status_429).label("status_429"),
        func.sum(UsageDaily.status_4xx).label("status_4xx"),
        func.sum(UsageDaily.status_5xx).label("status_5xx"),
        func.sum(UsageDaily.status_unknown).label("status_unknown"),
    )


def fetch_recent_usage(
    *,
    limit: int,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    session_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    only_failed: bool = False,
    status_429: bool = False,
    status_4xx: bool = False,
    status_5xx: bool = False,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent usage rows plus the resolved base URL when available."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        client_source=client_source,
        session_id=session_id,
        since=since,
        until=until,
        only_failed=only_failed,
        status_429=status_429,
        status_4xx=status_4xx,
        status_5xx=status_5xx,
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
    """Return distinct client_source values from usage_daily."""
    filters = _daily_usage_filters(since=since, until=until)
    filters.append(UsageDaily.client_source != "")
    query = (
        select(UsageDaily.client_source)
        .distinct()
        .where(and_(*filters))
        .order_by(UsageDaily.client_source)
    )
    with get_engine(db_path).connect() as connection:
        return [row[0] for row in connection.execute(query)]


def count_usage(
    *,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    session_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    db_path: str | None = None,
) -> int:
    """Sum request_count from usage_daily matching the optional filters.

    When *session_id* is set the daily-aggregate table cannot help (it has no
    session_id column), so we fall back to counting rows in the raw ``usage``
    table instead.
    """
    if session_id is not None:
        filters = _usage_filters(
            provider=provider,
            model=model,
            client_source=client_source,
            session_id=session_id,
            since=since,
            until=until,
        )
        query = select(func.count()).select_from(Usage)
        if filters:
            query = query.where(and_(*filters))
        with get_engine(db_path).connect() as connection:
            result = connection.execute(query).scalar_one()
            return int(result or 0)

    filters = _daily_usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )
    query = select(func.sum(UsageDaily.request_count))
    if filters:
        query = query.where(and_(*filters))
    with get_engine(db_path).connect() as connection:
        result = connection.execute(query).scalar_one()
        return int(result or 0)


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


def summarize_usage_by_source(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate usage_daily totals by client_source for dashboard source chart."""
    filters = _daily_usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )

    query = (
        select(
            UsageDaily.client_source,
            func.sum(UsageDaily.request_count).label("requests"),
            *_daily_usage_token_columns(),
            *_daily_usage_latency_columns(),
            *_daily_usage_cost_columns(),
            *_daily_usage_status_columns(),
        )
        .group_by(UsageDaily.client_source)
        .order_by(func.sum(UsageDaily.total_tokens).desc())
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine(db_path).connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def summarize_usage_by_provider(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate usage_daily totals by provider for dashboard provider chart."""
    filters = _daily_usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )

    query = (
        select(
            UsageDaily.provider,
            func.sum(UsageDaily.request_count).label("requests"),
            *_daily_usage_token_columns(),
            *_daily_usage_latency_columns(),
            *_daily_usage_cost_columns(),
            *_daily_usage_effective_price_columns(),
            *_daily_usage_status_columns(),
        )
        .group_by(UsageDaily.provider)
        .order_by(func.sum(UsageDaily.total_tokens).desc())
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine(db_path).connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def summarize_usage_daily(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate usage_daily totals by provider and model for dashboard summaries."""
    filters = _daily_usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )

    query = (
        select(
            UsageDaily.provider,
            UsageDaily.model,
            func.sum(UsageDaily.request_count).label("requests"),
            *_daily_usage_token_columns(),
            *_daily_usage_latency_columns(),
            *_daily_usage_cost_columns(),
            *_daily_usage_effective_price_columns(),
            *_daily_usage_status_columns(),
        )
        .group_by(UsageDaily.provider, UsageDaily.model)
        .order_by(func.sum(UsageDaily.total_tokens).desc())
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine(db_path).connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


# === Period aggregation ===


def _parse_tz_offset(tz_offset: str) -> tuple[int, int]:
    """Parse '+05:30' into (hours, minutes) with sign."""
    sign = 1 if tz_offset.startswith("+") else -1
    hours_str, minutes_str = tz_offset[1:].split(":", 1)
    return sign * int(hours_str), sign * int(minutes_str)


def _period_expression(granularity: str, tz_offset: str) -> Any:
    """Return a dialect-aware SQL expression that buckets Usage.ts into period strings."""
    dialect = get_engine().dialect.name
    offset_hours, offset_minutes = _parse_tz_offset(tz_offset)

    if dialect == "sqlite":
        fmt = "%Y-%m-%d %H:00" if granularity == "hour" else "%Y-%m-%d"
        modifiers: list[str] = []
        if offset_hours:
            modifiers.append(f"{offset_hours:+d} hours")
        if offset_minutes:
            modifiers.append(f"{offset_minutes:+d} minutes")
        return func.strftime(fmt, Usage.ts, *modifiers)

    if dialect == "postgresql":
        from sqlalchemy import types as sa_types

        pg_fmt = "YYYY-MM-DD HH24:00" if granularity == "hour" else "YYYY-MM-DD"
        ts_cast = func.cast(Usage.ts, sa_types.DateTime(timezone=True))
        parts: list[str] = []
        if offset_hours:
            parts.append(f"{offset_hours} hours")
        if offset_minutes:
            parts.append(f"{offset_minutes} minutes")
        ts_adjusted = (
            ts_cast + text(f"interval '{' '.join(parts)}'") if parts else ts_cast
        )
        return func.to_char(ts_adjusted, pg_fmt)

    if dialect == "mysql":
        fmt = "%Y-%m-%d %H:00" if granularity == "hour" else "%Y-%m-%d"
        ts_parsed = func.str_to_date(func.left(Usage.ts, 19), "%Y-%m-%dT%H:%i:%s")
        mysql_parts: list[str] = []
        if offset_hours:
            mysql_parts.append(f"INTERVAL {offset_hours} HOUR")
        if offset_minutes:
            mysql_parts.append(f"INTERVAL {offset_minutes} MINUTE")
        ts_adjusted = ts_parsed
        for part in mysql_parts:
            ts_adjusted = func.date_add(ts_adjusted, text(part))
        return func.date_format(ts_adjusted, fmt)

    raise ValueError(f"Unsupported database dialect: {dialect}")


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
    """Bucket usage into local-time hourly or daily periods via SQL GROUP BY."""
    filters = _usage_filters(
        provider=provider,
        model=model,
        client_source=client_source,
        since=since,
        until=until,
    )

    period_expr = _period_expression(granularity, tz_offset)

    latency_count = func.count(case((Usage.latency_ms.isnot(None), 1)))
    latency_sum = func.coalesce(
        func.sum(case((Usage.latency_ms.isnot(None), Usage.latency_ms), else_=0)),
        0,
    )

    query = (
        select(
            period_expr.label("period"),
            func.count().label("requests"),
            func.coalesce(func.sum(Usage.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(Usage.completion_tokens), 0).label(
                "completion_tokens"
            ),
            (
                func.sum(Usage.completion_tokens)
                * 1000.0
                / func.nullif(func.sum(Usage.latency_ms), 0)
            ).label("avg_throughput"),
            func.coalesce(func.sum(Usage.cached_tokens), 0).label("cached_tokens"),
            func.coalesce(func.sum(Usage.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(Usage.input_cost_usd), 0).label("input_cost_usd"),
            func.coalesce(func.sum(Usage.output_cost_usd), 0).label("output_cost_usd"),
            func.coalesce(func.sum(Usage.total_cost_usd), 0).label("total_cost_usd"),
            latency_sum.label("latency_sum"),
            latency_count.label("latency_count"),
            func.count(
                case((and_(Usage.status.isnot(None), Usage.status >= 400), 1))
            ).label("failed_requests"),
            func.count(
                case((or_(Usage.status.is_(None), Usage.status < 400), 1))
            ).label("successful_requests"),
        )
        .group_by(period_expr)
        .order_by(period_expr)
    )
    if filters:
        query = query.where(and_(*filters))

    result = []
    with get_engine().connect() as connection:
        for row in connection.execute(query):
            count = row.latency_count
            avg_latency = row.latency_sum / count if count > 0 else 0
            result.append(
                {
                    "period": row.period,
                    "requests": row.requests,
                    "prompt_tokens": row.prompt_tokens,
                    "completion_tokens": row.completion_tokens,
                    "avg_throughput": _normalize_value(row.avg_throughput),
                    "cached_tokens": row.cached_tokens,
                    "total_tokens": row.total_tokens,
                    "input_cost_usd": _normalize_value(row.input_cost_usd),
                    "output_cost_usd": _normalize_value(row.output_cost_usd),
                    "total_cost_usd": _normalize_value(row.total_cost_usd),
                    "avg_latency_ms": _normalize_value(avg_latency),
                    "successful_requests": row.successful_requests,
                    "failed_requests": row.failed_requests,
                }
            )
    return result


def aggregate_daily_by_period(
    *,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Read daily-bucketed usage from the pre-aggregated usage_daily table."""
    filters = _daily_usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )

    query = (
        select(
            UsageDaily.date.label("period"),
            func.sum(UsageDaily.request_count).label("requests"),
            *_daily_usage_token_columns(include_reasoning=False),
            *_daily_usage_cost_columns(),
            *_daily_usage_status_columns(),
            *_daily_usage_latency_columns(),
        )
        .group_by(UsageDaily.date)
        .order_by(UsageDaily.date)
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine(db_path).connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]


def aggregate_daily_by_dimension(
    *,
    dimension: str,
    since: str | None = None,
    until: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    client_source: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Read daily-bucketed usage grouped by a dimension (model/provider/client_source)."""
    filters = _daily_usage_filters(
        since=since,
        until=until,
        provider=provider,
        model=model,
        client_source=client_source,
    )

    if dimension == "provider":
        dim_col = UsageDaily.provider
    elif dimension == "client_source":
        dim_col = UsageDaily.client_source
    else:
        dim_col = UsageDaily.model

    query = (
        select(
            dim_col.label("dimension"),
            UsageDaily.date.label("period"),
            func.sum(UsageDaily.request_count).label("requests"),
            func.sum(UsageDaily.prompt_tokens).label("prompt_tokens"),
            func.sum(UsageDaily.cached_tokens).label("cached_tokens"),
            func.sum(UsageDaily.total_tokens).label("total_tokens"),
            func.sum(UsageDaily.total_cost_usd).label("total_cost_usd"),
            func.sum(UsageDaily.completion_tokens).label("completion_tokens"),
            func.sum(UsageDaily.latency_sum_ms).label("latency_sum_ms"),
            *_daily_usage_status_columns(),
        )
        .group_by(dim_col, UsageDaily.date)
        .order_by(UsageDaily.date)
    )
    if filters:
        query = query.where(and_(*filters))
    with get_engine(db_path).connect() as connection:
        return [_row_to_dict(row) for row in connection.execute(query)]
