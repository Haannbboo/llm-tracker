"""Session-related database operations.

Extracted from database/__init__.py during Phase 5 refactoring.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from .models import (
    SessionRecord,
    Usage,
    VALID_OUTCOMES,
    VALID_SOURCES,
)
from .engine import get_engine


def _successful_usage_count(usages: list[Usage]) -> int:
    return sum(1 for usage in usages if usage.status is None or usage.status < 400)


def _primary_by_cost(costs: dict[str, float]) -> str | None:
    if not costs:
        return None
    return max(costs, key=costs.get)  # type: ignore[arg-type]


def _load_cost_map(payload: str | None) -> dict[str, float]:
    return json.loads(payload or "{}")


def _add_usage_to_cost_maps(
    usage: Usage,
    *,
    total_cost: Decimal,
    models_costs: dict[str, float],
    providers_costs: dict[str, float],
) -> None:
    models_costs[usage.model] = models_costs.get(usage.model, 0) + float(total_cost)
    providers_costs[usage.provider] = providers_costs.get(usage.provider, 0) + float(
        total_cost
    )


def _cost_maps_from_usage(
    usages: list[Usage],
) -> tuple[dict[str, float], dict[str, float]]:
    models_costs: dict[str, float] = {}
    providers_costs: dict[str, float] = {}
    for usage in usages:
        _add_usage_to_cost_maps(
            usage,
            total_cost=Decimal(str(usage.total_cost_usd)),
            models_costs=models_costs,
            providers_costs=providers_costs,
        )
    return models_costs, providers_costs


def _session_record_kwargs(
    session_id: str,
    usages: list[Usage],
    *,
    now: str,
    missing_ttft_as_zero: bool = False,
) -> dict[str, Any]:
    request_count = len(usages)
    successful = _successful_usage_count(usages)
    total_cost = sum(Decimal(str(usage.total_cost_usd)) for usage in usages)
    latency_sum = sum(usage.latency_ms or 0 for usage in usages)
    if missing_ttft_as_zero:
        ttft_values = [usage.ttft_ms or 0 for usage in usages]
    else:
        ttft_values = [usage.ttft_ms for usage in usages if usage.ttft_ms is not None]
    models_costs, providers_costs = _cost_maps_from_usage(usages)

    return {
        "session_id": session_id,
        "client_source": usages[0].client_source,
        "started": usages[0].ts,
        "ended": usages[-1].ts,
        "request_count": request_count,
        "successful_requests": successful,
        "failed_requests": request_count - successful,
        "total_tokens": sum(usage.total_tokens or 0 for usage in usages),
        "prompt_tokens": sum(usage.prompt_tokens or 0 for usage in usages),
        "completion_tokens": sum(usage.completion_tokens or 0 for usage in usages),
        "cached_tokens": sum(usage.cached_tokens or 0 for usage in usages),
        "total_cost_usd": total_cost,
        "latency_sum_ms": latency_sum,
        "avg_latency_ms": latency_sum / request_count if request_count else None,
        "avg_ttft_ms": sum(ttft_values) / len(ttft_values) if ttft_values else None,
        "primary_provider": _primary_by_cost(providers_costs),
        "primary_model": _primary_by_cost(models_costs),
        "providers_json": json.dumps(providers_costs),
        "models_json": json.dumps(models_costs),
        "last_usage_id": usages[-1].id,
        "updated_at": now,
    }


def upsert_session_from_usage(usage: Usage, db_path: str | None = None) -> None:
    """Incrementally update the sessions table for a single usage row."""
    if not usage.session_id:
        return

    is_success = usage.status is None or usage.status < 400
    latency = usage.latency_ms or 0
    ttft = usage.ttft_ms or 0
    total_cost = Decimal(str(usage.total_cost_usd))
    now = datetime.now(timezone.utc).isoformat()

    engine = get_engine(db_path)
    with Session(engine) as session:
        existing = session.get(SessionRecord, usage.session_id)
        if existing:
            if usage.ts < existing.started:
                existing.started = usage.ts
            if usage.ts > existing.ended:
                existing.ended = usage.ts

            existing.request_count += 1
            existing.prompt_tokens += usage.prompt_tokens or 0
            existing.completion_tokens += usage.completion_tokens or 0
            existing.cached_tokens += usage.cached_tokens or 0
            existing.total_tokens += usage.total_tokens or 0
            existing.total_cost_usd += total_cost
            existing.latency_sum_ms += latency
            existing.successful_requests += 1 if is_success else 0
            existing.failed_requests += 0 if is_success else 1

            existing.avg_latency_ms = existing.latency_sum_ms / existing.request_count
            old_n = existing.request_count - 1
            old_avg_ttft = float(existing.avg_ttft_ms or 0)
            existing.avg_ttft_ms = (
                old_avg_ttft * old_n + ttft
            ) / existing.request_count

            models_costs = _load_cost_map(existing.models_json)
            providers_costs = _load_cost_map(existing.providers_json)
            _add_usage_to_cost_maps(
                usage,
                total_cost=total_cost,
                models_costs=models_costs,
                providers_costs=providers_costs,
            )

            existing.models_json = json.dumps(models_costs)
            existing.providers_json = json.dumps(providers_costs)
            existing.primary_model = _primary_by_cost(models_costs)
            existing.primary_provider = _primary_by_cost(providers_costs)

            existing.last_usage_id = usage.id
            existing.updated_at = now
        else:
            session.add(
                SessionRecord(
                    **_session_record_kwargs(
                        usage.session_id,
                        [usage],
                        now=now,
                        missing_ttft_as_zero=True,
                    )
                )
            )
        session.commit()


def rebuild_sessions_from_usage(db_path: str | None = None) -> int:
    """Clear and rebuild sessions table from usage rows. Returns count of sessions."""
    engine = get_engine(db_path)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sessions"))

    with Session(engine) as session:
        rows = (
            session.execute(
                select(Usage)
                .where(Usage.session_id.isnot(None), Usage.session_id != "")
                .order_by(Usage.session_id, Usage.ts)
            )
            .scalars()
            .all()
        )

    grouped: dict[str, list[Usage]] = {}
    for row in rows:
        grouped.setdefault(row.session_id, []).append(row)  # type: ignore[arg-type]

    now = datetime.now(timezone.utc).isoformat()
    count = 0

    with Session(engine) as session:
        for sid, usages in grouped.items():
            session.add(
                SessionRecord(
                    **_session_record_kwargs(
                        sid,
                        usages,
                        now=now,
                    )
                )
            )
            count += 1

        session.commit()

    return count


def upsert_session_evaluation(
    session_id: str,
    outcome: str,
    source: str = "manual",
    confidence: float | None = None,
    task_title: str | None = None,
    summary: str | None = None,
    evidence: list[str] | None = None,
    failure_reason: str | None = None,
    db_path: str | None = None,
) -> None:
    """Set evaluation on an existing session. Raises ValueError if session not found."""
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome: {outcome}. Must be one of {VALID_OUTCOMES}")
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source: {source}. Must be one of {VALID_SOURCES}")

    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine(db_path)
    with Session(engine) as session:
        record = session.get(SessionRecord, session_id)
        if not record:
            raise ValueError(f"Session not found: {session_id}")
        record.outcome = outcome
        record.source = source
        record.confidence = confidence
        record.task_title = task_title
        record.summary = summary
        record.evidence_json = json.dumps(evidence) if evidence else None
        record.failure_reason = failure_reason
        record.evaluated_at = now
        session.commit()


def get_session_evaluation(
    session_id: str, db_path: str | None = None
) -> dict[str, Any] | None:
    """Return evaluation dict for a session, or None if not found or not evaluated."""
    engine = get_engine(db_path)
    with Session(engine) as session:
        rec = session.get(SessionRecord, session_id)
        if not rec or rec.outcome is None:
            return None
        return {
            "session_id": rec.session_id,
            "outcome": rec.outcome,
            "source": rec.source,
            "confidence": float(rec.confidence) if rec.confidence is not None else None,
            "task_title": rec.task_title,
            "summary": rec.summary,
            "evidence": json.loads(rec.evidence_json) if rec.evidence_json else [],
            "failure_reason": rec.failure_reason,
            "evaluated_at": rec.evaluated_at,
        }


def delete_session_evaluation(session_id: str, db_path: str | None = None) -> bool:
    """Clear evaluation columns on a session. Returns True if session found."""
    engine = get_engine(db_path)
    with Session(engine) as session:
        rec = session.get(SessionRecord, session_id)
        if not rec:
            return False
        rec.outcome = None
        rec.source = None
        rec.confidence = None
        rec.task_title = None
        rec.summary = None
        rec.evidence_json = None
        rec.failure_reason = None
        rec.evaluated_at = None
        session.commit()
        return True


# Allowed sort columns for fetch_sessions (maps frontend names to SessionRecord columns)
_SESSION_SORT_COLUMNS = {
    "session_id": SessionRecord.session_id,
    "client_source": SessionRecord.client_source,
    "started": SessionRecord.started,
    "ended": SessionRecord.ended,
    "request_count": SessionRecord.request_count,
    "total_tokens": SessionRecord.total_tokens,
    "total_cost_usd": SessionRecord.total_cost_usd,
    "avg_latency_ms": SessionRecord.avg_latency_ms,
    "avg_ttft_ms": SessionRecord.avg_ttft_ms,
}

_MODEL_EFFECTIVENESS_GROUPS = {"model", "provider", "source"}


def _compute_duration_s(started: str | None, ended: str | None) -> int:
    """Compute duration in seconds from ISO timestamps."""
    if not started or not ended:
        return 0
    try:
        fmt = "%Y-%m-%dT%H:%M:%S"
        start = datetime.strptime(started[:19], fmt)
        end = datetime.strptime(ended[:19], fmt)
        return max(0, int((end - start).total_seconds()))
    except (ValueError, TypeError):
        return 0


def _normalize_timestamp_filter(value: str) -> str:
    try:
        normalized = f"{value[:-1]}+00:00" if value.endswith(("Z", "z")) else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat()


def _session_filters(
    *,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[Any]:
    filters: list[Any] = []
    if client_source:
        filters.append(SessionRecord.client_source == client_source)
    if since:
        filters.append(SessionRecord.started >= _normalize_timestamp_filter(since))
    if until:
        filters.append(SessionRecord.ended <= _normalize_timestamp_filter(until))
    return filters


def _session_record_to_dict(rec: SessionRecord) -> dict[str, Any]:
    """Convert a SessionRecord ORM object to the API response dict."""
    started = rec.started
    ended = rec.ended
    result: dict[str, Any] = {
        "session_id": rec.session_id,
        "client_source": rec.client_source or "",
        "model": rec.primary_model or "",
        "started": started,
        "ended": ended,
        "duration_s": _compute_duration_s(started, ended),
        "request_count": rec.request_count,
        "total_tokens": rec.total_tokens,
        "prompt_tokens": rec.prompt_tokens,
        "completion_tokens": rec.completion_tokens,
        "cached_tokens": rec.cached_tokens,
        "total_cost_usd": float(rec.total_cost_usd),
        "avg_latency_ms": round(float(rec.avg_latency_ms or 0), 1),
        "latency_sum_ms": float(rec.latency_sum_ms),
        "avg_ttft_ms": round(float(rec.avg_ttft_ms or 0), 1),
        "successful_requests": rec.successful_requests,
        "failed_requests": rec.failed_requests,
    }
    if rec.outcome is not None:
        result["evaluation"] = {
            "session_id": rec.session_id,
            "outcome": rec.outcome,
            "source": rec.source,
            "confidence": float(rec.confidence) if rec.confidence is not None else None,
            "task_title": rec.task_title,
            "summary": rec.summary,
            "evidence": json.loads(rec.evidence_json) if rec.evidence_json else [],
            "failure_reason": rec.failure_reason,
            "evaluated_at": rec.evaluated_at,
        }
    else:
        result["evaluation"] = None
    return result


def aggregate_model_effectiveness(
    *,
    group_by: str = "model",
    since: str | None = None,
    until: str | None = None,
    client_source: str | None = None,
    db_path: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Aggregate evaluated session outcomes by model, provider, or client source."""
    if group_by not in _MODEL_EFFECTIVENESS_GROUPS:
        raise ValueError(
            f"Invalid group_by: {group_by}. Must be one of {sorted(_MODEL_EFFECTIVENESS_GROUPS)}"
        )

    filters = _session_filters(
        client_source=client_source,
        since=since,
        until=until,
    )

    query = select(SessionRecord)
    if filters:
        query = query.where(and_(*filters))

    with Session(get_engine(db_path)) as session:
        records = session.execute(query).scalars().all()

    grouped: dict[str, dict[str, Any]] = {}
    for rec in records:
        if group_by == "provider":
            raw_key = rec.primary_provider
        elif group_by == "source":
            raw_key = rec.client_source
        else:
            raw_key = rec.primary_model
        key = raw_key or "unknown"

        group = grouped.setdefault(
            key,
            {
                "key": key,
                "session_count": 0,
                "evaluated_count": 0,
                "solved_count": 0,
                "partial_count": 0,
                "failed_count": 0,
                "stuck_count": 0,
                "unknown_count": 0,
                "no_op_count": 0,
                "solve_rate": None,
                "total_cost_usd": 0.0,
                "cost_per_solved": None,
                "avg_duration_s": 0.0,
                "_evaluated_cost_usd": 0.0,
                "_total_duration_s": 0,
            },
        )

        cost = float(rec.total_cost_usd or 0)
        group["session_count"] += 1
        group["total_cost_usd"] += cost
        group["_total_duration_s"] += _compute_duration_s(rec.started, rec.ended)

        if rec.outcome == "solved":
            group["solved_count"] += 1
            group["evaluated_count"] += 1
            group["_evaluated_cost_usd"] += cost
        elif rec.outcome == "partial":
            group["partial_count"] += 1
            group["evaluated_count"] += 1
            group["_evaluated_cost_usd"] += cost
        elif rec.outcome == "failed":
            group["failed_count"] += 1
            group["evaluated_count"] += 1
            group["_evaluated_cost_usd"] += cost
        elif rec.outcome == "stuck":
            group["stuck_count"] += 1
            group["evaluated_count"] += 1
            group["_evaluated_cost_usd"] += cost
        elif rec.outcome == "no_op":
            group["no_op_count"] += 1
        else:
            group["unknown_count"] += 1

    groups: list[dict[str, Any]] = []
    for group in grouped.values():
        evaluated_count = group["evaluated_count"]
        solved_count = group["solved_count"]
        session_count = group["session_count"]
        if evaluated_count:
            group["solve_rate"] = round(solved_count / evaluated_count, 4)
        if solved_count:
            group["cost_per_solved"] = group["_evaluated_cost_usd"] / solved_count
        group["avg_duration_s"] = (
            round(group["_total_duration_s"] / session_count, 1)
            if session_count
            else 0.0
        )
        group["total_cost_usd"] = float(group["total_cost_usd"])
        group.pop("_evaluated_cost_usd")
        group.pop("_total_duration_s")
        groups.append(group)

    groups.sort(key=lambda group: (-group["session_count"], group["key"]))
    return {"groups": groups}


def fetch_sessions(
    *,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
    sort_by: str = "ended",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Return sessions from the persisted sessions table."""
    filters = _session_filters(
        client_source=client_source,
        since=since,
        until=until,
    )

    sort_col = _SESSION_SORT_COLUMNS.get(sort_by)
    python_sort = sort_by == "duration_s"

    engine = get_engine(db_path)

    if python_sort:
        # Fetch all, sort+paginate in Python
        query = select(SessionRecord)
        if filters:
            query = query.where(and_(*filters))
        with Session(engine) as session:
            records = session.execute(query).scalars().all()
        result = [_session_record_to_dict(r) for r in records]
        result.sort(key=lambda r: r["duration_s"], reverse=(sort_order == "desc"))
        return result[offset : offset + limit]

    if sort_col is not None:
        order = sort_col.asc() if sort_order == "asc" else sort_col.desc()
    else:
        order = SessionRecord.ended.desc()

    query = select(SessionRecord).order_by(order).limit(limit).offset(offset)
    if filters:
        query = query.where(and_(*filters))

    with Session(engine) as session:
        records = session.execute(query).scalars().all()

    return [_session_record_to_dict(r) for r in records]


def count_sessions(
    *,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
    db_path: str | None = None,
) -> int:
    """Count sessions from the persisted sessions table."""
    filters = _session_filters(
        client_source=client_source,
        since=since,
        until=until,
    )

    query = select(func.count()).select_from(SessionRecord)
    if filters:
        query = query.where(and_(*filters))
    with get_engine(db_path).connect() as connection:
        result = connection.execute(query).scalar_one()
        return int(result or 0)


def summarize_sessions(
    *,
    client_source: str | None = None,
    since: str | None = None,
    until: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return aggregate stats across all sessions matching the filters."""
    filters = _session_filters(
        client_source=client_source,
        since=since,
        until=until,
    )

    query = select(
        func.count().label("session_count"),
        func.sum(SessionRecord.total_tokens).label("total_tokens"),
        func.sum(SessionRecord.total_cost_usd).label("total_cost_usd"),
        func.avg(SessionRecord.avg_latency_ms).label("avg_latency_ms"),
        func.sum(SessionRecord.latency_sum_ms).label("latency_sum_ms"),
    )
    if filters:
        query = query.where(and_(*filters))

    with get_engine(db_path).connect() as connection:
        row = connection.execute(query).fetchone()

    if not row or row.session_count == 0:
        return {
            "session_count": 0,
            "avg_duration_s": 0,
            "total_tokens": 0,
            "total_cost_usd": 0,
            "avg_latency_ms": 0,
        }

    # Compute avg_duration_s from persisted started/ended in Python
    duration_query = select(SessionRecord.started, SessionRecord.ended)
    if filters:
        duration_query = duration_query.where(and_(*filters))

    with get_engine(db_path).connect() as connection:
        duration_rows = connection.execute(duration_query).fetchall()

    durations = [_compute_duration_s(r.started, r.ended) for r in duration_rows]
    avg_duration = sum(durations) / len(durations) if durations else 0

    return {
        "session_count": int(row.session_count),
        "avg_duration_s": round(avg_duration, 1),
        "total_tokens": int(row.total_tokens or 0),
        "total_cost_usd": float(row.total_cost_usd or 0),
        "avg_latency_ms": round(float(row.avg_latency_ms or 0), 1),
    }
